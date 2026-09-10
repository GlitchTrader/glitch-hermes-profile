"""Read-only output-contract regressions; no live accounts or model calls."""
import copy
import json

import pytest

from test_direct_cycle_contracts import DIRECT, multibook_flat_scenario, position_management_evidence


@pytest.mark.parametrize("value", [
    "MNQ bearish destination remains 120 as an intermediate response, with larger support 100; "
    "current price has not supplied accepted downside extension.",
    "Price has not provided buyer response; objective 150 and invalidation 100 remain conditional.",
    "No authoritative order flow is available; objective 150, invalidation 100 derive from price.",
    "Target 150 is conditional because price has not supplied acceptance.",
])
def test_absent_market_response_is_not_deferring_setup_interpretation(value):
    DIRECT.validate_setup_derivation(value, 0, "trigger_review")


@pytest.mark.parametrize("value", [
    "No authoritative primary objective and invalidation pair was supplied",
    "Objective not supplied by packet",
    "Target is not provided",
    "Stop and target were not supplied",
    "Entry zone must be supplied",
    "Unsupplied invalidation prevents evaluation",
    "Geometry: not supplied",
])
def test_explicit_missing_geometry_deferral_still_fails(value):
    with pytest.raises(ValueError, match="setup_derivation_deferred"):
        DIRECT.validate_setup_derivation(value, 0, "trigger_review")


def positioned_scenario():
    scenario = multibook_flat_scenario()
    for index, book in enumerate(scenario["books"]):
        book["followers"] = [{"account": "NEVER_ROUTE_HERE", "enabled": True}]
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
        book["instrument_contexts"] = {
            "MNQ": {"current_signed_quantity": -1, "native_protection": {"orders": [
                {"leg_id": f"LEG{index}", "role": "stop", "stop_price": 150},
                {"leg_id": f"LEG{index}", "role": "target", "limit_price": 100},
                {"role": "unknown"},
            ]}},
            "MES": {"current_signed_quantity": 0, "native_protection": {"orders": [
                {"leg_id": "UNRELATED_FLAT_LEG"},
            ]}},
        }
    return scenario


def test_management_contract_is_book_scoped_deduplicated_and_non_mutating():
    scenario = positioned_scenario()
    before = copy.deepcopy(scenario)
    contract = DIRECT.management_payload_contract(scenario)
    assert contract["books"] == [
        {"decision_index": 0, "instrument": "MNQ", "native_leg_ids": ["LEG0"]},
        {"decision_index": 1, "instrument": "MNQ", "native_leg_ids": ["LEG1"]},
    ]
    assert contract["MOVE_STOP"] == {"protection_updates": [{
        "leg_id": "SELECT_NATIVE_LEG_ID", "stop_loss": "SELECT_SUPPORTED_NUMERIC_PRICE",
    }]}
    assert set(contract["MOVE_TP"]["protection_updates"][0]) == {"leg_id", "stop_loss", "take_profit"}
    assert contract["HOLD_EXIT"] == "omit protection_updates"
    assert "NEVER_ROUTE_HERE" not in json.dumps(contract)
    assert "UNRELATED_FLAT_LEG" not in json.dumps(contract)
    assert scenario == before


def test_missing_native_legs_stay_missing_not_generated():
    scenario = positioned_scenario()
    scenario["books"][0]["instrument_contexts"]["MNQ"].pop("native_protection")
    assert DIRECT.management_payload_contract(scenario)["books"][0]["native_leg_ids"] == []


@pytest.mark.parametrize("protection", [None, "unavailable", {"orders": None}])
def test_unavailable_native_protection_does_not_break_prompt(protection):
    scenario = positioned_scenario()
    scenario["books"][0]["instrument_contexts"]["MNQ"]["native_protection"] = protection
    assert DIRECT.management_payload_contract(scenario)["books"][0]["native_leg_ids"] == []


def test_payload_examples_do_not_admit_missing_or_placeholder_protection():
    scenario = positioned_scenario()
    book = scenario["books"][0]
    intent = {"instrument": "MNQ", "action": "MOVE_STOP"}
    with pytest.raises(ValueError, match="protection_updates_required"):
        DIRECT.validate_protection_updates(intent, book, 0, require_target=False)
    intent.update(DIRECT.management_payload_contract(scenario)["MOVE_STOP"])
    with pytest.raises(ValueError, match="protection_update_leg_unknown"):
        DIRECT.validate_protection_updates(intent, book, 0, require_target=False)
    intent["protection_updates"] = [{"leg_id": "LEG0", "stop_loss": 125.0}]
    DIRECT.validate_protection_updates(intent, book, 0, require_target=False)


def test_position_prompt_exposes_wire_contract_without_changing_flat_prompt():
    scenario = positioned_scenario()
    packet = {"packet_id": "cycle-9", "policy": {}, "frames": [{
        "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
        "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
    }]}
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []})
    envelope = json.JSONDecoder().raw_decode(prompt.split("CURRENT_CYCLE=", 1)[1])[0]
    assert envelope["management_payload_contract"] == DIRECT.management_payload_contract(scenario)
    assert "price described only in reason or audit does not request a native change" in prompt
    for d in envelope["required_output_template"]["decisions"]:
        assert d["action"] == "HOLD"  # Schema example does not select a protection move.
        assert "protection_updates" not in d
    for book in scenario["books"]:
        book["instrument_contexts"]["MNQ"]["current_signed_quantity"] = 0
    flat = DIRECT.build_prompt(packet, scenario, {"outcomes": []})
    assert "management_payload_contract" not in flat


def test_management_probability_arithmetic_and_action_separation_remain_strict():
    evidence = position_management_evidence("HOLD", "NEGATIVE")
    with pytest.raises(ValueError, match="position_management_hold_ev_event_inversion"):
        DIRECT.validate_position_management(evidence, "M2K", "HOLD", 0, {
            "status": "complete", "hold_target_before_stop_break_even_probability": 0.15789474,
        })


@pytest.mark.parametrize("verdict", ["POSITIVE", "NEGATIVE", "STRADDLES"])
def test_hold_arithmetic_repair_names_exact_enum_without_replanning(verdict):
    error = ValueError(
        "position_management_hold_ev_event_inversion:0:declared=STRADDLES:"
        f"expected={verdict}:authoritative_target_first_break_even=0.31707317"
    )
    prompt = DIRECT.contract_repair_prompt("unused", {"decisions": [{"action": "HOLD"}]}, error)
    assert f"Set exactly gross_hold_terminal_ev={verdict};" in prompt
    assert "put any dollar interval in reason" in prompt
    assert "Preserve action, final_choice" in prompt
    assert "all probability estimates" in prompt
