"""Offline-only, reversible prompt representation and paired research arms."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

VERSION = "hermes-briefing-research-v1"
ARMS = ("current", "guided", "compact_jev", "compact_without_jev")
GUIDANCE_PATH = Path(__file__).parent / "skills/interpret-jev/SKILL.md"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def split_prompt(prompt):
    prefix, marker, rest = prompt.partition("CURRENT_CYCLE=")
    if not marker:
        raise ValueError("missing_cycle_envelope")
    envelope, end = json.JSONDecoder().raw_decode(rest)
    if not isinstance(envelope, dict) or not envelope.get("decision_packet"):
        raise ValueError("invalid_cycle_envelope")
    return prefix, envelope, rest[end:]


def flatten(value, path=()):
    if isinstance(value, dict) and value:
        for key, cell in value.items():
            yield from flatten(cell, (*path, key))
    else:
        yield path, value


def expand(columns, row):
    if len(columns) != len(row):
        raise ValueError("table_width")
    value = {}
    for path, cell in zip(columns, row):
        if not path or not all(isinstance(k, str) for k in path):
            raise ValueError("table_path")
        target = value
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = copy.deepcopy(cell)
    return value


def compact(envelope):
    """Share repeated field names; retain every value, timestamp and missing-data marker."""
    result = copy.deepcopy(envelope)
    packet = result["decision_packet"]
    if "timeframe_evidence_tables" in packet:
        raise ValueError("already_compact")
    tables, schemas = [], {}
    for frame in packet.get("frames", []):
        for instrument in frame.get("market_snapshot", {}).get("instruments", []):
            bars = instrument.get("timeframe_bars")
            if not isinstance(bars, list):
                raise ValueError("unsupported_bar_shape")
            refs = []
            for bar in bars:
                if not isinstance(bar, dict) or not bar:
                    raise ValueError("unsupported_bar")
                cells = list(flatten(bar)); columns = tuple(path for path, _ in cells)
                if columns not in schemas:
                    schemas[columns] = len(tables)
                    tables.append({"columns": columns, "rows": []})
                index = schemas[columns]; table = tables[index]
                refs.append([index, len(table["rows"])])
                table["rows"].append([value for _, value in cells])
            instrument["timeframe_bars"] = {"evidence_rows": refs}
    packet["timeframe_evidence_tables"] = tables
    # First show the interpretation; the native facts remain independently available.
    return {"jev_evidence": result.pop("jev_evidence"), **result} if "jev_evidence" in result else result


def restore(envelope):
    result = copy.deepcopy(envelope); packet = result["decision_packet"]
    tables = packet.pop("timeframe_evidence_tables")
    for frame in packet["frames"]:
        for instrument in frame["market_snapshot"]["instruments"]:
            instrument["timeframe_bars"] = [expand(tables[t]["columns"], tables[t]["rows"][r])
                for t, r in instrument["timeframe_bars"]["evidence_rows"]]
    return result


def variant(prompt, arm, guidance=None):
    if arm not in ARMS:
        raise ValueError("unknown_arm")
    if arm == "current":
        return prompt
    prefix, envelope, suffix = split_prompt(prompt)
    guidance = GUIDANCE_PATH.read_text(encoding="utf-8") if guidance is None else guidance
    prefix += "\nRESEARCH_INTERPRETATION_GUIDANCE:\n" + guidance + "\n"
    if arm.startswith("compact"):
        original = copy.deepcopy(envelope)
        envelope = compact(envelope)
        if restore(envelope) != original:
            raise ValueError("non_reversible_briefing")
        prefix += (
            "COMPACT_EVIDENCE: Each instrument's timeframe_bars.evidence_rows contains [table,row] "
            "references into decision_packet.timeframe_evidence_tables. Columns are key paths within "
            "the original timeframe bar; row values align with those columns. This shares repeated field "
            "names without removing measurements. Preserve the original partial/completed-bar meanings. "
            "Use the Jev interpretation to focus the review, and consult these measurements for material "
            "agreement, contradictions and exact geometry. Current prices, economics, native position, "
            "protection, policy, prior thesis and the required output template remain unchanged.\n"
        )
    if arm == "compact_without_jev":
        envelope["jev_evidence"] = {"status": "unavailable", "reason": "offline_comparison_arm",
                                    "predictions": [], "included_request_ids": [], "effect": "advisory_only"}
    return prefix + "CURRENT_CYCLE=" + encoded(envelope) + suffix


def prepare_case(case):
    original = (case / "original-prompt.txt").read_text(encoding="utf-8")
    prefix, envelope, suffix = split_prompt(original)
    baseline = encoded(envelope)
    report = {"schema": VERSION, "original_prompt_sha256": sha(original), "arms": {},
              "guidance_sha256": sha(GUIDANCE_PATH.read_text(encoding="utf-8")),
              "original_envelope_chars": len(baseline), "values_omitted_by_compaction": 0,
              "protected_facts": "every original value retained; compact representation round-trips exactly"}
    destination = case / "variants"; destination.mkdir(exist_ok=False)
    for arm in ARMS:
        text = variant(original, arm)
        (destination / f"{arm}.txt").write_text(text, encoding="utf-8")
        _, body, _ = split_prompt(text)
        report["arms"][arm] = {"prompt_sha256": sha(text), "prompt_chars": len(text),
                              "envelope_chars": len(encoded(body)),
                              "jev_available": (body.get("jev_evidence") or {}).get("status") == "available"}
    (case / "comparison-manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
