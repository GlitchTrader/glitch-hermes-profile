"""Score superseded ENTER decisions: first-touch, escape direction, calibration.

Read-only. Uses decision-episodes.jsonl (278 entry_range_superseded) and each
row's forward_observations when present.
"""
from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE = Path(r"C:\Users\arifr\Projects\glitch-hermes-profile")
SCRIPTS = PROFILE / "scripts"
GD = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
SUP = GD / "hermes" / "exchange" / "hermes" / "supervisor"
DE = SUP / "decision-episodes.jsonl"
OUT_JSON = PROFILE / "research" / "report-superseded-enters.json"
OUT_MD = PROFILE / "research" / "report-superseded-enters.md"

POINT_VALUE = {"MES": 5.0, "MNQ": 2.0, "M2K": 5.0}

sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("evalcog", SCRIPTS / "evaluate-frozen-cognition.py")
ev = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ev)


def number(value: Any) -> float | None:
    return ev.number(value)


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


def declared_probability(row: dict[str, Any]) -> float | None:
    forecast = row.get("forecast")
    if isinstance(forecast, dict):
        # STOP_BEFORE_PRIMARY_TARGET → target-first = 1 - p
        event = str(forecast.get("event") or "")
        p = number(forecast.get("probability"))
        if p is None:
            return None
        if "STOP_BEFORE" in event.upper():
            return 1.0 - p
        return p
    audit = row.get("decision_audit") if isinstance(row.get("decision_audit"), dict) else {}
    text = str((audit or {}).get("decisive_evidence") or "")
    import re
    match = re.search(
        r"(?mi)^SELECTION_EV\s*=\s*.*?estimated_target_first_range=([^;]+)",
        text,
    )
    if not match:
        return None
    raw = match.group(1).strip()
    # ranges like 0.46-0.52 or single 0.55
    parts = [number(x) for x in raw.replace("%", "").split("-")]
    parts = [x for x in parts if x is not None]
    if not parts:
        return None
    vals = [x / 100.0 if x > 1 else x for x in parts]
    return statistics.fmean(vals)


def escape_direction(
    direction: str, decision_price: float, bars: list[dict[str, Any]]
) -> str:
    """Did price leave the decision area with or against the thesis first?"""
    if not bars:
        return "unknown"
    # first bar that moves materially from decision price
    for bar in bars[:12]:
        high = number(bar.get("high"))
        low = number(bar.get("low"))
        if high is None or low is None:
            continue
        up = high - decision_price
        down = decision_price - low
        if up <= 0 and down <= 0:
            continue
        if direction == "LONG":
            if up > down:
                return "with_thesis"
            if down > up:
                return "against_thesis"
        else:
            if down > up:
                return "with_thesis"
            if up > down:
                return "against_thesis"
    # fallback: end of window vs decision
    last = bars[-1]
    close = number(last.get("close")) or number(last.get("high"))
    if close is None:
        return "unknown"
    if direction == "LONG":
        return "with_thesis" if close > decision_price else (
            "against_thesis" if close < decision_price else "flat"
        )
    return "with_thesis" if close < decision_price else (
        "against_thesis" if close > decision_price else "flat"
    )


