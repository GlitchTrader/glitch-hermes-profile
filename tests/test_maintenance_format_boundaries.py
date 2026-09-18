"""Lossless witnessed formatting repairs; no model calls or native actions."""
import copy
from pathlib import Path

import pytest

from test_direct_cycle_contracts import (
    DIRECT, comparison_ledger, position_management_evidence, valid_batch,
)


def comparison(selected="MNQ"):
    fields = [f"{key}=supported evidence" for key in DIRECT.CANDIDATE_COMPARISON_FIELDS]
    return comparison_ledger({"MNQ": fields, "MES": fields}).replace(
        "SELECTION_INSTRUMENT=MNQ", f"SELECTION_INSTRUMENT={selected}")


@pytest.mark.parametrize("selected", ["MNQ", "MNQ 09-26", "MNQ 12-26"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_full_native_selection_preserves_root_validation(selected, newline):
    evidence = comparison(selected).replace("\n", newline)
    DIRECT.validate_candidate_comparison(evidence, ["MNQ", "MES"], "MNQ", "NOTHING", 0)
    batch, scenario = valid_batch("2026-09-11T04:31:00Z")
    scenario["market"]["candidates"] = [{"instrument": "MNQ"}, {"instrument": "MES"}]
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = evidence
    DIRECT.normalize_batch(batch, scenario)
    assert batch["decisions"][0]["instrument"] == "MNQ"
    assert batch["decisions"][0]["decision_audit"]["decisive_evidence"] == evidence


@pytest.mark.parametrize("selected", ["NQ 09-26", "MNQ or MES", "MNQ 09-26 sell", "MNQ 09-2026"])
def test_selection_suffix_does_not_admit_other_roots_or_extra_judgments(selected):
    with pytest.raises(ValueError, match="candidate_comparison_selection"):
        DIRECT.validate_candidate_comparison(comparison(selected), ["MNQ", "MES"], "MNQ", "NOTHING", 0)


def test_duplicate_wake_copy_collapses_without_changing_intent():
    batch, scenario = valid_batch("2026-09-11T18:35:00Z")
    DIRECT.normalize_batch(batch, scenario)
    before = copy.deepcopy(batch)
    batch["wake_triggers"] = copy.deepcopy(batch["decisions"][0]["wake_triggers"])
    DIRECT.normalize_batch(batch, scenario)
    assert batch == before
    DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("ambiguous", [False, True])
def test_wake_conflict_or_multi_decision_ownership_stays_invalid(ambiguous):
    batch, scenario = valid_batch("2026-09-11T18:35:00Z")
    batch["wake_triggers"] = [] if ambiguous else [{"different": True}]
    if ambiguous:
        batch["decisions"].append(copy.deepcopy(batch["decisions"][0]))
    DIRECT.normalize_batch(batch)
    assert "wake_triggers" in batch
    with pytest.raises(ValueError, match="batch_unknown_fields:wake_triggers"):
        DIRECT.validate_batch(batch, scenario)


def management(action="HOLD"):
    batch, _ = valid_batch("2026-09-11T11:14:00Z")
    intent = batch["decisions"][0]
    intent["action"] = action
    intent["decision_audit"].update(
        decisive_evidence=position_management_evidence(action, "POSITIVE"),
        final_choice=action,
    )
    return batch


@pytest.mark.parametrize("action", ["HOLD", "EXIT", "MOVE_STOP", "MOVE_TP"])
def test_missing_management_action_mirror_reuses_two_agreeing_authored_choices(action):
    batch = management(action)
    DIRECT.normalize_batch(batch)
    before = copy.deepcopy(batch)
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = audit["decisive_evidence"].replace(f"SELECTION_ACTION={action}\n", "")
    expected = audit["decisive_evidence"] + f"\nSELECTION_ACTION={action}"
    DIRECT.normalize_batch(batch)
    assert audit["decisive_evidence"] == expected
    before["decisions"][0]["decision_audit"]["decisive_evidence"] = expected
    assert batch == before
    DIRECT.validate_position_management(expected, "M2K", action, 0, {
        "status": "complete", "hold_target_before_stop_break_even_probability": .15789474,
    })


@pytest.mark.parametrize("conflict", ["final_choice", "explicit_line", "invalid_action"])
def test_action_mirror_does_not_resolve_disagreement(conflict):
    batch = management()
    intent = batch["decisions"][0]
    audit = intent["decision_audit"]
    if conflict == "explicit_line":
        audit["decisive_evidence"] = audit["decisive_evidence"].replace("SELECTION_ACTION=HOLD", "SELECTION_ACTION=EXIT")
    else:
        audit["decisive_evidence"] = audit["decisive_evidence"].replace("SELECTION_ACTION=HOLD\n", "")
        if conflict == "final_choice":
            audit["final_choice"] = "EXIT"
        else:
            intent["action"] = audit["final_choice"] = "INVALID"
    before = audit["decisive_evidence"]
    DIRECT.normalize_batch(batch)
    assert audit["decisive_evidence"] == before


def test_action_mirror_cannot_bypass_hold_probability_or_arithmetic():
    batch = management()
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = audit["decisive_evidence"].replace("SELECTION_ACTION=HOLD\n", "")
    audit["decisive_evidence"] = audit["decisive_evidence"].replace("break_even=15.79%", "break_even=90%")
    DIRECT.normalize_batch(batch)
    with pytest.raises(ValueError, match="position_management_hold_ev_event_inversion"):
        DIRECT.validate_position_management(audit["decisive_evidence"], "M2K", "HOLD", 0, {
            "status": "complete", "hold_target_before_stop_break_even_probability": .9,
        })


def test_missing_management_reason_mirror_uses_only_explicit_wire_reason():
    batch = management()
    intent = batch["decisions"][0]
    audit = intent["decision_audit"]
    intent["reason"] = "Authored reason for this selected action."
    audit["decisive_evidence"] = audit["decisive_evidence"].replace("SELECTION_REASON=model evidence", "")
    DIRECT.normalize_batch(batch)
    assert audit["decisive_evidence"].endswith("SELECTION_REASON=" + intent["reason"])
    assert "reason=compare the same target-first event" in audit["decisive_evidence"]
    before = copy.deepcopy(batch)
    DIRECT.normalize_batch(batch)
    assert batch == before


@pytest.mark.parametrize("reason", [None, "", "first\nsecond"])
def test_no_inferred_management_reason(reason):
    batch = management()
    intent = batch["decisions"][0]
    intent["reason"] = reason
    audit = intent["decision_audit"]
    audit["decisive_evidence"] = audit["decisive_evidence"].replace("SELECTION_REASON=model evidence", "")
    DIRECT.normalize_batch(batch)
    assert "SELECTION_REASON=" not in audit["decisive_evidence"]


def test_latency_in_selected_adjacent_clause_counts_but_other_candidates_do_not():
    base = comparison().replace("SELECTION_ACTION=NOTHING", "SELECTION_ACTION=ENTER_LONG")
    geometry = "risk 8 points/32 ticks/$16, 1m ATR 4 and 5m ATR 9"
    base = base.replace("NOISE_AND_GEOMETRY=supported evidence", "NOISE_AND_GEOMETRY=" + geometry)
    selected, other = base.split("INSTRUMENT MES:", 1)
    with pytest.raises(ValueError, match="entry_geometry_evidence_incomplete:0:candidate_comparison:latency"):
        DIRECT.validate_candidate_comparison(selected + "INSTRUMENT MES:\nEXECUTION_UNCERTAINTY=latency priced once\n" + other,
                                             ["MNQ", "MES"], "MNQ", "ENTER_LONG", 0)
    DIRECT.validate_candidate_comparison(selected + "EXECUTION_UNCERTAINTY=model latency priced once\nINSTRUMENT MES:" + other,
                                         ["MNQ", "MES"], "MNQ", "ENTER_LONG", 0)


def test_management_receipts_are_not_action_permission_and_noise_tolerance_remains():
    root = Path(__file__).resolve().parents[1]
    soul = (root / "SOUL.md").read_text(encoding="utf-8")
    skill = (root / "skills/glitch-position-management/SKILL.md").read_text(encoding="utf-8")
    assert '"unreceipted" does not make EXIT inferior' in soul
    assert "not an unspecified future rescue" in skill
    assert "same decision standard while green and red" in skill
    assert "an adverse mark, a one-minute indicator reversal or a probability estimate alone is not that evidence" in skill
    assert "do not wait for it to turn red" in skill


TRIGGER_SELECTION_FIELDS = (
    "ALTERNATIVE_CANDIDATES", "SELECTION_INSTRUMENT", "SELECTION_ACTION", "SELECTION_EV",
)


def trigger_selection_batch():
    batch, scenario = valid_batch("2026-09-14T10:17:00.0000000Z")
    values = {key: "Authored evidence." for key in DIRECT.TRIGGER_REVIEW_FIELDS}
    values.update(
        PRIOR_TRIGGER_REVIEW="HELD: original invalidation remains intact",
        ALTERNATIVE_CANDIDATES="MES has less room; MNQ remains the selected comparison.",
        SELECTION_INSTRUMENT="MNQ", SELECTION_ACTION="NOTHING",
        SELECTION_EV="direction=LONG;entry=100;stop=98;target=104;risk_points=2;reward_points=4;"
                     "friction_points=0;estimated_target_first_range=20%-30%;"
                     "breakeven_target_first=33.33%;now_ev=NEGATIVE;wait_price=99;"
                     "wait_ev=better price if reached;decisive_reason=Authored reason",
    )
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = "\n".join([
        DIRECT.TRIGGER_REVIEW_MARKER,
        *(f"{key}={value}" for key, value in values.items()),
    ])
    scenario["market"]["candidates"] = [{"instrument": "MNQ"}, {"instrument": "MES"}]
    DIRECT.normalize_batch(batch, scenario)
    return batch, scenario


@pytest.mark.parametrize("fields", [TRIGGER_SELECTION_FIELDS, ("SELECTION_EV",)])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_misplaced_trigger_selection_fields_are_lossless_and_idempotent(fields, newline):
    batch, scenario = trigger_selection_batch()
    audit = batch["decisions"][0]["decision_audit"]
    evidence = audit["decisive_evidence"]
    values = dict(line.split("=", 1) for line in evidence.splitlines()[1:])
    retained = [line for line in evidence.splitlines() if line.split("=", 1)[0] not in fields]
    audit["decisive_evidence"] = newline.join(retained)
    expected = copy.deepcopy(batch)
    expected["decisions"][0]["decision_audit"]["decisive_evidence"] = (
        audit["decisive_evidence"] + "".join(f"\n{key}={values[key]}" for key in fields)
    )
    for key in fields:
        audit[key] = values[key]
    DIRECT.normalize_batch(batch, scenario)
    assert batch == expected  # No changed choice, probability, level, route or wake trigger.
    DIRECT.validate_batch(batch, scenario)
    DIRECT.normalize_batch(batch, scenario)
    assert batch == expected


@pytest.mark.parametrize("field", TRIGGER_SELECTION_FIELDS)
def test_identical_trigger_selection_copy_collapses_but_conflict_stays_invalid(field):
    batch, scenario = trigger_selection_batch()
    expected = copy.deepcopy(batch)
    audit = batch["decisions"][0]["decision_audit"]
    values = dict(line.split("=", 1) for line in audit["decisive_evidence"].splitlines()[1:])
    audit[field] = values[field]
    DIRECT.normalize_batch(batch, scenario)
    assert batch == expected
    audit[field] = "Conflicting authored value"
    DIRECT.normalize_batch(batch, scenario)
    assert audit[field] == "Conflicting authored value"
    with pytest.raises(ValueError, match="decision_audit_contract_invalid"):
        DIRECT.validate_batch(batch, scenario)


@pytest.mark.parametrize("value", ["", None, {}, "first\nsecond", "first\rsecond"])
def test_invalid_trigger_selection_value_is_not_inferred(value):
    batch, scenario = trigger_selection_batch()
    audit = batch["decisions"][0]["decision_audit"]
    before = audit["decisive_evidence"]
    audit["ALTERNATIVE_CANDIDATES"] = value
    DIRECT.normalize_batch(batch, scenario)
    assert audit["decisive_evidence"] == before
    assert "ALTERNATIVE_CANDIDATES" in audit
    with pytest.raises(ValueError, match="decision_audit_contract_invalid"):
        DIRECT.validate_batch(batch, scenario)


def test_relocation_does_not_invent_missing_fields_or_change_other_modes():
    batch, scenario = trigger_selection_batch()
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = "\n".join(
        line for line in audit["decisive_evidence"].splitlines()
        if not line.startswith("ALTERNATIVE_CANDIDATES=")
    )
    DIRECT.normalize_batch(batch, scenario)
    with pytest.raises(ValueError, match="trigger_review_field_missing:0:ALTERNATIVE_CANDIDATES"):
        DIRECT.validate_batch(batch, scenario)
    for marker in ("ordinary evidence", DIRECT.CANDIDATE_COMPARISON_MARKER,
                   DIRECT.POSITION_MANAGEMENT_MARKER):
        audit["decisive_evidence"] = marker
        audit["ALTERNATIVE_CANDIDATES"] = "Authored value"
        DIRECT.normalize_batch(batch)
        assert audit["ALTERNATIVE_CANDIDATES"] == "Authored value"


def test_misplaced_trigger_fields_keep_entry_payload_unchanged():
    batch, scenario = trigger_selection_batch()
    intent = batch["decisions"][0]
    intent.update(action="ENTER_LONG", quantity=1, order_type="MARKET", stop_loss=98,
                  take_profit_1=104, entry_range_low=99.5, entry_range_high=100.5,
                  forecast={"event": "STOP_BEFORE_PRIMARY_TARGET", "probability": .4,
                            "method": "Authored estimate", "confidence": .5})
    audit = intent["decision_audit"]
    audit["final_choice"] = "ENTER_LONG"
    audit["decisive_evidence"] = audit["decisive_evidence"].replace(
        "SELECTION_ACTION=NOTHING", "SELECTION_ACTION=ENTER_LONG")
    DIRECT.normalize_batch(batch, scenario)
    expected = copy.deepcopy(batch)
    audit["SELECTION_ACTION"] = "ENTER_LONG"  # Identical misplaced duplicate.
    DIRECT.normalize_batch(batch, scenario)
    assert batch == expected
    audit["SELECTION_ACTION"] = "ENTER_SHORT"
    DIRECT.normalize_batch(batch, scenario)
    assert intent["action"] == "ENTER_LONG"
    assert audit["SELECTION_ACTION"] == "ENTER_SHORT"


def test_misplaced_trigger_fields_do_not_need_an_extra_model_call(monkeypatch):
    batch, scenario = trigger_selection_batch()
    audit = batch["decisions"][0]["decision_audit"]
    lines = audit["decisive_evidence"].splitlines()
    for line in lines:
        key, _, value = line.partition("=")
        if key in TRIGGER_SELECTION_FIELDS:
            audit[key] = value
    audit["decisive_evidence"] = "\n".join(
        line for line in lines if line.partition("=")[0] not in TRIGGER_SELECTION_FIELDS)
    calls = []

    def invoke(*args, **kwargs):
        calls.append(args)
        return copy.deepcopy(batch)

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    result, repairs, retries = DIRECT.invoke_validated_batch(
        "glitch", "offline fixture", scenario, None, 60, decision_mode="trigger_review")
    assert len(calls) == 1 and repairs == 0 and retries == 0
    assert result["decisions"][0]["action"] == "NOTHING"
