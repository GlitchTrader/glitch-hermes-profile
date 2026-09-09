"""Witnessed 2026-09-09 output failures; no model calls or trading side effects."""
import copy

import pytest

from test_direct_cycle_contracts import DIRECT, position_management_evidence, valid_batch


def selection(estimate="0.24-0.38", verdict="UNCERTAIN"):
    return (
        "direction=SHORT;entry=7684.75;stop=7688;target=7672.5;"
        "risk_points=3.25;reward_points=12.25;friction_points=0.25;"
        "breakeven_target_first=0.22580645;"
        f"estimated_target_first_range={estimate};now_ev={verdict};"
        "wait_price=7684;wait_ev=confirmation costs remaining room;"
        "decisive_reason=Wait for the authored alternative."
    )


def abstention(value):
    batch, scenario = valid_batch("2026-09-09T04:06:00Z")
    fields = {key: "authored evidence" for key in DIRECT.TRIGGER_REVIEW_FIELDS}
    fields.update(PRIOR_TRIGGER_REVIEW="HELD: invalidation intact",
                  SELECTION_INSTRUMENT="MNQ", SELECTION_ACTION="NOTHING",
                  SELECTION_EV=value)
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = "\n".join(
        [DIRECT.TRIGGER_REVIEW_MARKER] + [f"{key}={value}" for key, value in fields.items()])
    scenario["market"]["candidates"] = [{"instrument": "MNQ", "current_price": 7684.75}]
    return batch, scenario


@pytest.mark.parametrize("estimate,old,expected", [
    ("0.24-0.38", "UNCERTAIN", "POSITIVE"),
    ("24%-38%", "NEGATIVE", "POSITIVE"),
    ("0.10-0.20", "POSITIVE", "NEGATIVE"),
    ("0.10-0.38", "NEGATIVE", "UNCERTAIN"),
])
def test_abstention_math_correction_changes_only_exact_arithmetic_label(estimate, old, expected):
    batch, _ = abstention(selection(estimate, old))
    before = copy.deepcopy(batch)
    assert DIRECT.canonicalize_batch_selection_math(batch) == 1
    before["decisions"][0]["decision_audit"]["decisive_evidence"] = (
        before["decisions"][0]["decision_audit"]["decisive_evidence"]
        .replace(f"now_ev={old}", f"now_ev={expected}"))
    assert batch == before
    assert DIRECT.canonicalize_batch_selection_math(batch) == 0


@pytest.mark.parametrize("action", ["ENTER_LONG", "ENTER_SHORT", "HOLD", "EXIT", "MOVE_STOP", "MOVE_TP"])
def test_arithmetic_correction_cannot_admit_or_change_an_active_decision(action):
    batch, _ = abstention(selection())
    batch["decisions"][0]["action"] = action
    before = copy.deepcopy(batch)
    DIRECT.canonicalize_batch_selection_math(batch)
    assert batch == before
    assert "verdict_range_mismatch" in DIRECT.deterministic_selection_math(selection())["calculation_issues"]


@pytest.mark.parametrize("value", [
    selection("UNAVAILABLE"), selection().replace("target=7672.5", "target=NONE_SUPPLIED"),
    selection().replace("stop=7688", "stop=7680"), selection("0.38-0.24"),
    selection("0.24-0.38", "UNCERTAIN because of location"),
    selection("0.223-0.38"),  # existing rounding tolerance is unchanged
])
def test_unknown_invalid_or_qualified_verdict_is_not_invented(value):
    batch, _ = abstention(value)
    before = copy.deepcopy(batch)
    DIRECT.canonicalize_batch_selection_math(batch)
    assert batch == before


def test_witnessed_abstention_label_error_requires_no_second_model_call(monkeypatch):
    batch, scenario = abstention(selection())
    calls = []

    def invoke(*args, **kwargs):
        calls.append(args)
        assert len(calls) == 1, "Arithmetic on a fixed NOTHING is not another market review"
        return copy.deepcopy(batch)

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    result, repairs, retries = DIRECT.invoke_validated_batch(
        "glitch", "prompt", scenario, None, 30, decision_mode="trigger_review")
    assert (repairs, retries, len(calls)) == (0, 0, 1)
    assert result["decisions"][0]["action"] == "NOTHING"
    evidence = result["decisions"][0]["decision_audit"]["decisive_evidence"]
    assert "now_ev=POSITIVE" in evidence
    assert "estimated_target_first_range=0.24-0.38" in evidence
    assert not any(x.startswith(DIRECT.SELECTION_EV_SELF_CONSISTENCY_ERRORS)
                   for x in DIRECT.validate_batch(result, scenario, expected_decision_mode="trigger_review"))


