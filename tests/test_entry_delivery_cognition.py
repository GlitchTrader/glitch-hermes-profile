"""Delivery evidence stays observational; native intent validation is unchanged."""
import copy
import json

import pytest

from test_direct_cycle_contracts import DIRECT
from test_reference_units_and_management_shape import geometry_packet


def quoted_candidate(bid=30128.75, ask=30129.0):
    return {
        "instrument": "MNQ", "current_price": 30129.0,
        "timestamp_utc": "2026-09-21T06:47:00Z",
        "instrument_economics": {"point_value_usd": 2, "tick_size": 0.25},
        "timeframe_bars": [{"minutes": 1, "indicators": {"atr": 5.13},
            "descriptive_state": {"descriptive_state": {"liquidity": {
                "best_bid": bid, "best_ask": ask, "spread_points": 0.25,
                "last_quote_age_seconds": 0.001, "quality": "stale_or_unavailable",
            }}}}],
    }


def test_quote_context_preserves_sides_age_and_reference_without_claiming_a_fill():
    candidate = quoted_candidate()
    before = copy.deepcopy(candidate)
    context = DIRECT.deterministic_geometry_context(candidate)
    execution = context["entry_execution"]
    assert execution["packet_quotes"] == {
        "status": "observed_in_packet_not_a_current_fill",
        "sell_bid": 30128.75, "buy_ask": 30129.0,
        "instrument_observed_utc": "2026-09-21T06:47:00Z",
        "quote_age_seconds_at_observation": 0.001,
    }
    assert execution["decision_reference_price"] == 30129.0
    assert candidate == before
    assert context["effect"] == "decision_support_only_no_execution_effect"
    assert not {"action", "entry_range_low", "entry_range_high", "stop_loss"} & context.keys()


@pytest.mark.parametrize("bid,ask", [(None, 100), (99, None), (True, 100),
    (99, float("nan")), (float("inf"), 100), (101, 100), (0, 100), ("99", 100)])
def test_unusable_or_crossed_quote_never_becomes_an_executable_reference(bid, ask):
    context = DIRECT.deterministic_geometry_context(quoted_candidate(bid, ask))
    assert context["entry_execution"]["packet_quotes"] == {"status": "unavailable"}
    assert context["entry_execution"]["decision_reference_price"] == 30129.0


@pytest.mark.parametrize("trigger,limit", [(False, 6000), (True, 4000)])
def test_compact_flat_output_preserves_native_packet_full_comparison_and_wire_shape(trigger, limit):
    packet, perception, scenario = geometry_packet()
    scenario["market"]["candidates"] = [{"instrument": i} for i in ("MNQ", "MES", "M2K")]
    before = copy.deepcopy((packet, perception, scenario))
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []},
        invocation_reason="condition_change" if trigger else "scheduled",
        invocation_context={"fired_triggers": [{"instrument": "MNQ"}]} if trigger else None,
        market_perception=perception)
    assert f"Aim for {limit} chars; retain all required facts" in prompt
    envelope = json.JSONDecoder().raw_decode(prompt.split("CURRENT_CYCLE=", 1)[1])[0]
    template = envelope["required_output_template"]["decisions"][0]
    assert set(template["decision_audit"]) == DIRECT.DECISION_AUDIT_FIELDS
    evidence = template["decision_audit"]["decisive_evidence"]
    assert (DIRECT.TRIGGER_REVIEW_MARKER if trigger else DIRECT.CANDIDATE_COMPARISON_MARKER) in evidence
    if not trigger:
        assert all(f"INSTRUMENT {i}:" in evidence for i in ("MNQ", "MES", "M2K"))
    assert (packet, perception, scenario) == before


def test_management_output_budget_and_action_contract_are_not_changed():
    packet, perception, scenario = geometry_packet()
    scenario["books"][0]["instrument_contexts"] = {"MNQ": {"current_signed_quantity": 1}}
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []}, market_perception=perception)
    assert "Keep the entire response under 9000 characters" in prompt
    assert "Aim for " not in prompt
    assert DIRECT.POSITION_MANAGEMENT_MARKER in prompt
