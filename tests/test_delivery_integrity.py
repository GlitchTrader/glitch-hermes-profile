"""Witnessed delivery defects; no model calls, live files or native orders."""
import copy
import json

import pytest

from test_direct_cycle_contracts import DIRECT, valid_batch


def trigger_evidence(separator="\n"):
    values = {field: "supported current evidence" for field in DIRECT.TRIGGER_REVIEW_FIELDS}
    values.update(PRIOR_TRIGGER_REVIEW="HELD: invalidation intact",
                  SELECTION_INSTRUMENT="MES", SELECTION_ACTION="NOTHING")
    return separator.join([DIRECT.TRIGGER_REVIEW_MARKER] +
                          [f"{field}={value}" for field, value in values.items()])


@pytest.mark.parametrize("separator", ["; ", " ", "\n", "\\n"])
def test_inline_trigger_review_preserves_authored_values(separator):
    batch, _ = valid_batch("2026-09-09T02:14:00Z")
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    intent = batch["decisions"][0]
    intent["instrument"] = "MES"
    intent["decision_audit"]["decisive_evidence"] = trigger_evidence(separator)
    before = copy.deepcopy(intent)
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    evidence = intent["decision_audit"]["decisive_evidence"]
    DIRECT.validate_trigger_review(evidence, ["MES"], "MES", "NOTHING", 0)
    assert evidence == trigger_evidence()
    before["decision_audit"]["decisive_evidence"] = evidence
    assert intent == before


def test_terminal_misnested_disconfirmation_is_relocated_without_model_repair():
    batch, _ = valid_batch("2026-09-09T02:14:00Z")
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = trigger_evidence()
    original = copy.deepcopy(batch)
    text = audit.pop("disconfirming_evidence")
    audit["decisive_evidence"] += "\nDISCONFIRMING_EVIDENCE=" + text
    malformed = json.dumps(batch).replace('", "change_condition":', '\\nchange_condition":')
    with pytest.raises(json.JSONDecodeError):
        json.loads(malformed)
    restored = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")
    DIRECT.normalize_batch(restored, normalize_trigger_fields=False)
    assert restored == original


def candidate(tick=0.25):
    return {"instrument": "MES", "current_price": 7683.75,
            "instrument_economics": {"tick_size": tick, "point_value_usd": 5,
                                     "source": "ninjatrader"}}


@pytest.mark.parametrize("field,value", [
    ("stop_loss", 7685.375), ("take_profit_1", 7680.6098),
    ("take_profit_2", 7679.125), ("stop_loss_2", 7685.375),
    ("take_profit_3", 7678.125), ("stop_loss_3", 7685.375),
])
def test_every_native_entry_price_is_checked_without_silent_rounding(field, value):
    intent = {"action": "ENTER_SHORT", "stop_loss": 7685.5, "take_profit_1": 7680.5,
              field: value}
    before = copy.deepcopy(intent)
    with pytest.raises(ValueError, match="entry_native_price_off_tick"):
        DIRECT.validate_native_order_prices(intent, candidate(), 0)
    assert intent == before


@pytest.mark.parametrize("tick,price", [(0.25, 7685.5), (0.1, 2969.4), (0.1, 2969.4000000000005)])
def test_native_grid_accepts_valid_prices_and_float_representation_noise(tick, price):
    intent = {"action": "ENTER_LONG", "stop_loss": price, "take_profit_1": price + 10}
    DIRECT.validate_native_order_prices(intent, candidate(tick), 0)


@pytest.mark.parametrize("action,field", [("MOVE_STOP", "stop_loss"), ("MOVE_TP", "take_profit")])
def test_management_off_tick_prices_do_not_reach_native_submission(action, field):
    intent = {"action": action, "protection_updates": [{"leg_id": "native-leg", field: 7685.375}]}
    with pytest.raises(ValueError, match="management_native_price_off_tick"):
        DIRECT.validate_native_order_prices(intent, candidate(), 0)