def main() -> int:
    rows: list[dict[str, Any]] = []
    codes = Counter()
    with DE.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            action = str(row.get("action") or "")
            if action not in {"ENTER_LONG", "ENTER_SHORT"}:
                continue
            blob = json.dumps(row)
            if "entry_range_superseded" not in blob:
                codes["not_superseded"] += 1
                continue
            codes["entry_range_superseded"] += 1
            geometry = ev.geometry_from_decisive_evidence(row)
            direction = str(geometry.get("direction") or "").upper()
            entry = number(geometry.get("entry"))
            stop = number(geometry.get("stop"))
            target = number(geometry.get("target"))
            if direction not in {"LONG", "SHORT"} or None in (entry, stop, target):
                codes["no_geometry"] += 1
                continue
            assert entry is not None and stop is not None and target is not None
            bars = [b for b in row.get("forward_observations", []) if isinstance(b, dict)]
            chronology = ev.first_touch(direction, stop, target, bars)
            decision_price = entry
            # prefer explicit decision reference if present
            for key in ("decision_reference_price", "current_price", "mark_price"):
                n = number(row.get(key))
                if n is not None:
                    decision_price = n
                    break
            escape = escape_direction(direction, decision_price, bars)
            p_hat = declared_probability(row)
            root = ev.instrument_root(row.get("instrument"))
            risk_usd = abs(entry - stop) * POINT_VALUE.get(root, 0.0)
            reward_usd = abs(target - entry) * POINT_VALUE.get(root, 0.0)
            rows.append({
                "episode_id": row.get("episode_id"),
                "instrument": root,
                "action": action,
                "direction": direction,
                "chronology": chronology,
                "escape": escape,
                "declared_target_first_p": p_hat,
                "risk_usd": risk_usd,
                "reward_usd": reward_usd,
                "forward_bars": len(bars),
                "prompt_version": row.get("prompt_version"),
                "cognitive_bundle_hash": row.get("cognitive_bundle_hash"),
            })

    resolved = [
        r for r in rows
        if r["chronology"] in {"target_before_stop", "stop_before_target"}
    ]
    target_n = sum(1 for r in resolved if r["chronology"] == "target_before_stop")
    observed = target_n / len(resolved) if resolved else None

    escape_counts = Counter(r["escape"] for r in rows)
    chron_counts = Counter(r["chronology"] for r in rows)

    # calibration buckets by declared p
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resolved:
        p = r.get("declared_target_first_p")
        if p is None:
            buckets["unknown_p"].append(r)
            continue
        if p < 0.4:
            buckets["p_lt_0.40"].append(r)
        elif p < 0.5:
            buckets["p_0.40_0.50"].append(r)
        elif p < 0.6:
            buckets["p_0.50_0.60"].append(r)
        else:
            buckets["p_ge_0.60"].append(r)

    def bucket_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"n": 0}
        tf = sum(1 for r in items if r["chronology"] == "target_before_stop")
        declared = [r["declared_target_first_p"] for r in items if r.get("declared_target_first_p") is not None]
        return {
            "n": len(items),
            "observed_target_first": round(tf / len(items), 4),
            "mean_declared_p": round(statistics.fmean(declared), 4) if declared else None,
            "with_thesis_escape_share": round(
                sum(1 for r in items if r["escape"] == "with_thesis") / len(items), 4
            ),
        }

    # economic reading: with_thesis escapes that later target_first = missed good entries
    missed_good = [
        r for r in resolved
        if r["escape"] == "with_thesis" and r["chronology"] == "target_before_stop"
    ]
    correct_cancel = [
        r for r in resolved
        if r["escape"] == "against_thesis" and r["chronology"] == "stop_before_target"
    ]

    report = {
        "schema_version": "glitch.hermes.research.superseded_enters.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "codes": dict(codes),
        "n_scored": len(rows),
        "n_resolved": len(resolved),
        "chronology": dict(chron_counts),
        "escape": dict(escape_counts),
        "observed_target_first_among_resolved": (
            round(observed, 4) if observed is not None else None
        ),
        "calibration_buckets": {k: bucket_stats(v) for k, v in sorted(buckets.items())},
        "missed_good_n": len(missed_good),
        "missed_good_share_of_resolved": (
            round(len(missed_good) / len(resolved), 4) if resolved else None
        ),
        "correct_cancel_n": len(correct_cancel),
        "correct_cancel_share_of_resolved": (
            round(len(correct_cancel) / len(resolved), 4) if resolved else None
        ),
        "by_instrument": {
            root: {
                "n": len(items),
                "resolved": len([r for r in items if r["chronology"] in {"target_before_stop", "stop_before_target"}]),
                "escape": dict(Counter(r["escape"] for r in items)),
                "chronology": dict(Counter(r["chronology"] for r in items)),
            }
            for root, items in (
                (k, [r for r in rows if r["instrument"] == k])
                for k in sorted({r["instrument"] for r in rows})
            )
        },
        "interpretation": {
            "if_missed_good_dominates": "execution_path_entry_range_or_latency",
            "if_correct_cancel_dominates": "revalidation_protecting_ev",
            "if_declared_p_miscalibrated": "prompt_or_probability_process",
        },
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Superseded ENTER scorecard",
        "",
        f"Gerado: {report['generated_utc']}",
        "",
        f"- Scored: {report['n_scored']} (codes `{report['codes']}`)",
        f"- Resolved first-touch: {report['n_resolved']}",
        f"- Observed target-first (resolved): {report['observed_target_first_among_resolved']}",
        f"- Escape: `{json.dumps(report['escape'])}`",
        f"- Chronology: `{json.dumps(report['chronology'])}`",
        f"- Missed good (with_thesis + target_first): {report['missed_good_n']} "
        f"({report['missed_good_share_of_resolved']})",
        f"- Correct cancel (against_thesis + stop_first): {report['correct_cancel_n']} "
        f"({report['correct_cancel_share_of_resolved']})",
        "",
        "## Calibration buckets",
        "",
    ]
    for name, stats in report["calibration_buckets"].items():
        lines.append(f"- `{name}`: {json.dumps(stats)}")
    lines.append("")
    lines.append("## By instrument")
    lines.append("")
    for root, stats in report["by_instrument"].items():
        lines.append(f"- **{root}**: {json.dumps(stats)}")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_MD)
    print(OUT_JSON)
    print(
        "missed_good", report["missed_good_share_of_resolved"],
        "correct_cancel", report["correct_cancel_share_of_resolved"],
        "obs_tf", report["observed_target_first_among_resolved"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
