"""Observed contract delays: preserve the judgment and every execution check."""
import copy

import pytest

from test_direct_cycle_contracts import DIRECT
from test_p0_p1_profile_contract import entry_batch


ENTRY = ("quantity", "order_type", "stop_loss", "take_profit_1",
         "entry_range_low", "entry_range_high", "forecast")


def misplaced():
    batch, scenario = entry_batch()
    expected = copy.deepcopy(batch)
    for field in ENTRY:
        batch[field] = batch["decisions"][0].pop(field)
    return batch, scenario, expected


@pytest.mark.parametrize("wording", [
    "delivery uncertainty included once",
    "model/transport uncertainty included in the probability range",
    "partial-bar delivery and stale depth remain execution uncertainty",
    "delivery drift priced once", "transport risk considered",
    "model latency priced once", "transport delay considered",
])
def test_authored_delivery_uncertainty_satisfies_only_latency_dimension(wording):
    evidence = "Risk 6 points, 24 ticks, $12, 1m ATR 7 and 5m ATR 15; " + wording
    DIRECT.validate_entry_geometry_evidence(evidence, 0, "trigger_review")
    with pytest.raises(ValueError, match="dollars"):
        DIRECT.validate_entry_geometry_evidence(evidence.replace("$12, ", ""), 0, "trigger_review")


@pytest.mark.parametrize("wording", [
    "spread friction priced once", "general execution uncertainty",
    "stale depth creates uncertainty", "delivery confirmed; market uncertainty",
    "delivery. Uncertainty from market structure", "transport available",
])
def test_missing_delivery_time_risk_still_requires_correction(wording):
    with pytest.raises(ValueError, match="latency"):
        DIRECT.validate_entry_geometry_evidence(
            "Risk 6 points, 24 ticks, $12, 1m ATR 7 and 5m ATR 15; " + wording,
            0, "candidate_comparison")


def test_single_explicit_entry_is_recovered_without_changing_authored_values():
    batch, scenario, expected = misplaced()
    batch["instrument"] = batch["decisions"][0]["instrument"]
    batch["decision_level_wake_triggers"] = []
    DIRECT.normalize_batch(batch, scenario)
    assert batch == expected
    DIRECT.normalize_batch(batch, scenario)
    assert batch == expected  # Reprocessing cannot accumulate or rewrite fields.
    DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("field,value", [
    ("instrument", "MES"), ("stop_loss", 99), ("quantity", True),
    ("forecast", {"event": "STOP_BEFORE_PRIMARY_TARGET", "probability": True}),
])
def test_conflicting_entry_values_are_never_selected_or_overwritten(field, value):
    batch, scenario, _ = misplaced()
    batch["decisions"][0][field] = value
    if field == "instrument":
        batch[field] = "MNQ"
    before = copy.deepcopy(batch)
    DIRECT.normalize_batch(batch, scenario)
    assert all(batch.get(key) == before[key] for key in ENTRY)
    with pytest.raises(ValueError, match="batch_unknown_fields"):
        DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("condition", ["multiple", "no_instrument", "choice_conflict", "not_entry"])
def test_ambiguous_or_non_entry_ownership_remains_invalid(condition):
    batch, scenario, _ = misplaced()
    if condition == "multiple":
        batch["decisions"].append(copy.deepcopy(batch["decisions"][0]))
    elif condition == "no_instrument":
        batch["decisions"][0].pop("instrument")
    elif condition == "choice_conflict":
        batch["decisions"][0]["decision_audit"]["final_choice"] = "NOTHING"
    else:
        batch["decisions"][0]["action"] = "NOTHING"
    DIRECT.normalize_batch(batch, scenario)
    assert all(key in batch for key in ENTRY)
    with pytest.raises(ValueError, match="batch_unknown_fields"):
        DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("field,value,error", [
    ("quantity", 0, "entry_quantity_invalid"),
    ("entry_range_high", 104.5, "entry_range_excludes_decision_price"),
    ("stop_loss", 106, "entry_range_geometry_invalid"),
    ("forecast", {"event": "STOP_BEFORE_PRIMARY_TARGET", "probability": 1.5,
                  "method": "authored", "confidence": .6}, "forecast_probability_invalid"),
])
def test_relocation_retains_quantity_range_geometry_and_forecast_checks(field, value, error):
    batch, scenario, _ = misplaced()
    batch[field] = value
    DIRECT.normalize_batch(batch, scenario)
    assert batch["decisions"][0][field] == value
    with pytest.raises(ValueError, match=error):
        DIRECT.validate_batch(batch, scenario)


def test_relocated_off_tick_stop_is_still_rejected_without_rounding():
    batch, scenario, _ = misplaced()
    scenario["market"]["candidates"][0]["instrument_economics"] = {
        "tick_size": .25, "point_value_usd": 2, "source": "native"}
    batch["stop_loss"] = 100.125
    DIRECT.normalize_batch(batch, scenario)
    with pytest.raises(ValueError, match="entry_native_price_off_tick"):
        DIRECT.validate_batch(batch, scenario)
    assert batch["decisions"][0]["stop_loss"] == 100.125


@pytest.mark.parametrize("condition", ["nonempty", "conflicting", "multiple"])
def test_empty_wake_alias_recovery_never_assigns_ambiguous_trigger_information(condition):
    batch, scenario = entry_batch()
    batch["decision_level_wake_triggers"] = []
    trigger = {"type": "PRICE_CROSS", "instrument": "MNQ", "direction": "ABOVE", "price": 110}
    if condition == "nonempty":
        batch["decision_level_wake_triggers"] = [trigger]
    elif condition == "conflicting":
        batch["wake_triggers"] = [trigger]
    else:
        batch["decisions"].append(copy.deepcopy(batch["decisions"][0]))
    DIRECT.normalize_batch(batch, scenario)
    assert "decision_level_wake_triggers" in batch
    with pytest.raises(ValueError, match="batch_unknown_fields"):
        DIRECT.validate_batch(batch, scenario)


def test_saved_shape_and_latency_synonym_need_no_second_model_call(monkeypatch):
    batch, scenario, expected = misplaced()
    evidence = batch["decisions"][0]["decision_audit"]["decisive_evidence"]
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = evidence.replace(
        "after latency", "with delivery uncertainty priced once")
    calls = []

    def response(*args, **kwargs):
        calls.append(1)
        assert len(calls) == 1, "Unexpected paid repair call"
        return copy.deepcopy(batch)

    monkeypatch.setattr(DIRECT, "invoke_hermes", response)
    result, repairs, retries = DIRECT.invoke_validated_batch("glitch", "saved", scenario, None, 30)
    assert (len(calls), repairs, retries) == (1, 0, 0)
    actual, original = result["decisions"][0], expected["decisions"][0]
    assert {key:actual[key] for key in ENTRY} == {key:original[key] for key in ENTRY}
    assert (actual["action"], actual["instrument"]) == (original["action"], original["instrument"])