@pytest.mark.parametrize("action", ["NOTHING", "ENTER_LONG", "ENTER_SHORT"])
def test_terminal_audit_tail_with_identical_choice_is_relocated_verbatim(action):
    batch, _ = valid_batch("2026-09-09T05:52:00Z")
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    intent = batch["decisions"][0]
    intent["action"] = intent["decision_audit"]["final_choice"] = action
    audit = intent["decision_audit"]
    audit["decisive_evidence"] = "TRIGGER_REVIEW_V1\nSELECTION_REASON=Authored comparison."
    expected = copy.deepcopy(batch)
    audit["decisive_evidence"] += (
        "\nDISCONFIRMING_EVIDENCE=" + audit.pop("disconfirming_evidence")
        + "\nCHANGE_CONDITION=" + audit.pop("change_condition")
        + "\nFINAL_CHOICE=" + action)
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    assert batch == expected


def test_conflicting_terminal_choice_is_not_reconciled_by_code():
    batch, _ = valid_batch("2026-09-09T05:52:00Z")
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] += (
        "\nDISCONFIRMING_EVIDENCE=" + audit.pop("disconfirming_evidence")
        + "\nCHANGE_CONDITION=" + audit.pop("change_condition")
        + "\nFINAL_CHOICE=ENTER_LONG")
    expected = copy.deepcopy(batch)
    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    assert batch == expected


@pytest.mark.parametrize("mode,marker", [
    ("flat_scan", DIRECT.CANDIDATE_COMPARISON_MARKER),
    ("trigger_review", DIRECT.TRIGGER_REVIEW_MARKER),
    ("position_management", DIRECT.POSITION_MANAGEMENT_MARKER),
])
def test_format_repair_receives_authoritative_mode_and_book_count(mode, marker):
    batch, scenario = valid_batch("2026-09-09T06:08:00Z")
    context = DIRECT.contract_repair_context(scenario, batch, decision_mode=mode)
    assert context["required_decisive_evidence_marker"] == marker
    assert context["ordered_master_book_count"] == 1
    prompt = DIRECT.contract_repair_prompt("unused", batch, ValueError("decision_count_mismatch"), context)
    assert '"required_decisive_evidence_marker":"' + marker + '"' in prompt
    assert "never one decision per candidate instrument" in prompt
    assert "preserve the required ledger mode" in prompt
    assert "no market reassessment" in prompt


@pytest.mark.parametrize("message", [
    "protection_updates_required:0", "protection_update_not_object:0:0",
    "protection_update_fields_invalid:0:0", "protection_update_leg_invalid:0:0",
    "protection_update_leg_unknown:0:0", "protection_update_price_invalid:0:0",
    "protection_update_stop_invalid:0:0",
])
def test_invalid_protection_payload_needs_fresh_review_not_impossible_repair(message):
    assert DIRECT.retryable_model_contract_error(ValueError(message)) is False


def test_missing_protection_payload_does_not_spend_a_second_model_call(monkeypatch):
    batch, scenario = valid_batch("2026-09-09T09:30:00Z")
    scenario["books"][0]["instrument_contexts"] = {
        "MNQ": {"current_signed_quantity": -1,
                "native_protection": {"orders": [{"leg_id": "NATIVE_LEG"}]}}}
    intent = batch["decisions"][0]
    intent["action"] = intent["decision_audit"]["final_choice"] = "MOVE_STOP"
    intent["reason"] = "Move the stop to the authored structural level."
    intent["decision_audit"]["decisive_evidence"] = position_management_evidence(
        "MOVE_STOP", "POSITIVE").replace("INSTRUMENT=M2K", "INSTRUMENT=MNQ")
    calls = []

    def invoke(*args, **kwargs):
        calls.append(args)
        assert len(calls) == 1, "A repair cannot add or change a native protection instruction"
        return copy.deepcopy(batch)

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    with pytest.raises(ValueError, match="^protection_updates_required:0$"):
        DIRECT.invoke_validated_batch(
            "glitch", "full native evidence", scenario, None, 30,
            decision_mode="position_management")
    assert len(calls) == 1
    assert "protection_updates" not in intent
