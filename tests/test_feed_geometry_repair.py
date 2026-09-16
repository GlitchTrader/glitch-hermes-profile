"""September 16 witnessed defects; causal fixtures, no model or native calls."""
import copy
import json

import pytest

from test_direct_cycle_contracts import DIRECT
from test_learning_p0_repairs import LEARNING
from test_market_structure import ms, frame, minute_id


def mes_entry():
    selection = (
        "direction=MES long;entry=7672.5-7673.0;stop=7668.25;target=7678.25;"
        "risk_points=3.75;reward_points=6.25;friction_points=0.25;"
        "breakeven_target_first=0.4167;estimated_target_first_range=0.54-0.60;now_ev=POSITIVE"
    )
    intent = {"action": "ENTER_LONG", "instrument": "MES", "quantity": 1,
              "entry_range_low": 7672.5, "entry_range_high": 7673.0,
              "stop_loss": 7668.25, "take_profit_1": 7678.25,
              "decision_audit": {"decisive_evidence": "SELECTION_EV=" + selection},
              "forecast": {"event": "STOP_BEFORE_PRIMARY_TARGET", "probability": 0.43}}
    scenario = {"market": {"candidates": [{"instrument": "MES", "current_price": 7673}]}}
    return intent, scenario, selection


def test_witnessed_range_math_uses_native_packet_reference_not_range_low():
    intent, scenario, selection = mes_entry()
    geometry = DIRECT.submitted_selection_geometry(intent, scenario)
    math = DIRECT.deterministic_selection_math(selection, intent["forecast"], geometry)
    assert math["computed_risk_points"] == 4.75
    assert math["computed_reward_points"] == 5.25
    assert math["computed_breakeven_target_first"] == 0.5
    assert "declared_risk_mismatch" in math["calculation_issues"]
    audit = LEARNING.selection_ev_arithmetic_audit(intent["decision_audit"], intent["forecast"], geometry)
    assert audit["deterministic_breakeven_target_first"] == 0.5
    assert audit["arithmetic_status"] == "mismatch"
    before = copy.deepcopy(intent)
    DIRECT.canonicalize_batch_selection_math({"decisions": [intent]}, scenario)
    text = intent["decision_audit"]["decisive_evidence"]
    assert "entry=7673;" in text and "risk_points=4.75;" in text
    assert "reward_points=5.25;" in text and "breakeven_target_first=0.5;" in text
    intent["decision_audit"] = before["decision_audit"]
    assert intent == before  # execution, action and probabilities untouched


@pytest.mark.parametrize("direction", ["LONG", "MES long", "MNQ LONG", "m2k long"])
def test_instrument_qualified_direction_has_same_math(direction):
    _, _, selection = mes_entry()
    support = DIRECT.deterministic_selection_math(selection.replace("MES long", direction).replace("7672.5-7673.0", "7673"))
    assert support["status"] == "complete"
    assert support["computed_risk_points"] == 4.75


def test_small_positive_edge_is_not_mislabeled_as_straddling():
    text = ("direction=SHORT;entry=100;stop=110.25;target=90.25;"
            "risk_points=10.25;reward_points=9.75;friction_points=0.5;"
            "breakeven_target_first=0.5375;estimated_target_first_range=0.54-0.60;now_ev=POSITIVE")
    audit = LEARNING.selection_ev_arithmetic_audit({"decisive_evidence": "SELECTION_EV=" + text})
    assert audit["range_vs_break_even"] == "above_break_even"
    assert audit["expected_now_ev_from_range"] == "POSITIVE"


def test_unresolved_range_is_unknown_and_opposite_direction_is_not_hidden():
    intent, scenario, selection = mes_entry()
    assert DIRECT.deterministic_selection_math(selection)["status"] == "incomplete"
    intent["decision_audit"]["decisive_evidence"] = "SELECTION_EV=" + selection.replace("MES long", "SHORT")
    before = copy.deepcopy(intent)
    DIRECT.canonicalize_batch_selection_math({"decisions": [intent]}, scenario)
    assert intent == before
    with pytest.raises(ValueError, match="direction_action_mismatch"):
        DIRECT.validate_selection_ev(selection.replace("MES long", "SHORT"), "ENTER_LONG", 0, "test")


def test_contract_switch_cannot_join_old_and_new_bars():
    state = ms._empty_state()
    ms.ingest_frame(state, frame(1))
    switched = frame(2)
    switched["market_snapshot"]["instruments"][2]["instrument_full_name"] = "M2K 12-26"
    ms.ingest_frame(state, switched)
    assert len(state["instruments"]["M2K"]["bars"]) == 1
    assert len(state["instruments"]["MES"]["bars"]) == 2


def test_mixed_contract_native_candles_are_not_ingested():
    state = ms._empty_state()
    value = frame(2)
    m2k = value["market_snapshot"]["instruments"][2]
    m2k["timeframe_bars"][0]["descriptive_state"]["native_observations"]["instrument_full_name"] = "M2K 12-26"
    ms.ingest_frame(state, value)
    assert "M2K" not in state["instruments"]
    assert len(state["instruments"]) == 2


def test_backfill_selects_current_contract_without_repeated_history_resets(tmp_path):
    directory = tmp_path / "glitch" / "minute-frames"
    directory.mkdir(parents=True)
    frames = []
    for index in range(10):
        value = frame(index)
        if index % 2 == 0:
            value["market_snapshot"]["instruments"][2]["instrument_full_name"] = "M2K 12-26"
        frames.append(value)
        (directory / (value["minute_id"] + ".json")).write_text(json.dumps(value))
    packet = {"packet_id": minute_id(10), "frames": frames[-5:]}
    state = ms.update_state_from_exchange(ms._empty_state(), packet, tmp_path)
    slot = state["instruments"]["M2K"]
    assert slot["instrument_full_name"] == "M2K 09-26"
    assert len(slot["bars"]) == 5
    assert len(state["instruments"]["MES"]["bars"]) == 10


def test_legacy_mixed_cache_is_not_trusted(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"schema_version": "glitch.hermes.market_perception_state.v2",
                                "instruments": {"M2K": {"bars": [{"c": 100}]}}}))
    assert ms.load_state(path) == ms._empty_state()
    assert path.exists()  # no destructive migration of raw evidence


def test_invalid_frame_does_not_break_contract_selection(tmp_path):
    value = frame(2)
    packet = {"packet_id": value["minute_id"], "frames": [None, value]}
    state = ms.update_state_from_exchange(ms._empty_state(), packet, tmp_path)
    assert len(state["instruments"]) == 3
