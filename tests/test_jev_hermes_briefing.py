import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hermes_briefing", ROOT / "research/jev/hermes_briefing.py")
briefing = importlib.util.module_from_spec(spec); spec.loader.exec_module(briefing)


def envelope():
    bar = {"minutes": 1, "utc_time": "2026-09-21T03:24:33Z", "close": 100.25,
           "indicators": {"atr": 1.5, "vwap": None}, "empty": {}, "levels": [99, 102],
           "descriptive": {"quality": {"partial_1m": True}}}
    return {"decision_packet": {"packet_id": "cycle", "policy": {"limit": 3}, "frames": [{
        "market_snapshot": {"instruments": [{"instrument": "MNQ", "current_price": 100.25,
            "instrument_economics": {"tick_size": .25}, "timeframe_bars": [bar, dict(bar, minutes=5)]}]},
        "portfolio_snapshot": {"position": "long", "native_stop": 98.75}}]},
        "required_output_template": {"action": "HOLD"}, "prior_cognition": {"allowed_pullback": 99},
        "jev_evidence": {"status": "available", "predictions": [{"UP": .7, "DOWN": .3}]}}


def test_compaction_round_trips_all_native_facts_and_preserves_input():
    source = envelope(); before = copy.deepcopy(source)
    compact = briefing.compact(source)
    assert source == before and briefing.restore(compact) == before
    table = compact["decision_packet"]["timeframe_evidence_tables"][0]
    assert len(table["rows"]) == 2
    assert compact["decision_packet"]["frames"][0]["portfolio_snapshot"] == source["decision_packet"]["frames"][0]["portfolio_snapshot"]


def test_paired_arms_preserve_contract_and_isolate_jev_removal():
    source = envelope(); prompt = "original instructions\nCURRENT_CYCLE=" + json.dumps(source) + "\nOUTPUT_CLOSURE: original closure"
    assert briefing.variant(prompt, "current") == prompt
    _, a, tail = briefing.split_prompt(briefing.variant(prompt, "compact_jev"))
    _, b, _ = briefing.split_prompt(briefing.variant(prompt, "compact_without_jev"))
    a.pop("jev_evidence"); b.pop("jev_evidence")
    assert a == b and tail == "\nOUTPUT_CLOSURE: original closure"
    assert a["required_output_template"] == source["required_output_template"]


def test_guidance_has_no_threshold_or_execution_shortcut():
    skill = briefing.GUIDANCE_PATH.read_text()
    assert "not original-target-before-stop" in skill
    assert "Hermes owns" in skill and "Never invent" in skill
    assert "no tool or order" in skill


def test_bad_shape_cannot_be_silently_compressed():
    source = envelope(); source["decision_packet"]["frames"][0]["market_snapshot"]["instruments"][0]["timeframe_bars"] = None
    with pytest.raises(ValueError, match="unsupported_bar_shape"):
        briefing.compact(source)
