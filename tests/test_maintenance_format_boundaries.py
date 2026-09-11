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
    assert "not merely an intact thesis or unspecified future management" in skill
    assert "Before material favorable excursion" in skill
    assert "not make a red mark or one adverse bar an exit rule" in skill
