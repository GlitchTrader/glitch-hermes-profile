"""Score NOTHING decisions with authored geometry + wait_price touch rates.

Read-only. Answers the auditor EV question: when Luna abstains / waits,
how often would NOW geometry have been target-first, and how often did
wait_price actually print in the forward window.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
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
OUT_JSON = PROFILE / "research" / "report-nothing-waits.json"
OUT_MD = PROFILE / "research" / "report-nothing-waits.md"

POINT_VALUE = {"MES": 5.0, "MNQ": 2.0, "M2K": 5.0}

sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("evalcog", SCRIPTS / "evaluate-frozen-cognition.py")
ev = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ev)


def number(value: Any) -> float | None:
    return ev.number(value)


def parse_selection_ev_line(text: str) -> dict[str, str]:
    match = re.search(r"(?mi)^SELECTION_EV\s*=\s*(.+?)\s*$", text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for component in match.group(1).split(";"):
        key, separator, value = component.partition("=")
        if separator:
            fields[key.strip().lower()] = value.strip()
    return fields


def declared_probability(row: dict[str, Any], fields: dict[str, str]) -> float | None:
    sel = ev.selection_audit(row)
    pr = ev.probability_range(sel)
    if pr:
        return statistics.fmean(pr)
    raw = fields.get("estimated_target_first_range") or ""
    parts = [number(x) for x in raw.replace("%", "").split("-")]
    parts = [x for x in parts if x is not None]
    if not parts:
        return None
    vals = [x / 100.0 if x > 1 else x for x in parts]
    return statistics.fmean(vals)


def wait_levels(wait_price: str, entry: float | None = None) -> list[float]:
    """Extract numeric wait levels from free-text wait_price.

    Drops tokens that are not prices and levels stuck to the decision entry
    (those inflate touch rate because the first bar almost always covers them).
    """
    if not wait_price:
        return []
    levels: list[float] = []
    for match in re.finditer(r"\d+(?:\.\d+)?", wait_price):
        n = number(match.group(0))
        if n is None:
            continue
        # discard tiny tokens that are not prices (e.g. 0.25 spread)
        if n < 100:
            continue
        if entry is not None and abs(n - entry) < 1.0:
            continue
        levels.append(n)
    # unique, preserve order
    seen: set[float] = set()
    out: list[float] = []
    for n in levels:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out[:4]


def wait_touched(
    direction: str, levels: list[float], bars: list[dict[str, Any]]
) -> str:
    if not levels or not bars:
        return "unknown"
    for bar in bars:
        high = number(bar.get("high"))
        low = number(bar.get("low"))
        if high is None or low is None:
            continue
        for level in levels:
            if low <= level <= high:
                return "touched"
    return "not_touched"


def wait_before_stop(
    direction: str,
    levels: list[float],
    stop: float,
    bars: list[dict[str, Any]],
) -> str:
    """Did any wait level print before stop in the forward window?"""
    if not levels or not bars:
        return "unknown"
    for bar in bars:
        high = number(bar.get("high"))
        low = number(bar.get("low"))
        if high is None or low is None:
            continue
        stop_hit = low <= stop if direction == "LONG" else high >= stop
        wait_hit = any(low <= level <= high for level in levels)
        if wait_hit and stop_hit:
            return "ambiguous_same_bar"
        if wait_hit:
            return "wait_before_stop"
        if stop_hit:
            return "stop_before_wait"
    return "neither"


def main() -> int:
    codes: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    with DE.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get("action") or "") != "NOTHING":
                continue
            codes["nothing"] += 1
            audit = row.get("decision_audit") if isinstance(row.get("decision_audit"), dict) else {}
            text = str(audit.get("decisive_evidence") or "")
            fields = parse_selection_ev_line(text)
            geometry = ev.geometry_from_decisive_evidence(row)
            direction = str(geometry.get("direction") or "").upper()
            entry = number(geometry.get("entry"))
            stop = number(geometry.get("stop"))
            target = number(geometry.get("target"))
            if direction not in {"LONG", "SHORT"} or None in (entry, stop, target):
                codes["no_authored_geometry"] += 1
                continue
            assert entry is not None and stop is not None and target is not None
            codes["authored_geometry"] += 1
            bars = [b for b in row.get("forward_observations", []) if isinstance(b, dict)]
            chronology = ev.first_touch(direction, stop, target, bars)
            p_hat = declared_probability(row, fields)
            root = ev.instrument_root(row.get("instrument"))
            levels = wait_levels(fields.get("wait_price") or "", entry=entry)
            wait_touch = wait_touched(direction, levels, bars)
            wait_seq = wait_before_stop(direction, levels, stop, bars)
            now_ev_label = (fields.get("now_ev") or "").strip().upper()
            wait_ev = (fields.get("wait_ev") or "").strip()
            wait_improved = bool(re.search(r"(?i)\bIMPROVED\b|potentially improved", wait_ev))
            rows.append(
                {
                    "episode_id": row.get("episode_id"),
                    "instrument": root,
                    "direction": direction,
                    "chronology": chronology,
                    "declared_target_first_p": p_hat,
                    "forward_bars": len(bars),
                    "wait_levels_n": len(levels),
                    "wait_touched": wait_touch if levels else "no_distant_level",
                    "wait_vs_stop": wait_seq if levels else "no_distant_level",
                    "now_ev_label": now_ev_label or None,
                    "wait_improved_claimed": wait_improved,
                    "risk_usd": abs(entry - stop) * POINT_VALUE.get(root, 0.0),
                    "reward_usd": abs(target - entry) * POINT_VALUE.get(root, 0.0),
                    "prompt_version": row.get("prompt_version"),
                    "cognitive_bundle_hash": row.get("cognitive_bundle_hash"),
                }
            )

    resolved = [
        r
        for r in rows
        if r["chronology"] in {"target_before_stop", "stop_before_target"}
    ]
    target_n = sum(1 for r in resolved if r["chronology"] == "target_before_stop")
    observed = target_n / len(resolved) if resolved else None

    # Economic reading for abstention:
    # missed_good = abstained but NOW geometry would have been target-first
    # correct_abstention = abstained and stop would have hit first
    missed_good = [r for r in resolved if r["chronology"] == "target_before_stop"]
    correct_abstention = [r for r in resolved if r["chronology"] == "stop_before_target"]

    with_wait = [r for r in rows if r["wait_levels_n"] > 0]
    wait_resolved_touch = [r for r in with_wait if r["wait_touched"] in {"touched", "not_touched"}]
    wait_touch_rate = (
        sum(1 for r in wait_resolved_touch if r["wait_touched"] == "touched")
        / len(wait_resolved_touch)
        if wait_resolved_touch
        else None
    )
    wait_before = [r for r in with_wait if r["wait_vs_stop"] == "wait_before_stop"]
    stop_before_wait = [r for r in with_wait if r["wait_vs_stop"] == "stop_before_wait"]

    # Among claimed IMPROVED waits: did wait level print?
    claimed = [r for r in with_wait if r["wait_improved_claimed"]]
    claimed_touch = (
        sum(1 for r in claimed if r["wait_touched"] == "touched") / len(claimed)
        if claimed
        else None
    )
    # Missed good where WAIT also failed to print → pure abstention cost
    missed_and_wait_missed = [
        r
        for r in missed_good
        if r["wait_touched"] == "not_touched"
    ]
    missed_and_wait_filled = [
        r for r in missed_good if r["wait_touched"] == "touched"
    ]

    # Calibration buckets on counterfactual NOW geometry
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in resolved:
        p = r.get("declared_target_first_p")
        if p is None:
            buckets["unknown_p"].append(r)
        elif p < 0.4:
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
        declared = [
            r["declared_target_first_p"]
            for r in items
            if r.get("declared_target_first_p") is not None
        ]
        return {
            "n": len(items),
            "observed_target_first": round(tf / len(items), 4),
            "mean_declared_p": round(statistics.fmean(declared), 4) if declared else None,
        }

    # Auditor-style: when declared NOW EV > 0, did abstaining leave +EV on table?
    positive_now = []
    for r in rows:
        p = r.get("declared_target_first_p")
        risk = r.get("risk_usd")
        reward = r.get("reward_usd")
        if p is None or not risk or not reward:
            continue
        now_ev = p * reward - (1 - p) * risk
        if now_ev <= 0:
            continue
        positive_now.append(
            {
                "now_ev": now_ev,
                "chronology": r["chronology"],
                "wait_touched": r["wait_touched"],
                "target_first": r["chronology"] == "target_before_stop",
                "stop_first": r["chronology"] == "stop_before_target",
            }
        )
    pos_resolved = [
        a
        for a in positive_now
        if a["chronology"] in {"target_before_stop", "stop_before_target"}
    ]
    pos_tf = (
        sum(1 for a in pos_resolved if a["target_first"]) / len(pos_resolved)
        if pos_resolved
        else None
    )
    wait_fail_among_pos = [
        a for a in positive_now if a["wait_touched"] == "not_touched"
    ]

    report = {
        "schema_version": "glitch.hermes.research.nothing_waits.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "codes": dict(codes),
        "n_scored": len(rows),
        "n_resolved_now_geometry": len(resolved),
        "chronology": dict(Counter(r["chronology"] for r in rows)),
        "observed_target_first_among_resolved": (
            round(observed, 4) if observed is not None else None
        ),
        "missed_good_n": len(missed_good),
        "missed_good_share_of_resolved": (
            round(len(missed_good) / len(resolved), 4) if resolved else None
        ),
        "correct_abstention_n": len(correct_abstention),
        "correct_abstention_share_of_resolved": (
            round(len(correct_abstention) / len(resolved), 4) if resolved else None
        ),
        "wait": {
            "with_distant_parsed_levels": len(with_wait),
            "no_distant_level_n": sum(1 for r in rows if r["wait_levels_n"] == 0),
            "touch_rate": round(wait_touch_rate, 4) if wait_touch_rate is not None else None,
            "wait_before_stop_n": len(wait_before),
            "stop_before_wait_n": len(stop_before_wait),
            "claimed_improved_n": len(claimed),
            "claimed_improved_touch_rate": (
                round(claimed_touch, 4) if claimed_touch is not None else None
            ),
            "wait_vs_stop": dict(Counter(r["wait_vs_stop"] for r in with_wait)),
            "missed_good_and_wait_missed_n": len(missed_and_wait_missed),
            "missed_good_and_wait_filled_n": len(missed_and_wait_filled),
        },
        "calibration_buckets": {k: bucket_stats(v) for k, v in sorted(buckets.items())},
        "auditor_ev_proxy": {
            "declared_positive_now_ev_n": len(positive_now),
            "declared_positive_now_resolved_n": len(pos_resolved),
            "observed_target_first_when_declared_positive_now": (
                round(pos_tf, 4) if pos_tf is not None else None
            ),
            "wait_fail_among_declared_positive_now_n": len(wait_fail_among_pos),
            "wait_fail_share_among_declared_positive_now": (
                round(len(wait_fail_among_pos) / len(positive_now), 4)
                if positive_now
                else None
            ),
            "note": (
                "Levels within 1.0 of entry dropped. Positive NOW EV uses declared p "
                "and authored R:R only; wait_fail means distant wait_price never printed."
            ),
        },
        "by_instrument": {
            root: {
                "n": len(items),
                "resolved": len(
                    [
                        r
                        for r in items
                        if r["chronology"] in {"target_before_stop", "stop_before_target"}
                    ]
                ),
                "chronology": dict(Counter(r["chronology"] for r in items)),
                "wait_touch": dict(Counter(r["wait_touched"] for r in items)),
            }
            for root, items in (
                (k, [r for r in rows if r["instrument"] == k])
                for k in sorted({r["instrument"] for r in rows})
            )
        },
        "interpretation": {
            "if_correct_abstention_dominates": "NOTHING protecting EV; prompt assertiveness secondary",
            "if_missed_good_dominates": "habitual abstention / WAIT overweighted vs NOW",
            "if_wait_touch_low": "WAIT fill probability too low for claimed IMPROVED EV",
            "if_declared_p_miscalibrated": "probability process, not only timing choice",
        },
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# NOTHING / WAIT scorecard",
        "",
        f"Gerado: {report['generated_utc']}",
        "",
        f"- NOTHING total: {codes.get('nothing')} | scored com geometria: {report['n_scored']} "
        f"| sem geometria: {codes.get('no_authored_geometry')}",
        f"- Resolved first-touch (NOW contrafactual): {report['n_resolved_now_geometry']}",
        f"- Observed target-first (resolved): {report['observed_target_first_among_resolved']}",
        f"- Chronology: `{json.dumps(report['chronology'])}`",
        f"- Missed good (absteve mas target_first): {report['missed_good_n']} "
        f"({report['missed_good_share_of_resolved']})",
        f"- Correct abstention (stop_first): {report['correct_abstention_n']} "
        f"({report['correct_abstention_share_of_resolved']})",
        "",
        "## WAIT fill (níveis a ≥1.0 do entry)",
        "",
        f"- Com wait_price distante: {report['wait']['with_distant_parsed_levels']} "
        f"(sem nível distante: {report['wait']['no_distant_level_n']})",
        f"- Touch rate (forward window): {report['wait']['touch_rate']}",
        f"- wait_before_stop / stop_before_wait: "
        f"{report['wait']['wait_before_stop_n']} / {report['wait']['stop_before_wait_n']}",
        f"- Claimed IMPROVED n={report['wait']['claimed_improved_n']}, "
        f"touch_rate={report['wait']['claimed_improved_touch_rate']}",
        f"- Missed good ∩ wait missed/filled: "
        f"{report['wait']['missed_good_and_wait_missed_n']} / "
        f"{report['wait']['missed_good_and_wait_filled_n']}",
        f"- wait_vs_stop: `{json.dumps(report['wait']['wait_vs_stop'])}`",
        "",
        "## Auditor EV proxy (declared positive NOW EV)",
        "",
        f"- Declared positive NOW EV: {report['auditor_ev_proxy']['declared_positive_now_ev_n']} "
        f"(resolved {report['auditor_ev_proxy']['declared_positive_now_resolved_n']})",
        f"- Observed target-first nesses: "
        f"{report['auditor_ev_proxy']['observed_target_first_when_declared_positive_now']}",
        f"- WAIT fail share entre positive NOW: "
        f"{report['auditor_ev_proxy']['wait_fail_share_among_declared_positive_now']} "
        f"(n={report['auditor_ev_proxy']['wait_fail_among_declared_positive_now_n']})",
        f"- Note: {report['auditor_ev_proxy']['note']}",
        "",
        "## Calibration buckets (NOW geometry)",
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
        "missed_good",
        report["missed_good_share_of_resolved"],
        "correct_abstention",
        report["correct_abstention_share_of_resolved"],
        "wait_touch",
        report["wait"]["touch_rate"],
        "pos_now_tf",
        report["auditor_ev_proxy"]["observed_target_first_when_declared_positive_now"],
        "wait_fail_pos",
        report["auditor_ev_proxy"]["wait_fail_share_among_declared_positive_now"],
        "obs_tf",
        report["observed_target_first_among_resolved"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
