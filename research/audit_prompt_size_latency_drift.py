"""Passo 2a — read-only: prompt size, latency regression, drift, stop-first vs breakeven.

Does not write to the installed Hermes profile or Glitch exchange.
Rebuilds prompts via build_prompt without calling market_perception_context
(avoids rendering/writing chart images). Documents omitted sections.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import statistics
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE = Path(r"C:\Users\arifr\Projects\glitch-hermes-profile")
LIVE = Path.home() / "AppData" / "Local" / "hermes" / "profiles" / "glitch"
SCRIPTS = PROFILE / "scripts"
GD = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
EX = GD / "hermes" / "exchange"
ATTEMPTS = EX / "hermes" / "model-attempts"
OUTBOX = EX / "hermes" / "outbox"
PACKETS = EX / "glitch" / "decision-packets"
SUP = EX / "hermes" / "supervisor"
OUT_DIR = PROFILE / "research"
OUT_JSON = OUT_DIR / "report-prompt-size-latency-drift.json"
OUT_MD = OUT_DIR / "report-prompt-size-latency-drift.md"

CURRENT_HASH = "686f54d1a4fb"
POINT_VALUE = {"MES": 5.0, "MNQ": 2.0, "M2K": 5.0}

R2_WEAK = 0.15
R2_STRONG = 0.30
QUINTILE_RATIO = 1.15
DRIFT_CHEAP_USD = 10.0
DRIFT_EXPENSIVE_USD = 25.0
DRIFT_REL_CHEAP = 0.15
GAP_IC_MIN_PP = 0.05
MIN_RESOLVED_FOR_SELECTION = 30

sys.path.insert(0, str(SCRIPTS))


def load_direct():
    spec = importlib.util.spec_from_file_location(
        "direct_cycle", SCRIPTS / "run-direct-glitch-cycle.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def load_eval():
    spec = importlib.util.spec_from_file_location(
        "evalcog", SCRIPTS / "evaluate-frozen-cognition.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["evalcog"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def parse_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * p / 100.0
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)


def r_squared(xs: list[float], ys: list[float]) -> dict[str, Any] | None:
    if len(xs) < 10 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    beta = sxy / sxx
    r = sxy / math.sqrt(sxx * syy)
    return {
        "n": len(xs),
        "r": round(r, 4),
        "r2": round(r * r, 4),
        "slope_seconds_per_char": beta,
        "intercept": my - beta * mx,
        "x_mean": mx,
        "y_mean": my,
    }


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float | None:
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def walk_key_chars(obj: Any, key: str, acc: list[int]) -> None:
    if isinstance(obj, dict):
        if key in obj:
            acc.append(len(json.dumps(obj[key], separators=(",", ":"), ensure_ascii=False)))
        for value in obj.values():
            walk_key_chars(value, key, acc)
    elif isinstance(obj, list):
        for value in obj:
            walk_key_chars(value, key, acc)


def section_sizes(envelope: dict[str, Any]) -> dict[str, int]:
    return {
        key: len(json.dumps(value, separators=(",", ":"), ensure_ascii=False))
        for key, value in envelope.items()
    }


def packet_prices(packet: dict[str, Any]) -> dict[str, float]:
    prices: dict[str, float] = {}
    frames = packet.get("frames")
    if not isinstance(frames, list) or not frames:
        return prices
    latest = frames[-1] if isinstance(frames[-1], dict) else {}
    market = latest.get("market_snapshot") if isinstance(latest, dict) else None
    instruments = market.get("instruments") if isinstance(market, dict) else None
    if not isinstance(instruments, list):
        return prices
    for row in instruments:
        if not isinstance(row, dict):
            continue
        root = str(row.get("instrument_root") or row.get("instrument") or "").upper().split()[0]
        price = number(row.get("current_price"))
        if root and price is not None:
            prices[root] = price
    return prices


def packet_timestamp(packet: dict[str, Any]) -> datetime | None:
    for key in ("window_close_utc", "packet_id", "created_utc"):
        raw = packet.get(key)
        if key == "packet_id" and isinstance(raw, str) and len(raw) >= 15:
            try:
                return datetime.strptime(raw[:15], "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        dt = parse_utc(raw)
        if dt is not None:
            return dt
    frames = packet.get("frames")
    if isinstance(frames, list) and frames and isinstance(frames[-1], dict):
        market = frames[-1].get("market_snapshot")
        if isinstance(market, dict):
            return parse_utc(market.get("created_utc"))
    return None


def paso0_parity() -> dict[str, Any]:
    import hashlib

    paths = [
        "scripts/run-direct-glitch-cycle.py",
        "scripts/market_structure.py",
        "scripts/native_risk.py",
        "scripts/jev_evidence.py",
        "scripts/jev_observation.py",
        "scripts/jev_provider.py",
        "scripts/run-jev-shadow.py",
        "SOUL.md",
        "skills/glitch-market-scan/SKILL.md",
        "skills/glitch-setup-state/SKILL.md",
        "skills/glitch-order-flow/SKILL.md",
        "skills/glitch-position-management/SKILL.md",
        "skills/glitch-build-intent/SKILL.md",
    ]

    def digest(path: Path) -> str | None:
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]

    rows = []
    for rel in paths:
        repo_path = PROFILE / rel
        live_path = LIVE / rel
        ha, hb = digest(repo_path), digest(live_path)
        rows.append({
            "path": rel,
            "match": ha is not None and ha == hb,
            "repo": ha,
            "live": hb,
            "repo_bytes": repo_path.stat().st_size if repo_path.is_file() else None,
            "live_bytes": live_path.stat().st_size if live_path.is_file() else None,
        })
    soul = next(r for r in rows if r["path"] == "SOUL.md")
    return {
        "synced": False,
        "note": "diff only; no sync performed",
        "soul_direction": (
            "repo_ahead_of_live_vacuum_stop_line" if not soul["match"] else "identical"
        ),
        "soul_detail": (
            "Repo (dfb8f7b) rewrote volume-vacuum stop sentence; live still has older "
            "'Supplied volume-at-price facts may add evidence...' wording. Syncing either "
            "way changes cognitive_bundle_hash."
        ),
        "bundle_files": rows,
        "all_scripts_match": all(r["match"] for r in rows if r["path"] != "SOUL.md"),
    }


def rebuild_prompt_metrics(
    direct: Any,
    cycle_id: str,
    packet: dict[str, Any],
    attempt: dict[str, Any],
    journals: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        scenario = direct.build_scenario(packet)
    except Exception as error:
        return {"error": f"build_scenario:{type(error).__name__}:{error}"}
    decision_mode = str(attempt.get("decision_mode") or "flat_scan")
    prior = None
    if decision_mode in {"flat_scan", "trigger_review"}:
        try:
            prior = direct.latest_prior_cognition(EX, cycle_id)
        except Exception:
            prior = None
    omitted = ["market_perception_full_rebuild", "chart_image", "historical_exact_journals"]
    try:
        prompt = direct.build_prompt(
            packet,
            scenario,
            journals,
            None,
            invocation_reason=attempt.get("invocation_reason"),
            invocation_context=None,
            prior_cognition=prior,
            market_perception=None,
            jev_evidence=None,
        )
    except Exception as error:
        return {
            "error": f"build_prompt:{type(error).__name__}:{error}",
            "traceback": traceback.format_exc()[-800:],
            "omitted": omitted,
        }
    marker = "CURRENT_CYCLE="
    idx = prompt.find(marker)
    preamble_chars = idx if idx >= 0 else 0
    envelope: dict[str, Any] | None = None
    if idx >= 0:
        raw = prompt[idx + len(marker) :]
        try:
            envelope, _end = json.JSONDecoder().raw_decode(raw)
        except json.JSONDecodeError:
            envelope = None
    sizes = section_sizes(envelope) if isinstance(envelope, dict) else {}
    session_acc: list[int] = []
    volume_acc: list[int] = []
    bars_acc: list[int] = []
    if isinstance(envelope, dict):
        walk_key_chars(envelope, "session_rows", session_acc)
        walk_key_chars(envelope, "volume_profile", volume_acc)
        walk_key_chars(envelope, "bars_1m", bars_acc)
    packet_chars = len(json.dumps(packet, separators=(",", ":"), ensure_ascii=False))
    raw_session: list[int] = []
    walk_key_chars(packet, "session_rows", raw_session)
    return {
        "prompt_chars": len(prompt),
        "prompt_utf8_bytes": len(prompt.encode("utf-8")),
        "preamble_chars": preamble_chars,
        "section_chars": sizes,
        "session_rows_chars_in_envelope": sum(session_acc),
        "volume_profile_chars_in_envelope": sum(volume_acc),
        "bars_1m_chars_in_envelope": sum(bars_acc),
        "raw_packet_chars": packet_chars,
        "raw_session_rows_chars": sum(raw_session),
        "session_rows_share_of_prompt": (
            round(sum(session_acc) / len(prompt), 4) if prompt else None
        ),
        "omitted_from_rebuild": omitted,
        "decision_mode_used": decision_mode,
        "prior_cognition_present": prior is not None,
    }


def audit_size_latency(direct: Any) -> dict[str, Any]:
    journals: dict[str, Any] = {}
    try:
        journals = direct.journal_tail(GD)
        journals.update(direct.learning_context(EX))
    except Exception as error:
        journals = {"_journal_error": f"{type(error).__name__}:{error}"}

    rows: list[dict[str, Any]] = []
    errors: Counter[str] = Counter()
    paths = sorted(ATTEMPTS.glob("*.json"))
    total = len(paths)
    for index, path in enumerate(paths, start=1):
        if index % 200 == 0:
            print(f"  rebuild {index}/{total} ok={len(rows)}", flush=True)
        attempt = load_json(path)
        if not attempt:
            continue
        status = str(attempt.get("status") or "")
        if status not in {"completed", "decision_ready"}:
            continue
        started = parse_utc(attempt.get("started_utc"))
        completed = parse_utc(attempt.get("completed_utc"))
        if started is None or completed is None:
            continue
        elapsed = (completed - started).total_seconds()
        if elapsed < 0 or elapsed > 600:
            continue
        cycle_id = path.stem
        packet = load_json(PACKETS / f"{cycle_id}.json")
        if not packet:
            errors["packet_missing"] += 1
            continue
        metrics = rebuild_prompt_metrics(direct, cycle_id, packet, attempt, journals)
        if not metrics or metrics.get("error"):
            errors[str((metrics or {}).get("error") or "rebuild_failed")[:80]] += 1
            continue
        rows.append({
            "cycle_id": cycle_id,
            "elapsed_s": elapsed,
            "decision_mode": attempt.get("decision_mode"),
            "prompt_version": attempt.get("prompt_version"),
            "cognitive_bundle_hash": attempt.get("cognitive_bundle_hash"),
            "output_repair_count": attempt.get("output_repair_count") or 0,
            **metrics,
        })

    current = [r for r in rows if str(r.get("cognitive_bundle_hash") or "") == CURRENT_HASH]
    focus = current if len(current) >= 50 else rows

    def regress(subset: list[dict[str, Any]], x_key: str) -> dict[str, Any]:
        paired = [
            (float(r[x_key]), float(r["elapsed_s"]))
            for r in subset
            if r.get(x_key) is not None
        ]
        if len(paired) < 10:
            return {"n": len(paired)}
        xs = [p[0] for p in paired]
        ys = [p[1] for p in paired]
        fit = r_squared(xs, ys) or {"n": len(paired)}
        order = sorted(paired, key=lambda p: p[0])
        q = max(1, len(order) // 5)
        buckets = []
        for i in range(5):
            chunk = order[i * q : (i + 1) * q] if i < 4 else order[i * q :]
            if not chunk:
                continue
            buckets.append({
                "quintile": i + 1,
                "n": len(chunk),
                "x_p50": pct([c[0] for c in chunk], 50),
                "elapsed_p50": pct([c[1] for c in chunk], 50),
            })
        thin = buckets[0]["elapsed_p50"] if buckets else None
        fat = buckets[-1]["elapsed_p50"] if buckets else None
        ratio = (fat / thin) if thin and fat and thin > 0 else None
        return {
            **fit,
            "x_key": x_key,
            "elapsed_p50": pct(ys, 50),
            "elapsed_p95": pct(ys, 95),
            "x_p50": pct(xs, 50),
            "quintiles": buckets,
            "fat_over_thin_elapsed_p50_ratio": round(ratio, 4) if ratio else None,
        }

    size_summary = {
        "prompt_chars_p50": pct([r["prompt_chars"] for r in focus], 50),
        "session_rows_chars_p50": pct(
            [r["session_rows_chars_in_envelope"] for r in focus], 50
        ),
        "session_rows_share_p50": pct(
            [
                r["session_rows_share_of_prompt"]
                for r in focus
                if r.get("session_rows_share_of_prompt") is not None
            ],
            50,
        ),
        "decision_packet_chars_p50": pct(
            [
                (r.get("section_chars") or {}).get("decision_packet")
                for r in focus
                if (r.get("section_chars") or {}).get("decision_packet")
            ],
            50,
        ),
    }

    return {
        "rows_ok": len(rows),
        "rows_current_hash": len(current),
        "focus": "current_hash" if focus is current else "all_completed",
        "focus_n": len(focus),
        "rebuild_errors": dict(errors),
        "size_summary_focus": size_summary,
        "regression_prompt_chars": regress(focus, "prompt_chars"),
        "regression_session_rows_chars": regress(focus, "session_rows_chars_in_envelope"),
        "regression_all_prompt_chars": regress(rows, "prompt_chars"),
        "by_mode_elapsed_p50": {
            mode: pct([r["elapsed_s"] for r in focus if r.get("decision_mode") == mode], 50)
            for mode in sorted({str(r.get("decision_mode")) for r in focus})
        },
        "sample_rows": [
            {
                "cycle_id": r["cycle_id"],
                "elapsed_s": round(r["elapsed_s"], 2),
                "prompt_chars": r["prompt_chars"],
                "session_rows_chars_in_envelope": r["session_rows_chars_in_envelope"],
                "session_rows_share_of_prompt": r["session_rows_share_of_prompt"],
                "decision_mode": r["decision_mode"],
            }
            for r in sorted(focus, key=lambda x: x["elapsed_s"], reverse=True)[:8]
        ],
    }


def audit_drift() -> dict[str, Any]:
    packet_index: list[tuple[datetime, str, dict[str, float]]] = []
    for path in sorted(PACKETS.glob("*.json")):
        packet = load_json(path)
        if not packet:
            continue
        ts = packet_timestamp(packet)
        if ts is None:
            continue
        packet_index.append((ts, path.stem, packet_prices(packet)))
    packet_index.sort(key=lambda row: row[0])

    def price_at(ts: datetime) -> dict[str, float] | None:
        candidate = None
        for pts, _cid, prices in packet_index:
            if pts <= ts:
                candidate = prices
            else:
                break
        return candidate

    enter_cycles = set()
    for path in OUTBOX.glob("*.json"):
        batch = load_json(path)
        if not batch:
            continue
        for decision in batch.get("decisions") or []:
            if not isinstance(decision, dict):
                continue
            if str(decision.get("action") or "") in {"ENTER_LONG", "ENTER_SHORT"}:
                enter_cycles.add(path.stem)

    rows = []
    for path in sorted(ATTEMPTS.glob("*.json")):
        attempt = load_json(path)
        if not attempt or attempt.get("status") not in {"completed", "decision_ready"}:
            continue
        if str(attempt.get("cognitive_bundle_hash") or "") != CURRENT_HASH:
            continue
        started = parse_utc(attempt.get("started_utc"))
        completed = parse_utc(attempt.get("completed_utc"))
        if started is None or completed is None:
            continue
        start_prices = price_at(started)
        end_prices = price_at(completed)
        if not start_prices or not end_prices:
            continue
        for root in sorted(set(start_prices) & set(end_prices)):
            pts = abs(end_prices[root] - start_prices[root])
            usd = pts * POINT_VALUE.get(root, 0.0)
            rows.append({
                "cycle_id": path.stem,
                "root": root,
                "abs_pts": pts,
                "abs_usd": usd,
                "elapsed_s": (completed - started).total_seconds(),
                "is_enter_cycle": path.stem in enter_cycles,
            })

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"n": 0}
        usds = [r["abs_usd"] for r in items]
        return {
            "n": len(items),
            "abs_usd_p50": pct(usds, 50),
            "abs_usd_p95": pct(usds, 95),
            "abs_usd_mean": statistics.fmean(usds),
            "abs_pts_p50": pct([r["abs_pts"] for r in items], 50),
        }

    enter_rows = [r for r in rows if r["is_enter_cycle"]]
    enter_by_root = {
        root: summarize([r for r in enter_rows if r["root"] == root])
        for root in sorted({r["root"] for r in enter_rows})
    }
    by_root = {
        root: summarize([r for r in rows if r["root"] == root])
        for root in sorted({r["root"] for r in rows})
    }
    return {
        "hash": CURRENT_HASH,
        "all_decision_instrument_rows": summarize(rows),
        "by_root": by_root,
        "enter_cycles_instrument_rows": summarize(enter_rows),
        "enter_by_root": enter_by_root,
        "mnq_enter_abs_usd_p50": (enter_by_root.get("MNQ") or {}).get("abs_usd_p50"),
        "note": (
            "Drift uses packet prices at started_utc vs completed_utc via temporal join; "
            "1m packets understate intraminute move when attempt finishes in same minute."
        ),
    }


def _parse_breakeven(evidence: str, entry: float, stop: float, target: float) -> float | None:
    risk_pts = abs(entry - stop)
    reward = abs(target - entry)
    fallback = risk_pts / (risk_pts + reward) if risk_pts + reward > 0 else None
    match = re.search(r"(?mi)^SELECTION_EV\s*=\s*(.+?)\s*$", evidence)
    if not match:
        return fallback
    fields = dict(part.split("=", 1) for part in match.group(1).split(";") if "=" in part)
    declared = number(fields.get("breakeven_target_first"))
    return declared if declared is not None else fallback


def audit_selection(ev: Any) -> dict[str, Any]:
    path = SUP / "decision-episodes.jsonl"
    if not path.is_file():
        return {"error": "decision_episodes_missing"}

    def collect(require_current_hash: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                action = str(row.get("action") or "")
                if action not in {"ENTER_LONG", "ENTER_SHORT"}:
                    continue
                row_hash = str(row.get("cognitive_bundle_hash") or "")
                if require_current_hash and row_hash and row_hash != CURRENT_HASH:
                    continue
                if require_current_hash and not row_hash:
                    continue
                geometry = ev.geometry_from_decisive_evidence(row)
                direction = str(geometry.get("direction") or "").upper()
                entry = number(geometry.get("entry"))
                stop = number(geometry.get("stop"))
                target = number(geometry.get("target"))
                if direction not in {"LONG", "SHORT"} or None in (entry, stop, target):
                    continue
                assert entry is not None and stop is not None and target is not None
                bars = [bar for bar in row.get("forward_observations", []) if isinstance(bar, dict)]
                chronology = ev.first_touch(direction, stop, target, bars)
                if chronology not in {"target_before_stop", "stop_before_target"}:
                    continue
                risk_pts = abs(entry - stop)
                root = ev.instrument_root(row.get("instrument"))
                audit = row.get("decision_audit") if isinstance(row.get("decision_audit"), dict) else {}
                evidence = str((audit or {}).get("decisive_evidence") or row.get("decisive_evidence") or "")
                breakeven = _parse_breakeven(evidence, entry, stop, target)
                out.append({
                    "episode_id": row.get("episode_id"),
                    "instrument": root,
                    "action": action,
                    "chronology": chronology,
                    "target_first": chronology == "target_before_stop",
                    "stop_first": chronology == "stop_before_target",
                    "risk_usd": risk_pts * POINT_VALUE.get(root, 0.0),
                    "breakeven_target_first": breakeven,
                    "cognitive_bundle_hash": row_hash,
                })
        return out

    rows = collect(True)
    scope = "current_hash"
    if len(rows) < 10:
        rows = collect(False)
        scope = "all_hashes_fallback"

    n = len(rows)
    target_first_n = sum(1 for r in rows if r["target_first"])
    observed = target_first_n / n if n else None
    be_vals = [r["breakeven_target_first"] for r in rows if r.get("breakeven_target_first") is not None]
    mean_be = statistics.fmean(be_vals) if be_vals else None
    gap = (mean_be - observed) if mean_be is not None and observed is not None else None
    mean_risk = statistics.fmean([r["risk_usd"] for r in rows]) if rows else None
    implied_usd = (gap * mean_risk) if gap is not None and mean_risk is not None else None
    obs_upper = None
    if n and observed is not None:
        obs_upper = 1.0 - (wilson_lower(n - target_first_n, n) or 0.0)
    gap_lower = (mean_be - obs_upper) if mean_be is not None and obs_upper is not None else None

    by_instrument = {}
    for root in sorted({r["instrument"] for r in rows}):
        items = [r for r in rows if r["instrument"] == root]
        be_i = [r["breakeven_target_first"] for r in items if r.get("breakeven_target_first") is not None]
        by_instrument[root] = {
            "n": len(items),
            "target_first": round(sum(1 for r in items if r["target_first"]) / len(items), 4),
            "mean_breakeven": round(statistics.fmean(be_i), 4) if be_i else None,
            "mean_risk_usd": round(statistics.fmean([r["risk_usd"] for r in items]), 2),
        }

    return {
        "n_resolved_enters": n,
        "scope_note": scope,
        "observed_target_first": round(observed, 4) if observed is not None else None,
        "observed_stop_first": round(1 - observed, 4) if observed is not None else None,
        "mean_breakeven_target_first": round(mean_be, 4) if mean_be is not None else None,
        "gap_breakeven_minus_observed": round(gap, 4) if gap is not None else None,
        "mean_risk_usd": round(mean_risk, 2) if mean_risk is not None else None,
        "implied_gap_usd_per_enter": round(implied_usd, 2) if implied_usd is not None else None,
        "gap_lower_approx": round(gap_lower, 4) if gap_lower is not None else None,
        "by_instrument": by_instrument,
    }


def apply_gate(size: dict[str, Any], drift: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    reg = size.get("regression_prompt_chars") or {}
    reg_sr = size.get("regression_session_rows_chars") or {}
    r2 = reg.get("r2")
    r2_sr = reg_sr.get("r2")
    candidates = [x for x in (r2, r2_sr) if x is not None]
    best_r2 = max(candidates) if candidates else None
    ratio = reg.get("fat_over_thin_elapsed_p50_ratio")

    if best_r2 is not None and best_r2 >= R2_STRONG:
        size_signal = "strong"
    elif (
        best_r2 is not None
        and R2_WEAK <= best_r2 < R2_STRONG
        and ratio is not None
        and ratio >= QUINTILE_RATIO
    ):
        size_signal = "borderline_strong"
    elif best_r2 is None or best_r2 < R2_WEAK:
        size_signal = "weak"
    else:
        size_signal = "inconclusive"

    mnq_enter = drift.get("mnq_enter_abs_usd_p50")
    mean_risk = selection.get("mean_risk_usd")
    if mnq_enter is None:
        drift_signal = "inconclusive"
    elif mnq_enter >= DRIFT_EXPENSIVE_USD:
        drift_signal = "expensive"
    elif mnq_enter < DRIFT_CHEAP_USD:
        drift_signal = "cheap"
    elif mean_risk and mean_risk > 0 and mnq_enter / mean_risk < DRIFT_REL_CHEAP:
        drift_signal = "cheap"
    else:
        drift_signal = "inconclusive"

    gap = selection.get("gap_breakeven_minus_observed")
    implied = selection.get("implied_gap_usd_per_enter")
    n_sel = selection.get("n_resolved_enters") or 0
    gap_lower = selection.get("gap_lower_approx")
    if gap is not None and gap <= 0:
        selection_signal = "not_below_breakeven"
    elif gap is not None and gap > 0:
        if n_sel >= MIN_RESOLVED_FOR_SELECTION or (
            gap_lower is not None and gap_lower > GAP_IC_MIN_PP
        ):
            selection_signal = "below_breakeven"
        else:
            selection_signal = "inconclusive_small_n"
    else:
        selection_signal = "inconclusive"

    decision = "C"
    reasons: list[str] = []
    drift_usd = mnq_enter

    if selection_signal == "below_breakeven" and implied is not None and drift_usd is not None:
        if implied > drift_usd and size_signal in {"weak", "inconclusive"}:
            decision = "B"
            reasons.append(
                f"selection implied USD/enter {implied} > MNQ enter drift p50 {drift_usd}; "
                f"size signal {size_signal}"
            )
    if decision == "C" and size_signal in {"strong", "borderline_strong"} and drift_signal != "cheap":
        if selection_signal != "below_breakeven" or (
            implied is not None and drift_usd is not None and implied <= drift_usd
        ):
            decision = "A"
            reasons.append(
                f"size/latency signal {size_signal} (best_r2={best_r2}, quintile_ratio={ratio}); "
                f"drift {drift_signal}"
            )
    if decision == "C":
        reasons.append(
            f"default accumulate: size={size_signal} best_r2={best_r2} ratio={ratio}; "
            f"drift={drift_signal} mnq_enter_p50={drift_usd}; selection={selection_signal} "
            f"implied={implied}"
        )

    step1_needed = False
    if decision == "A" and size_signal == "weak":
        step1_needed = True
        step1_reason = "latency_expensive_but_size_weak_need_output_token_telemetry"
    elif decision in {"A", "B"}:
        step1_reason = "not_required_2a_sufficient_for_next_freeze_break_decision"
    else:
        step1_reason = "gate_C_no_hot_path_change"

    return {
        "thresholds": {
            "r2_weak": R2_WEAK,
            "r2_strong": R2_STRONG,
            "quintile_ratio": QUINTILE_RATIO,
            "drift_cheap_usd": DRIFT_CHEAP_USD,
            "drift_expensive_usd": DRIFT_EXPENSIVE_USD,
            "min_resolved_enters": MIN_RESOLVED_FOR_SELECTION,
            "gap_ic_min_pp": GAP_IC_MIN_PP,
        },
        "signals": {
            "size_latency": size_signal,
            "best_r2": best_r2,
            "prompt_r2": r2,
            "session_rows_r2": r2_sr,
            "fat_over_thin_ratio": ratio,
            "drift": drift_signal,
            "mnq_enter_drift_usd_p50": drift_usd,
            "selection": selection_signal,
            "implied_gap_usd_per_enter": implied,
        },
        "decision": decision,
        "decision_labels": {
            "A": "attack_latency_or_size_next",
            "B": "attack_enter_selection_next",
            "C": "accumulate_N_and_eval_only",
        },
        "reasons": reasons,
        "step1_instrumentation_needed": step1_needed,
        "step1_reason": step1_reason,
        "step4_eval_hash": CURRENT_HASH if not step1_needed else "new_hash_after_instrumentation",
    }


def render_md(report: dict[str, Any]) -> str:
    g = report["gate"]
    s = report["size_latency"]
    d = report["drift"]
    sel = report["selection"]
    p0 = report["paso0"]
    lines = [
        "# Relatório 2a — prompt size × latência × deriva × seleção",
        "",
        f"Gerado: {report['generated_utc']}",
        "",
        "## Passo 0 (diff only)",
        "",
        f"- Scripts do bundle (exceto SOUL): **{'OK' if p0['all_scripts_match'] else 'DIVERGEM'}**",
        f"- SOUL: **{p0['soul_direction']}** — {p0['soul_detail']}",
        "- Sync: **não feita**",
        "",
        "## Tamanho e latência",
        "",
        f"- Rows OK: {s['rows_ok']} (hash atual {s['rows_current_hash']}, foco `{s['focus']}` n={s['focus_n']})",
        f"- prompt_chars p50: {s['size_summary_focus'].get('prompt_chars_p50')}",
        f"- session_rows chars p50: {s['size_summary_focus'].get('session_rows_chars_p50')} "
        f"(share p50 {s['size_summary_focus'].get('session_rows_share_p50')})",
        f"- R² elapsed~prompt_chars: {(s.get('regression_prompt_chars') or {}).get('r2')}",
        f"- R² elapsed~session_rows: {(s.get('regression_session_rows_chars') or {}).get('r2')}",
        f"- Quintil gordo/magro elapsed p50: "
        f"{(s.get('regression_prompt_chars') or {}).get('fat_over_thin_elapsed_p50_ratio')}",
        "- Rebuild omissions: market_perception full + chart image + exact historical journals",
        "",
        "## Deriva decisão→fim (hash atual)",
        "",
        f"- MNQ ENTER abs USD p50: {d.get('mnq_enter_abs_usd_p50')}",
        f"- ENTER by root: `{json.dumps(d.get('enter_by_root'), ensure_ascii=True)}`",
        f"- Nota: {d.get('note')}",
        "",
        "## Seleção ENTER vs breakeven",
        "",
        f"- n resolvidos: {sel.get('n_resolved_enters')} ({sel.get('scope_note')})",
        f"- observed target_first: {sel.get('observed_target_first')} "
        f"(stop_first {sel.get('observed_stop_first')})",
        f"- mean breakeven_target_first: {sel.get('mean_breakeven_target_first')}",
        f"- gap (breakeven − observed): {sel.get('gap_breakeven_minus_observed')}",
        f"- implied USD/ENTER: {sel.get('implied_gap_usd_per_enter')} "
        f"(mean risk ${sel.get('mean_risk_usd')})",
        f"- gap_lower_approx: {sel.get('gap_lower_approx')}",
        "",
        "## Gate (limiares pré-declarados)",
        "",
        f"- **Decisão: {g['decision']}** — {g['decision_labels'].get(g['decision'])}",
        f"- Sinais: `{json.dumps(g['signals'], ensure_ascii=True)}`",
        f"- Passo 1 necessário: **{g['step1_instrumentation_needed']}** ({g['step1_reason']})",
        f"- Passo 4 eval hash: `{g['step4_eval_hash']}`",
        "",
    ]
    for reason in g.get("reasons") or []:
        lines.append(f"- Motivo: {reason}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("loading modules...", flush=True)
    direct = load_direct()
    ev = load_eval()
    if not hasattr(ev, "deterministic_selection_math"):
        ev.deterministic_selection_math = direct.deterministic_selection_math

    print("paso0...", flush=True)
    paso0 = paso0_parity()
    print("size/latency rebuild (slow)...", flush=True)
    size = audit_size_latency(direct)
    print("drift...", flush=True)
    drift = audit_drift()
    print("selection...", flush=True)
    selection = audit_selection(ev)
    print("gate...", flush=True)
    gate = apply_gate(size, drift, selection)
    report = {
        "schema_version": "glitch.hermes.research.prompt_size_latency_drift.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "current_hash": CURRENT_HASH,
        "paso0": paso0,
        "size_latency": size,
        "drift": drift,
        "selection": selection,
        "gate": gate,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_md(report), encoding="utf-8")
    print(OUT_MD)
    print(OUT_JSON)
    print("GATE", gate["decision"], "step1", gate["step1_instrumentation_needed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