def test_native_tick_neighbors_are_facts_not_a_selected_bracket():
    assert DIRECT.native_tick_neighbors(7685.375, 0.25) == {"lower": 7685.25, "upper": 7685.5}
    assert DIRECT.native_tick_neighbors(7680.6098, 0.25) == {"lower": 7680.5, "upper": 7680.75}
    assert DIRECT.native_tick_neighbors(2969.45, 0.1) == {"lower": 2969.4, "upper": 2969.5}
    assert DIRECT.native_tick_neighbors(7685.5, 0.25) == {"lower": 7685.5, "upper": 7685.5}


def test_cognition_separates_expired_order_scope_from_a_fresh_decision():
    source = (DIRECT.Path(__file__).resolve().parents[1] / "scripts/run-direct-glitch-cycle.py").read_text()
    assert "an expired order range is not a permanent veto" in source
    assert "VWAP and order flow are optional corroboration" in source
    scan = (DIRECT.Path(__file__).resolve().parents[1] / "skills/glitch-market-scan/SKILL.md").read_text()
    assert "order-flow requirement" not in scan


def entry_fixture():
    batch, scenario = valid_batch("2026-09-09T01:53:00Z")
    scenario["market"]["candidates"] = [candidate()]
    intent = batch["decisions"][0]
    intent.update(instrument="MES", action="ENTER_SHORT", quantity=1, order_type="MARKET",
                  stop_loss=7685.375, take_profit_1=7680.6098,
                  entry_range_low=7683.5, entry_range_high=7684.0,
                  forecast={"event": "STOP_BEFORE_PRIMARY_TARGET", "probability": 0.45,
                            "confidence": 0.5, "method": "original unchanged bracket"})
    values = {field: "supported current evidence" for field in DIRECT.TRIGGER_REVIEW_FIELDS}
    values.update(PRIOR_TRIGGER_REVIEW="HELD: invalidation intact",
                  ENTRY_RANGE_NOISE_GEOMETRY="1.625 points, 6.5 ticks, $8.125; 1m/5m ATR and latency considered",
                  SELECTION_INSTRUMENT="MES", SELECTION_ACTION="ENTER_SHORT")
    intent["decision_audit"]["final_choice"] = "ENTER_SHORT"
    intent["decision_audit"]["decisive_evidence"] = (
        "\n".join([DIRECT.TRIGGER_REVIEW_MARKER] + [f"{k}={v}" for k, v in values.items()])
        + "\nSELECTION_EV=direction=SHORT;entry=7683.75;stop=7685.375;target=7680.6098;"
        "risk_points=1.625;reward_points=3.1402;friction_points=0.25;"
        "breakeven_target_first=0.3935;estimated_target_first_range=0.50-0.60;"
        "now_ev=POSITIVE;wait_price=7684;wait_ev=POSITIVE;decisive_reason=current evidence")
    return batch, scenario


def repaired_entry(batch):
    repaired = copy.deepcopy(batch)
    intent = repaired["decisions"][0]
    intent.update(stop_loss=7685.5, take_profit_1=7680.5)
    intent["decision_audit"]["decisive_evidence"] = (
        intent["decision_audit"]["decisive_evidence"]
        .replace("stop=7685.375", "stop=7685.5").replace("target=7680.6098", "target=7680.5"))
    DIRECT.canonicalize_batch_selection_math(repaired)
    return repaired


@pytest.mark.parametrize("book_count", [1, 2])
def test_native_price_repair_is_one_bounded_call_and_preserves_shared_decision(monkeypatch, book_count):
    first, scenario = entry_fixture()
    if book_count == 2:
        scenario["books"].append({"route_id": "second", "master_account": "Sim301"})
    second = repaired_entry(first)
    calls = []

    def invoke(_profile, prompt, _timeout, **kwargs):
        calls.append((prompt, kwargs))
        assert len(calls) <= 2
        return copy.deepcopy(first if len(calls) == 1 else second)

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    result, repairs, retries = DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL", scenario, None, 30, decision_mode="trigger_review")
    assert (repairs, retries) == (1, 0)
    assert calls[1][0].startswith("NATIVE_PRICE_CORRECTION_ONLY:")
    assert '"lower":7685.25,"upper":7685.5' in calls[1][0]
    assert calls[1][1]["image_path"] is None
    assert len(result["decisions"]) == book_count
    for intent in result["decisions"]:
        assert (intent["action"], intent["quantity"], intent["stop_loss"], intent["take_profit_1"]) == (
            "ENTER_SHORT", 1, 7685.5, 7680.5)
        assert intent["forecast"] == first["decisions"][0]["forecast"]


@pytest.mark.parametrize("field,value", [
    ("instrument", "MNQ"), ("action", "ENTER_LONG"), ("quantity", 2),
    ("entry_range_low", 7683), ("entry_range_high", 7684.5), ("confidence", 0.8),
    ("stop_loss", 7685.75), ("take_profit_1", 7680.25),
])
def test_native_price_repair_cannot_expand_into_recalibration(field, value):
    before, scenario = entry_fixture()
    after = repaired_entry(before)
    after["decisions"][0][field] = value
    with pytest.raises(ValueError, match="native_price_repair_"):
        DIRECT.enforce_native_price_repair_boundary(
            before, after, scenario, ValueError("entry_native_price_off_tick:0"))


@pytest.mark.parametrize("old,new", [
    ("estimated_target_first_range=0.50-0.60", "estimated_target_first_range=0.70-0.80"),
    ("entry=7683.75", "entry=7684"), ("friction_points=0.25", "friction_points=0.1"),
])
def test_native_price_repair_cannot_backsolve_probability_or_change_reference(old, new):
    before, scenario = entry_fixture()
    after = repaired_entry(before)
    after["decisions"][0]["decision_audit"]["decisive_evidence"] = (
        after["decisions"][0]["decision_audit"]["decisive_evidence"].replace(old, new))
    with pytest.raises(ValueError, match="native_price_repair_evidence_changed"):
        DIRECT.enforce_native_price_repair_boundary(
            before, after, scenario, ValueError("entry_native_price_off_tick:0"))


def test_invalid_price_does_not_prevent_existing_contract_repair_context():
    batch, scenario = entry_fixture()
    batch["decisions"][0]["stop_loss"] = None
    context = DIRECT.contract_repair_context(scenario, batch)
    assert context["candidates"][0]["native_price_options"] == []
    assert context["candidates"][0]["geometry"]["tick_size_points"] == 0.25


def test_native_price_repair_may_abstain_but_cannot_poison_the_next_review_geometry():
    before, scenario = entry_fixture()
    after = repaired_entry(before)
    decision = after["decisions"][0]
    decision["action"] = decision["decision_audit"]["final_choice"] = "NOTHING"
    decision["decision_audit"]["decisive_evidence"] = (
        decision["decision_audit"]["decisive_evidence"].replace("SELECTION_ACTION=ENTER_SHORT", "SELECTION_ACTION=NOTHING"))
    for key in DIRECT.ENTRY_FIELDS | DIRECT.ENTRY_RANGE_FIELDS:
        decision.pop(key, None)
    error = ValueError("entry_native_price_off_tick:0")
    DIRECT.validate_batch(after, scenario, expected_decision_mode="trigger_review")
    DIRECT.enforce_native_price_repair_boundary(before, after, scenario, error)
    decision["decision_audit"]["decisive_evidence"] = (
        decision["decision_audit"]["decisive_evidence"].replace("stop=7685.5", "stop=7690"))
    with pytest.raises(ValueError, match="native_price_repair_geometry_changed"):
        DIRECT.enforce_native_price_repair_boundary(before, after, scenario, error)


def test_normalization_does_not_split_selection_arithmetic_or_invent_absent_fields():
    batch, _ = entry_fixture()
    original = batch["decisions"][0]["decision_audit"]["decisive_evidence"]
    flat = original.replace("\n", "; ")
    assert DIRECT.normalize_ledger_separators(flat) == original
    absent = flat.replace("FIRED_TRIGGER=supported current evidence; ", "")
    restored = DIRECT.normalize_ledger_separators(absent)
    with pytest.raises(ValueError, match="trigger_review_field_missing:0:FIRED_TRIGGER"):
        DIRECT.validate_trigger_review(restored, ["MES"], "MES", "ENTER_SHORT", 0)
