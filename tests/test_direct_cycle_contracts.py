import importlib.util
import json
import sys
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_direct_glitch_cycle",
    ROOT / "scripts" / "run-direct-glitch-cycle.py",
)
DIRECT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DIRECT)


def valid_batch(created_utc: str) -> tuple[dict, dict]:
    scenario = {
        "cycle_id": "cycle-1",
        "market": {"snapshot_hash": "snapshot-1"},
        "books": [{"route_id": "glitch", "master_account": "Sim101"}],
    }
    batch = {
        "schema_version": "glitch.intent.batch.v1",
        "cycle_id": "cycle-1",
        "next_review_seconds": 300,
        "decisions": [{
            "schema_version": "glitch.intent.v3",
            "intent_id": "intent-1",
            "created_utc": created_utc,
            "instrument": "MNQ",
            "account": "Sim101",
            "operator_profile": "glitch",
            "action": "NOTHING",
            "confidence": 0.5,
            "snapshot_hash": "snapshot-1",
            "model_version": "test-model",
            "prompt_version": "test-prompt",
            "reason": "No current edge.",
            "decision_audit": {
                "bull_case": "No decisive evidence.",
                "bear_case": "No decisive evidence.",
                "flat_case": "Wait for clearer evidence.",
                "aggressive_case": "Act now without confirmation.",
                "conservative_case": "Remain flat.",
                "decisive_evidence": "Current evidence favors waiting.",
                "disconfirming_evidence": "A material structure change.",
                "change_condition": "Review the next complete packet.",
                "final_choice": "NOTHING",
            },
            "wake_triggers": [],
        }],
    }
    return batch, scenario


def delivery_receipt(*bodies: dict) -> dict:
    return {
        "complete": True,
        "results": [
            {
                "intent_id": f"intent-{index}",
                "result": {"http_status": 200, "body": body},
            }
            for index, body in enumerate(bodies)
        ],
    }


def test_validator_canonicalizes_offset_bearing_created_utc() -> None:
    batch, scenario = valid_batch("2026-08-03T10:02:41.0414987+03:00")

    DIRECT.validate_batch(batch, scenario)

    assert batch["decisions"][0]["created_utc"] == "2026-08-03T07:02:41.0414987Z"


def test_supersession_reassessment_marker_is_validated_as_hermes_batch_metadata() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    batch["supersession_reassessment_requested"] = True

    DIRECT.validate_batch(batch, scenario)

    batch["supersession_reassessment_requested"] = "true"
    with pytest.raises(ValueError, match="supersession_reassessment_requested_invalid"):
        DIRECT.validate_batch(batch, scenario)


def test_normalize_wake_triggers_repairs_model_shape() -> None:
    batch, _ = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    intent["decision_audit"]["change_condition"] = "Reassess if price moves above 20100.5."
    intent["wake_triggers"] = [{"type": "PRICE_CROSS", "direction": "ABOVE", "price": 20100.5, "note": "model"}]

    DIRECT.normalize_batch(batch)

    assert intent["wake_triggers"] == [{
        "type": "PRICE_CROSS",
        "instrument": "MNQ",
        "direction": "ABOVE",
        "price": 20100.5,
    }]
    DIRECT.validate_batch(batch, {
        "cycle_id": "cycle-1",
        "market": {"snapshot_hash": "snapshot-1"},
        "books": [{"route_id": "glitch", "master_account": "Sim101"}],
    })


def test_normalize_wake_triggers_repairs_string_trigger() -> None:
    batch, _ = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    intent["wake_triggers"] = ["below 19900"]

    DIRECT.normalize_batch(batch)

    assert intent["wake_triggers"] == [{
        "type": "PRICE_CROSS",
        "instrument": "MNQ",
        "direction": "BELOW",
        "price": 19900.0,
    }]


def test_pending_normalization_defers_wake_repair_until_original_scenario() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    scenario["market"]["candidates"] = [
        {"instrument": "MES"},
        {"instrument": "MNQ"},
        {"instrument": "M2K"},
    ]
    intent = batch["decisions"][0]
    intent["instrument"] = "MES"
    intent["decision_audit"]["change_condition"] = (
        "Reassess MES below 7680.25 or MNQ above 29154.5."
    )
    intent["wake_triggers"] = []

    DIRECT.normalize_batch(batch, normalize_trigger_fields=False)
    assert intent["wake_triggers"] == []

    DIRECT.normalize_batch(batch, scenario)
    assert intent["wake_triggers"] == [
        {"type": "PRICE_CROSS", "instrument": "MES", "direction": "BELOW", "price": 7680.25},
        {"type": "PRICE_CROSS", "instrument": "MNQ", "direction": "ABOVE", "price": 29154.5},
    ]


def test_normalize_batch_relocates_misplaced_audit_wake_triggers() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    intent["decision_audit"]["wake_triggers"] = []

    DIRECT.normalize_batch(batch, scenario)

    assert intent["wake_triggers"] == []
    assert set(intent["decision_audit"]) == DIRECT.DECISION_AUDIT_FIELDS
    DIRECT.validate_batch(batch, scenario)


def test_normalize_batch_relocates_known_audit_fields_without_changing_evidence() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    audit = intent["decision_audit"]
    audit["decisive_evidence"] = (
        "INSTRUMENT_COMPARISON_V1\n"
        "SELECTION_REASON=Canonical model-authored reason."
    )
    audit["SELECTION_REASON"] = "Duplicated model-authored reason."
    intent["change_condition"] = audit.pop("change_condition")

    DIRECT.normalize_batch(batch, scenario)

    assert "SELECTION_REASON" not in audit
    assert (
        audit["decisive_evidence"]
        == "INSTRUMENT_COMPARISON_V1\nSELECTION_REASON=Canonical model-authored reason."
    )
    assert "change_condition" not in intent
    assert audit["change_condition"] == "Review the next complete packet."


def test_normalize_batch_relocates_paired_audit_tail_without_changing_values() -> None:
    batch, scenario = valid_batch("2026-09-02T22:12:08Z")
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = (
        "INSTRUMENT_COMPARISON_V1\n"
        "SELECTION_REASON=MNQ retains the strongest evidence. "
        "DISCONFIRMING_EVIDENCE=Completed acceptance below 29147.75 would invalidate the path. "
        "change_condition=Reassess MNQ below 29147.75 or above 29218.5."
    )
    audit.pop("disconfirming_evidence")
    audit.pop("change_condition")

    DIRECT.normalize_batch(batch, scenario)

    assert audit["decisive_evidence"] == (
        "INSTRUMENT_COMPARISON_V1\n"
        "SELECTION_REASON=MNQ retains the strongest evidence."
    )
    assert (
        audit["disconfirming_evidence"]
        == "Completed acceptance below 29147.75 would invalidate the path."
    )
    assert audit["change_condition"] == (
        "Reassess MNQ below 29147.75 or above 29218.5."
    )
    DIRECT.validate_batch(batch, scenario)


def test_normalize_batch_does_not_relocate_partial_audit_tail() -> None:
    batch, scenario = valid_batch("2026-09-02T22:12:08Z")
    audit = batch["decisions"][0]["decision_audit"]
    original_evidence = (
        "INSTRUMENT_COMPARISON_V1\n"
        "DISCONFIRMING_EVIDENCE=Model-authored contrary evidence. "
        "change_condition=Model-authored reassessment condition."
    )
    audit["decisive_evidence"] = original_evidence
    audit.pop("disconfirming_evidence")
    audit["change_condition"] = "Existing canonical condition."

    DIRECT.normalize_batch(batch, scenario)

    assert audit["decisive_evidence"] == original_evidence
    assert "disconfirming_evidence" not in audit
    assert audit["change_condition"] == "Existing canonical condition."


def test_normalize_batch_moves_misplaced_selection_reason_into_evidence() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    audit = batch["decisions"][0]["decision_audit"]
    audit["decisive_evidence"] = "INSTRUMENT_COMPARISON_V1"
    audit["SELECTION_REASON"] = "Model-authored comparative reason."

    DIRECT.normalize_batch(batch, scenario)

    assert "SELECTION_REASON" not in audit
    assert audit["decisive_evidence"].endswith(
        "SELECTION_REASON=Model-authored comparative reason."
    )


def test_decision_audit_contract_error_names_exact_missing_and_extra_fields() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    audit = batch["decisions"][0]["decision_audit"]
    audit.pop("bear_case")
    audit.pop("change_condition")
    audit["SELECTION_REASON"] = "Misnested reason."

    with pytest.raises(
        ValueError,
        match=(
            r"^decision_audit_contract_invalid:0:"
            r"missing=bear_case,change_condition:extra=SELECTION_REASON$"
        ),
    ):
        DIRECT.validate_batch(batch, scenario)


def test_normalize_batch_recovers_duplicate_reason_from_model_audit() -> None:
    batch, _ = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    intent.pop("reason")
    intent["decision_audit"]["decisive_evidence"] = (
        "INSTRUMENT_COMPARISON_V1\nSELECTION_REASON=Model-authored reason."
    )

    DIRECT.normalize_batch(batch)

    assert intent["reason"] == "Model-authored reason."


def test_extract_json_repairs_only_terminal_missing_decision_closer() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"final_choice":"NOTHING","wake_triggers":[]}]}]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")

    assert value["decisions"][0]["decision_audit"]["final_choice"] == "NOTHING"


def test_extract_json_repairs_prefixed_terminal_missing_decision_closer() -> None:
    malformed = (
        'Hermes response:\n'
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"final_choice":"NOTHING","wake_triggers":[]}]}]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")

    assert value["decisions"][0]["decision_audit"]["final_choice"] == "NOTHING"


def test_extract_json_repairs_decision_closer_before_misplaced_batch_wake_triggers() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","cycle_id":"cycle-1",'
        '"next_review_seconds":300,"decisions":[{"instrument":"M2K",'
        '"decision_audit":{"final_choice":"HOLD"}],"wake_triggers":[]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")
    DIRECT.normalize_batch(value)

    assert "wake_triggers" not in value
    assert value["decisions"][0]["decision_audit"]["final_choice"] == "HOLD"
    assert value["decisions"][0]["wake_triggers"] == []


def test_extract_json_removes_one_extra_terminal_decision_closer() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"final_choice":"NOTHING"},"wake_triggers":[]}}]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")

    assert value["decisions"][0]["decision_audit"]["final_choice"] == "NOTHING"
    assert value["decisions"][0]["wake_triggers"] == []


def test_extract_json_repairs_empty_wake_triggers_after_closed_sole_decision() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"decisive_evidence":"evidence"},'
        '"final_choice":"NOTHING"},"wake_triggers":[]}]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")
    DIRECT.normalize_batch(value)

    assert value["decisions"][0]["decision_audit"]["final_choice"] == "NOTHING"
    assert value["decisions"][0]["wake_triggers"] == []


def test_extract_json_repairs_terminal_labeled_audit_tail_without_rewriting_values() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"decisive_evidence":"INSTRUMENT_COMPARISON_V1'
        '\\nDISCONFIRMING_EVIDENCE=Authored counterevidence.'
        '\\nCHANGE_CONDITION=Authored condition.'
        '\\nfinal_choice":"NOTHING"},"wake_triggers":[]}]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")
    DIRECT.normalize_batch(value)
    audit = value["decisions"][0]["decision_audit"]

    assert audit["decisive_evidence"] == "INSTRUMENT_COMPARISON_V1"
    assert audit["disconfirming_evidence"] == "Authored counterevidence."
    assert audit["change_condition"] == "Authored condition."
    assert audit["final_choice"] == "NOTHING"


def test_extract_json_closes_decisive_evidence_before_complete_json_audit_tail() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"decisive_evidence":"INSTRUMENT_COMPARISON_V1'
        '\\nSELECTION_REASON=Authored reason.'
        '\\ndisconfirming_evidence":"Authored counterevidence.",'
        '"change_condition":"Authored condition.","final_choice":"NOTHING"},'
        '"wake_triggers":[]}]}'
    )

    value = DIRECT.extract_json(malformed, "glitch.intent.batch.v1")
    audit = value["decisions"][0]["decision_audit"]

    assert audit["decisive_evidence"].endswith("SELECTION_REASON=Authored reason.")
    assert audit["disconfirming_evidence"] == "Authored counterevidence."
    assert audit["change_condition"] == "Authored condition."
    assert audit["final_choice"] == "NOTHING"


def test_extract_json_does_not_assign_misplaced_wake_triggers_across_decisions() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"final_choice":"NOTHING"}},'
        '{"decision_audit":{"final_choice":"NOTHING"}},"wake_triggers":[]}]}'
    )

    with pytest.raises(json.JSONDecodeError):
        DIRECT.extract_json(malformed, "glitch.intent.batch.v1")


def test_normalize_batch_repairs_escaped_ledger_line_separators() -> None:
    batch, _ = valid_batch("2026-08-03T07:02:41.0414987Z")
    evidence = "POSITION_MANAGEMENT_V1\\nINSTRUMENT=M2K\\nHOLD_EV=POSITIVE"
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = evidence

    DIRECT.normalize_batch(batch)

    repaired = batch["decisions"][0]["decision_audit"]["decisive_evidence"]
    assert repaired.splitlines() == [
        "POSITION_MANAGEMENT_V1",
        "INSTRUMENT=M2K",
        "HOLD_EV=POSITIVE",
    ]
    assert "\\n" not in repaired


@pytest.mark.parametrize(
    "message",
    [
        "protection_updates_required:0",
        "position_management_instrument_mismatch:0",
    ],
)
def test_position_management_shape_errors_receive_one_contract_repair(message: str) -> None:
    assert DIRECT.retryable_model_contract_error(ValueError(message)) is True
    repair = DIRECT.contract_repair_prompt("prompt", {}, ValueError(message))
    assert "MOVE_STOP requires protection_updates" in repair


def test_invalid_position_management_action_does_not_receive_format_repair() -> None:
    assert DIRECT.retryable_model_contract_error(
        ValueError("position_management_action_invalid:0")
    ) is False


def test_incomplete_entry_geometry_receives_one_bounded_entry_repair() -> None:
    error = ValueError(
        "entry_geometry_evidence_incomplete:0:candidate_comparison:points"
    )
    context = {
        "candidates": [{"instrument": "MNQ", "current_decision_price": 20000.0}],
    }

    assert DIRECT.retryable_model_contract_error(error) is True
    repair = DIRECT.contract_repair_prompt("prompt", {}, error, context)
    assert repair.startswith("ENTRY_CONTRACT_CORRECTION_ONLY:")
    assert "add only the dimensions named by the error" in repair
    assert "one-contract stop dollars" in repair
    assert "state model/transport latency once without inventing a duration" in repair
    assert '"current_decision_price":20000.0' in repair


def test_entry_geometry_accepts_compact_atr_one_and_five_minute_notation() -> None:
    DIRECT.validate_entry_geometry_evidence(
        "ATR1m/5m 7.24/14.90 points; 81 ticks; $40.50 risk; latency priced once; "
        "stop is deeper than ordinary 5m excursion.",
        0,
        "candidate_comparison",
    )


def test_entry_geometry_does_not_confuse_eleven_and_fifteen_minute_atr_for_one_and_five() -> None:
    with pytest.raises(ValueError, match="horizon_noise"):
        DIRECT.validate_entry_geometry_evidence(
            "ATR11m/15m 7.24/14.90 points; 81 ticks; $40.50 risk; latency priced once.",
            0,
            "candidate_comparison",
        )


@pytest.mark.parametrize(
    "message",
    [
        "protected_market_entry_required:0",
        "entry_quantity_invalid:0",
        "entry_range_invalid:0",
        "entry_range_excludes_decision_price:0",
        "entry_range_geometry_invalid:0",
    ],
)
def test_repairable_entry_contract_errors_receive_bounded_context(message: str) -> None:
    context = {"valid_entry_quantities_for_all_books": [1, 2]}

    assert DIRECT.retryable_model_contract_error(ValueError(message)) is True
    repair = DIRECT.contract_repair_prompt("prompt", {}, ValueError(message), context)

    assert repair.startswith("ENTRY_CONTRACT_CORRECTION_ONLY:")
    assert "must not trigger market reassessment" in repair
    assert "never widen the stop or target" in repair
    assert '"valid_entry_quantities_for_all_books":[1,2]' in repair


def test_contract_repair_context_is_compact_authoritative_arithmetic_only() -> None:
    scenario = {
        "market": {"candidates": [{
            "instrument": "MNQ 09-26",
            "current_price": 20000.25,
            "instrument_economics": {
                "point_value_usd": 2.0,
                "tick_size": 0.25,
                "source": "ninjatrader_master_instrument",
            },
            "timeframe_bars": [
                {"minutes": 1, "indicators": {"atr": 8.0}},
                {"minutes": 5, "indicators": {"atr": 18.0}},
            ],
        }]},
        "books": [
            {"valid_entry_quantities": [1, 2, 3]},
            {"valid_entry_quantities": [1, 2]},
        ],
    }

    context = DIRECT.contract_repair_context(
        scenario,
        {"decisions": [{"instrument": "MNQ"}]},
    )

    assert context["effect"] == "contract_correction_facts_only_no_market_reassessment"
    assert context["required_entry_order_type"] == "MARKET"
    assert context["valid_entry_quantities_for_all_books"] == [1, 2]
    selected = context["candidates"]
    assert len(selected) == 1
    assert selected[0]["instrument"] == "MNQ"
    assert selected[0]["current_decision_price"] == 20000.25
    assert selected[0]["geometry"]["point_value_usd_per_point"] == 2.0
    assert selected[0]["geometry"]["tick_size_points"] == 0.25
    assert selected[0]["geometry"]["atr"] == {
        "1m": {"points": 8.0, "ticks": 32.0, "one_contract_usd": 16.0},
        "5m": {"points": 18.0, "ticks": 72.0, "one_contract_usd": 36.0},
    }
    assert "timeframe_bars" not in json.dumps(context)


def test_extract_json_does_not_repair_missing_semantic_value() -> None:
    malformed = (
        '{"schema_version":"glitch.intent.batch.v1","decisions":['
        '{"decision_audit":{"final_choice":}]}]}'
    )

    with pytest.raises(json.JSONDecodeError):
        DIRECT.extract_json(malformed, "glitch.intent.batch.v1")


def test_validator_rejects_compact_created_utc() -> None:
    batch, scenario = valid_batch("20260803T070241.0414980Z")

    with pytest.raises(ValueError, match=r"^intent_created_utc_invalid:0$"):
        DIRECT.validate_batch(batch, scenario)


def test_model_decisions_use_runtime_owned_created_utc() -> None:
    batch, _ = valid_batch("2000-01-01T00:00:00Z")

    DIRECT.stamp_decision_created_utc(batch)

    created = batch["decisions"][0]["created_utc"]
    assert created != "2000-01-01T00:00:00Z"
    assert datetime.fromisoformat(created.replace("Z", "+00:00")).date() == datetime.now(timezone.utc).date()


def test_runtime_owns_intent_transport_metadata() -> None:
    batch, scenario = valid_batch("2000-01-01T00:00:00Z")
    intent = batch["decisions"][0]
    for field in (
        "schema_version", "intent_id", "account", "operator_profile", "snapshot_hash"
    ):
        intent.pop(field)

    DIRECT.stamp_deterministic_intent_fields(batch, scenario)

    assert intent["schema_version"] == "glitch.intent.v3"
    assert intent["account"] == "Sim101"
    assert intent["operator_profile"] == "glitch"
    assert intent["snapshot_hash"] == "snapshot-1"
    uuid.UUID(intent["intent_id"])


def test_runtime_binds_position_management_to_the_native_instrument() -> None:
    batch, scenario = valid_batch("2000-01-01T00:00:00Z")
    book = scenario["books"][0]
    book["instrument_contexts"] = {
        "MNQ": {"current_signed_quantity": 1},
        "MES": {"current_signed_quantity": 0},
    }
    intent = batch["decisions"][0]
    intent["instrument"] = "MES"
    intent["action"] = "HOLD"
    intent["reason"] = "Preserve this model-authored judgment."
    intent["decision_audit"]["final_choice"] = "HOLD"
    intent["decision_audit"]["decisive_evidence"] = "\n".join([
        DIRECT.POSITION_MANAGEMENT_MARKER,
        "INSTRUMENT=MES 09-26",
        *(f"{field}={'HOLD' if field == 'SELECTION_ACTION' else 'HELD: model evidence' if field == 'CURRENT_SETUP' else 'model evidence'}"
          for field in DIRECT.POSITION_MANAGEMENT_FIELDS),
    ])

    DIRECT.stamp_deterministic_intent_fields(batch, scenario)

    assert intent["instrument"] == "MNQ"
    assert "INSTRUMENT=MNQ" in intent["decision_audit"]["decisive_evidence"]
    assert intent["action"] == "HOLD"
    assert intent["reason"] == "Preserve this model-authored judgment."
    DIRECT.validate_position_management(
        intent["decision_audit"]["decisive_evidence"], "MNQ", "HOLD", 0
    )


def test_position_management_validator_accepts_full_native_contract_name() -> None:
    evidence = "\n".join([
        DIRECT.POSITION_MANAGEMENT_MARKER,
        "INSTRUMENT=MNQ 09-26",
        *(f"{field}={'HOLD' if field == 'SELECTION_ACTION' else 'HELD: model evidence' if field == 'CURRENT_SETUP' else 'model evidence'}"
          for field in DIRECT.POSITION_MANAGEMENT_FIELDS),
    ])

    DIRECT.validate_position_management(evidence, "MNQ", "HOLD", 0)


def position_management_evidence(action: str, gross_hold_terminal_ev: str) -> str:
    values = {
        field: "model evidence" for field in DIRECT.POSITION_MANAGEMENT_FIELDS
    }
    values["CURRENT_SETUP"] = "HELD: model evidence"
    values["HOLD_EV"] = (
        "target_before_stop_probability_range=35%-50%;"
        "target_before_stop_break_even=15.79%;"
        f"gross_hold_terminal_ev={gross_hold_terminal_ev};"
        "reason=compare the same target-first event"
    )
    values["SELECTION_ACTION"] = action
    return "\n".join([
        DIRECT.POSITION_MANAGEMENT_MARKER,
        "INSTRUMENT=M2K",
        *(f"{field}={values[field]}" for field in DIRECT.POSITION_MANAGEMENT_FIELDS),
    ])


def test_position_management_rejects_the_observed_target_first_event_inversion() -> None:
    management_math = {
        "status": "complete",
        "hold_target_before_stop_break_even_probability": 0.15789474,
    }

    with pytest.raises(
        ValueError,
        match=r"^position_management_hold_ev_event_inversion:0:declared=NEGATIVE:expected=POSITIVE",
    ):
        DIRECT.validate_position_management(
            position_management_evidence("EXIT", "NEGATIVE"),
            "M2K",
            "EXIT",
            0,
            management_math,
        )


def test_position_management_consistency_check_never_chooses_the_action() -> None:
    management_math = {
        "status": "complete",
        "hold_target_before_stop_break_even_probability": 0.15789474,
    }

    DIRECT.validate_position_management(
        position_management_evidence("EXIT", "POSITIVE"),
        "M2K",
        "EXIT",
        0,
        management_math,
    )


def test_position_management_rejects_nonpositive_exit_while_thesis_is_held() -> None:
    management_math = {
        "status": "complete",
        "current_unrealized_pnl_usd": -12.5,
        "hold_target_before_stop_break_even_probability": 0.15789474,
    }

    with pytest.raises(
        ValueError,
        match=r"^position_management_nonpositive_exit_without_failure:0:",
    ):
        DIRECT.validate_position_management(
            position_management_evidence("EXIT", "POSITIVE"),
            "M2K",
            "EXIT",
            0,
            management_math,
        )


def test_position_management_allows_nonpositive_exit_after_model_owned_failure() -> None:
    management_math = {
        "status": "complete",
        "current_unrealized_pnl_usd": -12.5,
        "hold_target_before_stop_break_even_probability": 0.15789474,
    }
    evidence = position_management_evidence("EXIT", "POSITIVE").replace(
        "CURRENT_SETUP=HELD: model evidence",
        "CURRENT_SETUP=FAILED: accepted post-entry structure contradicted the entry path",
    )

    DIRECT.validate_position_management(
        evidence,
        "M2K",
        "EXIT",
        0,
        management_math,
    )


def test_position_thesis_error_receives_correction_only_repair() -> None:
    error = ValueError(
        "position_management_nonpositive_exit_without_failure:0:"
        "current_unrealized_pnl_usd=-12.50000000"
    )

    assert DIRECT.retryable_model_contract_error(error) is True
    repair = DIRECT.contract_repair_prompt("prompt", {}, error)
    assert repair.startswith("POSITION_THESIS_SELF_CONSISTENCY_CORRECTION_ONLY:")
    assert "A negative mark, one adverse bar, absent immediate follow-through" in repair
    assert "change action, final_choice, and SELECTION_ACTION together to HOLD" in repair


def test_position_management_rejects_an_unselected_verdict_placeholder() -> None:
    management_math = {
        "status": "complete",
        "hold_target_before_stop_break_even_probability": 0.15789474,
    }

    with pytest.raises(ValueError, match="position_management_hold_ev_verdict_invalid"):
        DIRECT.validate_position_management(
            position_management_evidence("EXIT", "POSITIVE|NEGATIVE|STRADDLES"),
            "M2K",
            "EXIT",
            0,
            management_math,
        )


def test_validate_batch_applies_native_management_math_to_positioned_response() -> None:
    batch, scenario = valid_batch("2026-09-02T02:30:24Z")
    scenario["books"][0]["instrument_contexts"] = {
        "M2K": {"current_signed_quantity": -1},
    }
    intent = batch["decisions"][0]
    intent["instrument"] = "M2K"
    intent["action"] = "EXIT"
    intent["decision_audit"]["decisive_evidence"] = position_management_evidence(
        "EXIT", "NEGATIVE"
    )
    intent["decision_audit"]["final_choice"] = "EXIT"
    active_trade_state = {"trades": [{
        "route_id": "glitch",
        "master_account": "Sim101",
        "instrument": "M2K",
        "deterministic_management_math": {
            "status": "complete",
            "hold_target_before_stop_break_even_probability": 0.15789474,
        },
    }]}

    with pytest.raises(ValueError, match="position_management_hold_ev_event_inversion"):
        DIRECT.validate_batch(
            batch,
            scenario,
            active_trade_state=active_trade_state,
        )


def test_native_gl1_protection_uses_authoritative_order_fields() -> None:
    account = {
        "positions": [{"instrument_root": "MNQ", "market_position": "Short", "quantity": 1}],
        "working_order_details": [
            {
                "instrument_root": "MNQ",
                "name": "GL1-command-HS0-LEG0",
                "order_type": "StopMarket",
                "quantity": 1,
                "filled": 0,
                "stop_price": 29569.75,
                "limit_price": 0,
                "leg_id": "LEG0",
                "oco": "OCO0",
            },
            {
                "instrument_root": "MNQ",
                "name": "GL1-command-HT0-LEG0",
                "order_type": "Limit",
                "quantity": 1,
                "filled": 0,
                "stop_price": 0,
                "limit_price": 29459.75,
                "leg_id": "LEG0",
                "oco": "OCO0",
            },
        ],
    }

    protection = DIRECT.owned_native_protection(
        account,
        29504.75,
        {"point_value_usd": 2.0, "tick_size": 0.25, "source": "ninjatrader"},
    )

    assert protection["coverage_complete"] is True
    assert {row["leg_id"] for row in protection["orders"]} == {"LEG0"}
    assert {row["limit_price"] for row in protection["orders"]} == {0, 29459.75}


def test_active_trade_state_uses_native_entry_time_and_preserves_bracket_geometry(tmp_path: Path) -> None:
    glitch_data = tmp_path / "GlitchData"
    exchange = tmp_path / "exchange"
    (glitch_data / "intents").mkdir(parents=True)
    native_entry_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    intent = {
        "intent_id": "11111111-1111-4111-8111-111111111111",
        "created_utc": "2000-01-01T00:00:00Z",
        "action": "ENTER_SHORT",
        "instrument": "MNQ",
        "account": "Sim101",
        "quantity": 1,
        "stop_loss": 29569.75,
        "take_profit_1": 29459.75,
        "decision_audit": {
            "disconfirming_evidence": "Accepted reclaim above 29569.75",
            "change_condition": "Review on accepted reclaim above 29560.00",
        },
    }
    (glitch_data / "intents" / "decisions.jsonl").write_text(
        json.dumps({"intent": intent}) + "\n", encoding="utf-8"
    )
    (glitch_data / "intents" / "executions.jsonl").write_text(
        json.dumps({
            "intent_id": intent["intent_id"],
            "code": "master_entry_submitted",
            "recorded_utc": native_entry_utc,
        }) + "\n",
        encoding="utf-8",
    )
    account = {
        "account": "Sim101",
        "positions": [{
            "instrument_root": "MNQ",
            "market_position": "Short",
            "quantity": 1,
            "average_price": 29534.75,
            "unrealized_pnl": 72.0,
        }],
        "working_order_details": [
            {
                "instrument_root": "MNQ",
                "name": "GL1-command-HS0-LEG0",
                "order_type": "StopMarket",
                "order_state": "Accepted",
                "quantity": 1,
                "filled": 0,
                "stop_price": 29569.75,
                "limit_price": 0,
                "leg_id": "LEG0",
                "oco": "OCO0",
            },
            {
                "instrument_root": "MNQ",
                "name": "GL1-command-HT0-LEG0",
                "order_type": "Limit",
                "order_state": "Working",
                "quantity": 1,
                "filled": 0,
                "stop_price": 0,
                "limit_price": 29459.75,
                "leg_id": "LEG0",
                "oco": "OCO0",
            },
        ],
    }
    packet = {"frames": [{"portfolio_snapshot": {"accounts": [account]}}]}
    scenario = {"books": [{
        "route_id": "glitch",
        "master_account": "Sim101",
        "instrument_contexts": {"MNQ": {
            "current_price": 29498.75,
            "point_value_usd": 2.0,
            "tick_size": 0.25,
        }},
    }]}

    state = DIRECT.active_trade_state(packet, scenario, glitch_data, exchange)
    trade = state["trades"][0]

    assert trade["entry_decision_utc"] == native_entry_utc
    assert trade["trade_age_seconds"] is not None and trade["trade_age_seconds"] < 10
    assert trade["entry_plans"][0]["disconfirming_evidence"] == "Accepted reclaim above 29569.75"
    assert trade["entry_plans"][0]["change_condition"] == "Review on accepted reclaim above 29560.00"
    assert trade["working_orders"][0]["stop_price"] == 29569.75
    assert trade["working_orders"][1]["limit_price"] == 29459.75
    support = trade["deterministic_management_math"]
    assert support["effect"] == "decision_support_only_no_execution_effect"
    assert support["decision_authority"] == "hermes"
    assert support["status"] == "complete"
    assert support["calculation_basis"].endswith("gross_before_incremental_execution_costs")
    assert support["aggregate_giveback_to_stop_usd"] == 142.0
    assert support["aggregate_remaining_reward_to_target_usd"] == 78.0
    assert support["hold_break_even_event"] == "TARGET_BEFORE_STOP"
    assert support["hold_target_before_stop_break_even_probability"] == 0.64545455
    assert support["hold_stop_before_target_maximum_probability"] == 0.35454545


def test_deterministic_management_math_supports_long_multileg_brackets() -> None:
    support = DIRECT.deterministic_management_math(
        "long",
        2,
        101.0,
        5.0,
        0.25,
        [
            {"role": "stop", "leg_id": "A", "remaining_quantity": 1, "stop_price": 98.0},
            {"role": "stop", "leg_id": "B", "remaining_quantity": 1, "stop_price": 99.0},
            {"role": "target", "leg_id": "A", "remaining_quantity": 1, "limit_price": 103.0},
            {"role": "target", "leg_id": "B", "remaining_quantity": 1, "limit_price": 105.0},
        ],
        10.0,
        30.0,
        -20.0,
    )

    assert support["status"] == "complete"
    assert support["aggregate_giveback_to_stop_usd"] == 25.0
    assert support["aggregate_remaining_reward_to_target_usd"] == 30.0
    assert support["hold_target_before_stop_break_even_probability"] == 0.45454545
    assert support["hold_stop_before_target_maximum_probability"] == 0.54545455
    assert support["rollback_from_peak_usd"] == 20.0
    assert support["profit_retained_fraction_of_peak"] == pytest.approx(1 / 3)


def test_active_trade_state_uses_native_pnl_implied_price_when_analytics_conflict(
    tmp_path: Path,
) -> None:
    glitch_data = tmp_path / "GlitchData"
    exchange = tmp_path / "exchange"
    (glitch_data / "intents").mkdir(parents=True)
    account = {
        "account": "Sim101",
        "positions": [{
            "instrument_root": "MNQ",
            "market_position": "Long",
            "quantity": 3,
            "average_price": 29508.916666666668,
            "unrealized_pnl": 2.0,
        }],
        "working_order_details": [
            {
                "instrument_root": "MNQ",
                "name": "Stop1",
                "order_type": "StopMarket",
                "order_state": "Accepted",
                "quantity": 3,
                "filled": 0,
                "stop_price": 29465.5,
                "limit_price": 0,
            },
            {
                "instrument_root": "MNQ",
                "name": "Target1",
                "order_type": "Limit",
                "order_state": "Working",
                "quantity": 3,
                "filled": 0,
                "stop_price": 0,
                "limit_price": 29711.25,
            },
        ],
    }
    packet = {"frames": [{
        "created_utc": "2026-08-28T16:36:00Z",
        "portfolio_snapshot": {"accounts": [account]},
    }]}
    scenario = {"books": [{
        "route_id": "glitch",
        "master_account": "Sim101",
        "instrument_contexts": {"MNQ": {
            "current_price": 29489.5,
            "point_value_usd": 2.0,
            "tick_size": 0.25,
        }},
    }]}

    trade = DIRECT.active_trade_state(packet, scenario, glitch_data, exchange)["trades"][0]
    support = trade["deterministic_management_math"]
    basis = support["price_basis"]

    assert basis["status"] == "complete"
    assert basis["selected_price_source"] == "native_position_unrealized_pnl_implied"
    assert basis["analytics_current_price"] == 29489.5
    assert basis["native_pnl_implied_price"] == pytest.approx(29509.25)
    assert basis["absolute_disagreement_ticks"] == 79.0
    assert basis["absolute_disagreement_usd"] == 118.5
    assert support["current_price"] == pytest.approx(29509.25)
    assert support["aggregate_giveback_to_stop_usd"] == 262.5
    assert support["aggregate_remaining_reward_to_target_usd"] == 1212.0


def test_position_management_price_basis_falls_back_without_native_inputs() -> None:
    basis = DIRECT.position_management_price_basis(
        "long", 1, None, None, 101.25, 5.0, 0.25
    )

    assert basis["status"] == "analytics_fallback"
    assert basis["selected_current_price"] == 101.25
    assert basis["selected_price_source"] == "analytics_market_snapshot"
    assert basis["native_pnl_implied_price"] is None


def test_deterministic_management_math_never_publishes_partial_break_even() -> None:
    support = DIRECT.deterministic_management_math(
        "long",
        2,
        101.0,
        5.0,
        0.25,
        [
            {"role": "stop", "leg_id": "A", "remaining_quantity": 1, "stop_price": 98.0},
            {"role": "target", "leg_id": "A", "remaining_quantity": 2, "limit_price": 103.0},
        ],
        0.0,
        0.0,
        0.0,
    )

    assert support["status"] == "incomplete"
    assert support["calculation_issues"] == ["stop_coverage_incomplete"]
    assert support["aggregate_giveback_to_stop_usd"] is None
    assert support["aggregate_remaining_reward_to_target_usd"] is None
    assert support["hold_target_before_stop_break_even_probability"] is None


def test_active_trade_state_starts_fresh_after_native_flat_boundary(tmp_path: Path) -> None:
    glitch_data = tmp_path / "GlitchData"
    exchange = tmp_path / "exchange"
    (glitch_data / "intents").mkdir(parents=True)
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True)
    old_entry = {
        "intent_id": "11111111-1111-4111-8111-111111111111",
        "created_utc": "2026-08-06T10:30:00Z",
        "action": "ENTER_LONG",
        "instrument": "MNQ",
        "account": "Sim101",
        "quantity": 1,
        "stop_loss": 29400,
        "take_profit_1": 29600,
    }
    new_entry = {
        "intent_id": "22222222-2222-4222-8222-222222222222",
        "created_utc": "2026-08-07T00:45:54Z",
        "action": "ENTER_LONG",
        "instrument": "MNQ",
        "account": "Sim101",
        "quantity": 1,
        "stop_loss": 29485.25,
        "take_profit_1": 29593,
    }
    old_hold = {
        "intent_id": "33333333-3333-4333-8333-333333333333",
        "created_utc": "2026-08-06T10:31:00Z",
        "action": "HOLD",
        "instrument": "MNQ",
        "account": "Sim101",
    }
    new_hold = {
        "intent_id": "44444444-4444-4444-8444-444444444444",
        "created_utc": "2026-08-07T00:47:00Z",
        "action": "HOLD",
        "instrument": "MNQ",
        "account": "Sim101",
    }
    future_exit = {
        "intent_id": "55555555-5555-4555-8555-555555555555",
        "created_utc": "2026-08-07T00:48:00Z",
        "action": "EXIT",
        "instrument": "MNQ",
        "account": "Sim101",
    }
    (glitch_data / "intents" / "decisions.jsonl").write_text(
        "".join(json.dumps({"intent": row}) + "\n" for row in (old_entry, old_hold, new_entry, new_hold, future_exit)),
        encoding="utf-8",
    )
    (glitch_data / "intents" / "executions.jsonl").write_text(
        "".join(json.dumps({
            "intent_id": row["intent_id"],
            "code": "master_entry_submitted",
            "recorded_utc": row["created_utc"],
        }) + "\n" for row in (old_entry, new_entry)),
        encoding="utf-8",
    )
    (glitch_data / "intents" / "hermes-trade-outcomes.jsonl").write_text(
        json.dumps({
            "intent_id": new_entry["intent_id"],
            "recorded_utc": "2026-08-07T00:48:00Z",
        }) + "\n",
        encoding="utf-8",
    )
    (supervisor / "active-trades.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.active_trade_state.v1",
        "recorded_utc": "2026-08-06T10:32:00Z",
        "trades": [{
            "master_account": "Sim101",
            "side": "long",
            "entry_decision_utc": old_entry["created_utc"],
            "entry_intent_ids": [old_entry["intent_id"]],
            "peak_unrealized_pnl_usd": 500,
            "trough_unrealized_pnl_usd": -100,
            "working_orders": [{"leg_id": "OLD-LEG"}],
        }],
    }), encoding="utf-8")
    account = {
        "account": "Sim101",
        "positions": [{
            "instrument_root": "MNQ",
            "market_position": "Long",
            "quantity": 1,
            "average_price": 29537.25,
            "unrealized_pnl": -54,
        }],
        "working_order_details": [{
            "instrument_root": "MNQ",
            "name": "GL1-new-HS0-NEW-LEG",
            "order_type": "StopMarket",
            "order_state": "Accepted",
            "quantity": 1,
            "filled": 0,
            "stop_price": 29485.25,
            "limit_price": 0,
            "leg_id": "NEW-LEG",
        }],
    }
    early_account = {
        **account,
        "positions": [{**account["positions"][0], "unrealized_pnl": 25}],
    }
    packet = {"frames": [
        {
            "created_utc": "2026-08-07T00:45:00Z",
            "portfolio_snapshot": {"accounts": [{"account": "Sim101", "positions": []}]},
        },
        {
            "created_utc": "2026-08-07T00:46:00Z",
            "portfolio_snapshot": {"accounts": [early_account]},
        },
        {
            "created_utc": "2026-08-07T00:47:00Z",
            "portfolio_snapshot": {"accounts": [account]},
        },
    ]}
    scenario = {"books": [{"route_id": "glitch", "master_account": "Sim101"}]}

    trade = DIRECT.active_trade_state(packet, scenario, glitch_data, exchange)["trades"][0]

    assert trade["entry_intent_ids"] == [new_entry["intent_id"]]
    assert trade["entry_plans"] == [{
        "intent_id": new_entry["intent_id"],
        "quantity": 1,
        "planned_stop": 29485.25,
        "planned_targets": [29593],
        "reason": None,
        "disconfirming_evidence": None,
        "change_condition": None,
    }]
    assert trade["entry_decision_utc"] == new_entry["created_utc"]
    assert trade["trade_age_seconds"] == 66
    assert trade["peak_unrealized_pnl_usd"] == 25
    assert trade["trough_unrealized_pnl_usd"] == -54
    assert [row["intent_id"] for row in trade["recent_management"]] == [new_hold["intent_id"]]


def test_active_trade_state_preserves_zero_peak_for_continuing_native_leg(tmp_path: Path) -> None:
    glitch_data = tmp_path / "GlitchData"
    exchange = tmp_path / "exchange"
    (glitch_data / "intents").mkdir(parents=True)
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True)
    entry = {
        "intent_id": "11111111-1111-4111-8111-111111111111",
        "created_utc": "2026-08-07T00:00:00Z",
        "action": "ENTER_LONG",
        "instrument": "MNQ",
        "account": "Sim101",
        "quantity": 1,
        "stop_loss": 29490,
        "take_profit_1": 29590,
    }
    (glitch_data / "intents" / "decisions.jsonl").write_text(
        json.dumps({"intent": entry}) + "\n", encoding="utf-8"
    )
    (glitch_data / "intents" / "executions.jsonl").write_text(
        json.dumps({
            "intent_id": entry["intent_id"],
            "code": "master_entry_submitted",
            "recorded_utc": entry["created_utc"],
        }) + "\n",
        encoding="utf-8",
    )
    (supervisor / "active-trades.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.active_trade_state.v1",
        "recorded_utc": "2026-08-07T00:10:00Z",
        "trades": [{
            "master_account": "Sim101",
            "side": "long",
            "entry_decision_utc": entry["created_utc"],
            "entry_intent_ids": [entry["intent_id"]],
            "peak_unrealized_pnl_usd": 0,
            "trough_unrealized_pnl_usd": -10,
            "working_orders": [{"leg_id": "SAME-LEG"}],
        }],
    }), encoding="utf-8")
    account = {
        "account": "Sim101",
        "positions": [{
            "instrument_root": "MNQ",
            "market_position": "Long",
            "quantity": 1,
            "average_price": 29550,
            "unrealized_pnl": -5,
        }],
        "working_order_details": [{
            "instrument_root": "MNQ",
            "name": "GL1-same-HS0-SAME-LEG",
            "order_type": "StopMarket",
            "order_state": "Accepted",
            "quantity": 1,
            "filled": 0,
            "stop_price": 29490,
            "limit_price": 0,
            "leg_id": "SAME-LEG",
        }],
    }
    packet = {"frames": [{
        "created_utc": "2026-08-07T00:11:00Z",
        "portfolio_snapshot": {"accounts": [account]},
    }]}
    scenario = {"books": [{"route_id": "glitch", "master_account": "Sim101"}]}

    trade = DIRECT.active_trade_state(packet, scenario, glitch_data, exchange)["trades"][0]

    assert trade["entry_intent_ids"] == [entry["intent_id"]]
    assert trade["peak_unrealized_pnl_usd"] == 0
    assert trade["trough_unrealized_pnl_usd"] == -10


def test_llm_activation_is_closed_during_cme_maintenance_and_weekend() -> None:
    # 17:30 ET Wednesday: daily maintenance.
    assert DIRECT.llm_maintenance_reason(
        datetime(2026, 8, 5, 21, 30, tzinfo=timezone.utc)
    ) == "maintenance_window"
    # 12:00 ET Saturday: weekend.
    assert DIRECT.llm_maintenance_reason(
        datetime(2026, 8, 8, 16, 0, tzinfo=timezone.utc)
    ) == "weekend"
    # 11:00 ET Wednesday: open.
    assert DIRECT.llm_maintenance_reason(
        datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)
    ) is None


def fresh_model_admission_packet() -> dict:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    market = {
        "fresh_instrument_count": 2,
        "instrument_count": 2,
        "coverage": [
            {"instrument_root": "MES", "is_fresh": True},
            {"instrument_root": "MNQ", "is_fresh": True},
        ],
        "instruments": [
            {"instrument": "MES", "timestamp_utc": now, "is_fresh": True, "timeframe_bars": []},
            {"instrument": "MNQ", "timestamp_utc": now, "is_fresh": True, "timeframe_bars": []},
        ],
    }
    frames = [{"market_snapshot": json.loads(json.dumps(market))} for _ in range(5)]
    frames[-1]["portfolio_snapshot"] = {
        "accounts": [{
            "account": "Sim101",
            "trading_window_valid": True,
            "trading_session_open": True,
        }],
    }
    return {
        "packet_id": "current",
        "window_close_utc": now,
        "frame_count": 5,
        "is_contiguous": True,
        "missing_minute_ids": [],
        "policy": {"snapshot_max_age_seconds": 300},
        "frames": frames,
    }


def write_model_admission_runtime(glitch_data: Path) -> None:
    state = glitch_data / "hermes" / "control-state.json"
    policy = glitch_data / "ai" / "policy.json"
    rail = glitch_data / "selfcheck" / "rail.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    policy.parent.mkdir(parents=True, exist_ok=True)
    rail.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"trading_paused": False}), encoding="utf-8")
    policy.write_text(json.dumps({
        "schema_version": "glitch.ai.policy.v2",
        "snapshot_max_age_seconds": 300,
        "profile_account_bindings": [],
        "instrument_allowlist": [],
        "account_allowlist": [],
        "blocked_sessions": [],
    }), encoding="utf-8")
    rail.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_bus": {"fresh_instrument_count": 2},
    }), encoding="utf-8")


def test_model_call_admission_requires_ai_native_open_session_and_complete_fresh_package(
    tmp_path: Path,
) -> None:
    write_model_admission_runtime(tmp_path)
    packet = fresh_model_admission_packet()
    open_time = datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc)

    assert DIRECT.model_call_admission_reason(tmp_path, packet, open_time) is None

    state = tmp_path / "hermes" / "control-state.json"
    state.write_text(json.dumps({"trading_paused": True}), encoding="utf-8")
    assert DIRECT.model_call_admission_reason(tmp_path, packet, open_time) == "ai_auto_off_or_scope_invalid"

    state.write_text(json.dumps({"trading_paused": False}), encoding="utf-8")
    packet["frames"][-1]["portfolio_snapshot"]["accounts"][0]["trading_session_open"] = False
    assert DIRECT.model_call_admission_reason(tmp_path, packet, open_time) == "market_session_closed"

    packet["frames"][-1]["portfolio_snapshot"]["accounts"][0]["trading_session_open"] = True
    packet["frames"][-1]["market_snapshot"]["coverage"][1]["is_fresh"] = False
    assert DIRECT.model_call_admission_reason(tmp_path, packet, open_time) == "stale_market_package"

    packet = fresh_model_admission_packet()
    weekend = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)
    assert DIRECT.model_call_admission_reason(tmp_path, packet, weekend) == "weekend"

    rail = tmp_path / "selfcheck" / "rail.json"
    rail.write_text(json.dumps({
        "created_utc": "2026-08-05T12:00:00Z",
        "feed_bus": {"fresh_instrument_count": 2},
    }), encoding="utf-8")
    assert DIRECT.model_call_admission_reason(tmp_path, packet, open_time) == "stale_feed_observation"


def test_direct_retry_rechecks_live_model_call_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid, scenario = valid_batch("2026-08-13T10:00:00Z")
    invalid["decisions"][0]["decision_audit"].pop("bear_case")
    model_calls = 0
    admission_calls = 0

    def invoke(*_args, **_kwargs):
        nonlocal model_calls
        model_calls += 1
        return invalid

    def admission():
        nonlocal admission_calls
        admission_calls += 1
        return None if admission_calls == 1 else "maintenance_window"

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    with pytest.raises(DIRECT.ModelCallDeferred, match="maintenance_window"):
        DIRECT.invoke_validated_batch(
            "glitch",
            "PROMPT",
            scenario,
            None,
            30,
            model_call_admission=admission,
        )

    assert model_calls == 1
    assert admission_calls == 2


def test_missing_market_timestamp_fails_closed() -> None:
    packet = {
        "policy": {"snapshot_max_age_seconds": 180},
        "frames": [{"market_snapshot": {
            "instruments": [{"instrument": "MNQ", "timeframe_bars": []}],
        }}],
    }
    assert DIRECT.market_snapshot_is_fresh(packet) is False


def test_feed_observation_does_not_depend_on_unrelated_native_connections(tmp_path: Path) -> None:
    rail = tmp_path / "selfcheck" / "rail.json"
    rail.parent.mkdir(parents=True)
    rail.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_bus": {"fresh_instrument_count": 1},
        "connection": {"all_accounts_connected": False, "account_count": 14, "connected_count": 7},
    }), encoding="utf-8")

    assert DIRECT.feed_observation_is_fresh(tmp_path) is True


def test_repeated_packet_fingerprint_ignores_rolling_identity() -> None:
    first = {"packet_id": "20260805T1500Z", "created_utc": "a", "frames": [{"x": 1}]}
    second = {"packet_id": "20260805T1501Z", "created_utc": "b", "frames": [{"x": 1}]}
    assert DIRECT.packet_fingerprint(first) == DIRECT.packet_fingerprint(second)


def test_selection_ev_positive_nothing_remains_observational() -> None:
    value = (
        "direction=LONG;entry=100;stop=95;target=110;risk_points=5;reward_points=10;"
        "friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=40-50%;"
        "now_ev=POSITIVE;wait_price=105;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    assert DIRECT.validate_selection_ev(value, "NOTHING", 0, "test") == [
        "selection_ev_nothing_positive:0:test"
    ]


def test_selection_ev_observes_numeric_gaps_then_canonicalizes_exact_math() -> None:
    value = (
        "direction=LONG;entry=100;stop=95;target=110;"
        "risk_points=approximately 5 points (20 ticks);reward_points=10 pts;"
        "friction_points=not material;breakeven_target_first=about 33.3%;"
        "estimated_target_first_range=40-50%;now_ev=NEGATIVE;wait_price=105;"
        "wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    observations = DIRECT.validate_selection_ev(value, "NOTHING", 0, "test")
    assert "selection_ev_numeric_invalid:0:test" in observations

    inconsistent = (
        "direction=LONG;entry=100;stop=95;target=110;risk_points=4;reward_points=9;"
        "friction_points=0.5;breakeven_target_first=25%;"
        "estimated_target_first_range=40-50%;now_ev=POSITIVE;wait_price=99;"
        "wait_ev=POSITIVE;decisive_reason=fixture"
    )
    canonical = DIRECT.canonicalize_selection_ev_math(inconsistent)
    fields = DIRECT._selection_ev_fields(canonical)

    assert fields["direction"] == "LONG"
    assert fields["entry"] == "100"
    assert fields["stop"] == "95"
    assert fields["target"] == "110"
    assert fields["risk_points"] == "5"
    assert fields["reward_points"] == "10"
    assert float(fields["breakeven_target_first"]) == pytest.approx(5.5 / 15)
    assert fields["now_ev"] == "POSITIVE"
    DIRECT.validate_selection_ev(canonical, "ENTER_LONG", 0, "test")


def test_selection_ev_forecast_range_and_verdict_remain_observational() -> None:
    value = (
        "direction=LONG;entry=100;stop=95;target=110;risk_points=5;reward_points=10;"
        "friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=40-50%;"
        "now_ev=POSITIVE;wait_price=105;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    forecast = {
        "event": "STOP_BEFORE_PRIMARY_TARGET",
        "probability": 0.55,
        "method": "fixture",
        "confidence": 0.7,
    }
    DIRECT.validate_selection_ev(value, "ENTER_LONG", 0, "test", forecast)

    observations = DIRECT.validate_selection_ev(
        value, "ENTER_LONG", 0, "test", {**forecast, "probability": 0.8}
    )
    assert "selection_ev_forecast_range_mismatch:0:test" in observations

    observations = DIRECT.validate_selection_ev(
        value.replace("40-50%", "20-30%"),
        "ENTER_LONG",
        0,
        "test",
        {**forecast, "probability": 0.75},
    )
    assert "selection_ev_verdict_range_mismatch:0:test" in observations


def test_selection_math_reconciles_levels_without_choosing_an_action() -> None:
    support = DIRECT.deterministic_selection_math(
        "direction=LONG;entry=100;stop=95;target=110;risk_points=4;reward_points=9;"
        "friction_points=0.5;breakeven_target_first=25%;estimated_target_first_range=40-50%;"
        "now_ev=POSITIVE;wait_price=99;wait_ev=POSITIVE;decisive_reason=fixture",
        {
            "event": "STOP_BEFORE_PRIMARY_TARGET",
            "probability": 0.8,
            "method": "fixture",
            "confidence": 0.7,
        },
    )

    assert support["effect"] == "decision_support_only_no_execution_effect"
    assert support["decision_authority"] == "hermes"
    assert support["computed_risk_points"] == 5
    assert support["computed_reward_points"] == 10
    assert support["computed_breakeven_target_first"] == pytest.approx(5.5 / 15)
    assert support["forecast_target_first_probability"] == pytest.approx(0.2)
    assert support["calculation_issues"] == [
        "declared_breakeven_mismatch",
        "declared_reward_mismatch",
        "declared_risk_mismatch",
        "forecast_range_mismatch",
    ]


@pytest.mark.parametrize(
    ("direction", "target", "wait_price"),
    (("LONG", 110, 110), ("SHORT", 90, 89)),
)
def test_selection_ev_observes_wait_that_claims_improvement_after_target(
    direction: str, target: float, wait_price: float
) -> None:
    value = (
        f"direction={direction};entry=100;stop={95 if direction == 'LONG' else 105};target={target};risk_points=5;reward_points=10;"
        "friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=20-30%;"
        f"now_ev=NEGATIVE;wait_price={wait_price};wait_ev=IMPROVES;decisive_reason=fixture"
    )
    assert "selection_ev_wait_consumes_target:0:test" in DIRECT.validate_selection_ev(
        value, "NOTHING", 0, "test"
    )


@pytest.mark.parametrize(
    ("direction", "wait_price"),
    (("LONG", 101), ("SHORT", 99)),
)
def test_selection_ev_observes_wait_that_worsens_entry(
    direction: str, wait_price: float
) -> None:
    value = (
        f"direction={direction};entry=100;stop={95 if direction == 'LONG' else 105};"
        f"target={110 if direction == 'LONG' else 90};risk_points=5;reward_points=10;"
        "friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=20-30%;"
        f"now_ev=NEGATIVE;wait_price={wait_price};wait_ev=IMPROVES;decisive_reason=fixture"
    )

    assert "selection_ev_wait_worsens_entry:0:test" in DIRECT.validate_selection_ev(
        value, "NOTHING", 0, "test"
    )


def test_selection_ev_direction_action_contradiction_remains_a_hard_gate() -> None:
    value = (
        "direction=SHORT;entry=100;stop=95;target=110;risk_points=5;reward_points=10;"
        "friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=40-50%;"
        "now_ev=POSITIVE;wait_price=105;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    with pytest.raises(ValueError, match="selection_ev_direction_action_mismatch") as error:
        DIRECT.validate_selection_ev(value, "ENTER_LONG", 0, "test")
    assert DIRECT.retryable_model_contract_error(error.value) is False


@pytest.mark.parametrize("supersession_direction", ["better_price", "targetward"])
def test_supersession_reassessment_request_carries_original_geometry(
    tmp_path: Path, supersession_direction: str,
) -> None:
    exchange = tmp_path / "exchange"
    better_price = supersession_direction == "better_price"
    batch = {
        "decisions": [{
            "action": "ENTER_SHORT",
            "instrument": "MNQ",
            "entry_revalidation": {
                "favorable_supersession": better_price,
                "reassessment_eligible": True,
                "supersession_direction": supersession_direction,
                "entry_range_low": 100,
                "entry_range_high": 101,
                "stop": 105,
                "target": 95,
                "source_price": 100.5,
                "latest_price": 101.25 if better_price else 99.75,
                "source_packet_id": "source",
                "latest_packet_id": "latest",
            },
        }],
    }
    assert DIRECT.maybe_request_supersession_reassessment(
        batch, exchange, {"packet_id": "source"}, {"packet_id": "latest"}
    ) is True
    request = DIRECT.read_json(exchange / "hermes" / "direct-cycle-request.json")
    assert request["kind"] == "entry_range_supersession"
    assert request["suppress_supersession_followup"] is True
    assert request["reassessment_context"]["target"] == 95
    assert request["reassessment_context"]["source_packet_id"] == "source"
    assert request["reassessment_context"]["supersession_direction"] == supersession_direction


def test_coalesced_request_claim_preserves_newer_launcher_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "exchange"
    marker = exchange / "hermes" / "direct-cycle-request.json"
    DIRECT.write_json_atomic(marker, {
        "schema_version": "glitch.hermes.direct_cycle_request.v1",
        "requested_utc": "2026-08-07T12:00:00Z",
    })
    original_read = DIRECT.read_json

    def read_and_publish_newer(path: Path, *args, **kwargs):
        value = original_read(path, *args, **kwargs)
        if ".claim-" in path.name:
            DIRECT.write_json_atomic(marker, {
                "schema_version": "glitch.hermes.direct_cycle_request.v1",
                "requested_utc": "2026-08-07T12:01:00Z",
            })
        return value

    monkeypatch.setattr(DIRECT, "read_json", read_and_publish_newer)

    claimed = DIRECT.consume_direct_cycle_request(exchange)

    assert claimed["requested_utc"] == "2026-08-07T12:00:00Z"
    assert original_read(marker)["requested_utc"] == "2026-08-07T12:01:00Z"


def test_entry_reassessment_waits_for_a_fresh_unused_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "exchange"
    packet_path = exchange / "glitch" / "latest-decision-packet.json"
    DIRECT.write_json_atomic(packet_path, {"packet_id": "cycle-used"})
    DIRECT.write_json_atomic(
        DIRECT.model_attempt_path(exchange, "cycle-used"),
        {"status": "completed"},
    )
    monkeypatch.setattr(DIRECT, "packet_is_current", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "market_snapshot_is_fresh", lambda _packet: True)
    request = {
        "schema_version": "glitch.hermes.direct_cycle_request.v1",
        "requested_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "kind": "entry_range_supersession",
        "reassessment_context": {"instrument": "MNQ", "latest_price": 100.0},
    }

    assert DIRECT.defer_reassessment_until_unused_packet(exchange, request) is True
    deferred = DIRECT.read_json(exchange / "hermes" / "direct-cycle-request.json")
    assert deferred["kind"] == "entry_range_supersession"
    assert deferred["reassessment_context"]["latest_price"] == 100.0


def test_submit_batch_canonicalizes_created_utc_at_wire_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    glitch_data = tmp_path / "GlitchData"
    exchange = tmp_path / "exchange"
    glitch_data.mkdir()
    (glitch_data / "telemetry.token").write_text("test-token", encoding="utf-8")
    posted: list[dict] = []

    def fake_post_intent(intent: dict, token: str) -> dict:
        posted.append(intent)
        assert token == "test-token"
        return {"http_status": 200, "body": {"executor": "completed"}}

    monkeypatch.setattr(DIRECT, "post_intent", fake_post_intent)
    batch = {
        "cycle_id": "cycle-1",
        "decisions": [{
            "intent_id": "intent-1",
            "created_utc": "2026-08-03T04:02:41.5-03:00",
            "entry_range_low": 99.5,
            "entry_range_high": 100.5,
            "position_revalidation": {"status": "accepted_current_position"},
            "wake_triggers": [],
            "forecast": {
                "event": "STOP_BEFORE_PRIMARY_TARGET",
                "probability": 0.4,
                "method": "test",
                "confidence": 0.6,
            },
        }],
    }

    DIRECT.submit_batch(batch, glitch_data, exchange)

    assert posted[0]["created_utc"] == "2026-08-03T07:02:41.5000000Z"
    assert "wake_triggers" not in posted[0]
    assert "forecast" not in posted[0]
    assert "position_revalidation" not in posted[0]
    assert posted[0]["entry_range_low"] == 99.5
    assert posted[0]["entry_range_high"] == 100.5


def test_native_economics_drive_risk_geometry() -> None:
    economics = DIRECT.resolve_instrument_economics({
        "instrument_economics": {
            "point_value_usd": 5.0,
            "tick_size": 0.25,
            "source": "ninjatrader_master_instrument",
        },
    })
    intent = {
        "action": "ENTER_LONG",
        "quantity": 1,
        "stop_loss": 19970.0,
        "take_profit_1": 20040.0,
    }

    legs = DIRECT.entry_risk_legs(intent, 20000.0, economics)

    assert economics["source"] == "ninjatrader_master_instrument"
    assert legs[0]["planned_risk_usd"] == 150.0


def test_deterministic_geometry_context_normalizes_contract_noise_without_ranking() -> None:
    context = DIRECT.deterministic_geometry_context({
        "instrument": "MNQ",
        "instrument_economics": {
            "point_value_usd": 2.0,
            "tick_size": 0.25,
            "source": "ninjatrader_master_instrument",
        },
        "timeframe_bars": [
            {
                "minutes": 1,
                "indicators": {"atr": 9.0},
                "descriptive_state": {
                    "descriptive_state": {
                        "liquidity": {"spread_points": 0.5},
                    },
                },
            },
            {"minutes": 5, "indicators": {"atr": 25.0}},
        ],
    })

    assert context["effect"] == "decision_support_only_no_execution_effect"
    assert context["decision_authority"] == "hermes"
    assert context["tick_value_usd"] == 0.5
    assert context["atr"]["1m"] == {
        "points": 9.0,
        "ticks": 36.0,
        "one_contract_usd": 18.0,
    }
    assert context["atr"]["5m"]["one_contract_usd"] == 50.0
    assert context["spread"]["one_contract_usd"] == 1.0
    assert "action" not in context
    assert "ranking" not in context
    assert "threshold" not in context


def test_forecast_is_validated_as_non_gating_metadata() -> None:
    DIRECT.validate_forecast(None, 0)
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    batch["decisions"][0]["forecast"] = {
        "event": "STOP_BEFORE_PRIMARY_TARGET",
        "probability": 0.4,
        "method": "bounded_path",
        "confidence": 0.7,
    }

    DIRECT.validate_batch(batch, scenario)

    assert batch["decisions"][0]["forecast"]["probability"] == 0.4

    batch["decisions"][0]["forecast"]["probability"] = 1.1
    with pytest.raises(ValueError, match=r"^forecast_probability_invalid:0$"):
        DIRECT.validate_batch(batch, scenario)


def test_packet_preserves_economics_and_removes_duplicate_observation_aliases() -> None:
    packet = {
        "policy": {},
        "frames": [{
            "market_snapshot": {
                "instruments": [{
                    "instrument": "MNQ",
                    "current_price": 20000.0,
                    "instrument_economics": {
                        "point_value_usd": 5.0,
                        "tick_size": 0.25,
                        "source": "ninjatrader_master_instrument",
                    },
                    "native_observations": {"duplicate": True},
                    "descriptive_state": {"duplicate": True},
                    "heuristic_projections": {"duplicate": True},
                    "timeframe_bars": [{
                        "minutes": 1,
                        "open": 1,
                        "high": 2,
                        "low": 0,
                        "close": 1,
                        "native_observations": {"duplicate": True},
                        "descriptive_state": {"flow": {"delta": 1}},
                        "derived_analytics": {"directional_score": 0.2},
                        "heuristic_projections": {"directional_score": 0.2},
                    }],
                }],
                "coverage": [],
            },
            "portfolio_snapshot": {"accounts": []},
        }],
    }
    scenario = {
        "books": [{
            "route_id": "glitch",
            "master_account": "Sim101",
            "followers": [],
        }],
    }

    result = DIRECT.packet_for_model(packet, scenario)
    instrument = result["frames"][0]["market_snapshot"]["instruments"][0]

    assert instrument["instrument_economics"]["point_value_usd"] == 5.0
    assert instrument["deterministic_geometry_context"]["effect"] == (
        "decision_support_only_no_execution_effect"
    )
    assert "native_observations" not in instrument
    assert "descriptive_state" not in instrument
    assert "heuristic_projections" not in instrument
    bar = instrument["timeframe_bars"][0]
    assert bar["descriptive_state"]["flow"]["delta"] == 1
    assert bar["derived_analytics"]["directional_score"] == 0.2
    assert "native_observations" not in bar
    assert "heuristic_projections" not in bar


def test_forecast_method_is_bounded_without_a_second_model_call() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    intent.update({
        "action": "ENTER_LONG",
        "forecast": {
            "event": "STOP_BEFORE_PRIMARY_TARGET",
            "probability": 0.4,
            "method": "evidence " * 40,
            "confidence": 0.6,
        },
    })

    DIRECT.normalize_batch(batch, scenario)

    assert len(intent["forecast"]["method"]) == 128


def test_flat_invocation_uses_exact_completed_five_minute_boundaries(tmp_path: Path) -> None:
    scenario = {"books": [{"master_account": "Sim101"}]}

    def packet_at(minute: int, quantity: int = 0) -> dict:
        return {
            "packet_id": f"20260813T12{minute:02d}Z",
            "window_close_utc": f"2026-08-13T12:{minute:02d}:00Z",
            "frames": [{"portfolio_snapshot": {"accounts": [{
                "account": "Sim101",
                "positions": [] if quantity == 0 else [{
                    "instrument_root": "MNQ",
                    "market_position": "Long",
                    "quantity": quantity,
                }],
            }]}}],
        }

    assert DIRECT.invocation_reason(packet_at(5), scenario, tmp_path, None) == "scheduled"
    assert DIRECT.invocation_reason(packet_at(6), scenario, tmp_path, None) is None
    assert DIRECT.invocation_reason(packet_at(6, 1), scenario, tmp_path, None) == "positioned"
    assert DIRECT.invocation_reason(packet_at(6), scenario, tmp_path, {"status": "pending"}) == "operator_directive"


def test_imminent_rollover_reads_the_next_packet_from_the_normal_cron_phase(
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc)
    old_time = now.timestamp() - 45
    old_utc = datetime.fromtimestamp(old_time, timezone.utc).isoformat().replace("+00:00", "Z")
    old = {
        "packet_id": "20260813T1205Z",
        "window_close_utc": old_utc,
        "created_utc": old_utc,
        "policy": {"snapshot_max_age_seconds": 180},
    }
    new = {
        **old,
        "packet_id": "20260813T1206Z",
        "window_close_utc": now.isoformat().replace("+00:00", "Z"),
        "created_utc": now.isoformat().replace("+00:00", "Z"),
    }
    packets = iter((old, new))
    monkeypatch.setattr(DIRECT, "read_json", lambda _path: next(packets))
    monkeypatch.setattr(DIRECT.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(DIRECT.time, "sleep", lambda _seconds: None)

    assert DIRECT.read_packet_after_imminent_rollover(Path("packet.json"), 20) is new


def test_scheduled_boundary_is_preserved_when_fresh_packet_rolls_one_minute(
    tmp_path: Path,
) -> None:
    scenario = {"books": [{"master_account": "Sim101"}]}
    old = {
        "packet_id": "20260813T1205Z",
        "window_close_utc": "2026-08-13T12:05:00Z",
    }
    new = {
        "packet_id": "20260813T1206Z",
        "window_close_utc": "2026-08-13T12:06:00Z",
        "frames": [{"portfolio_snapshot": {"accounts": [{
            "account": "Sim101", "positions": [],
        }]}}],
    }

    assert DIRECT.scheduled_boundary_crossed(old, new) is True
    assert DIRECT.invocation_reason(
        new,
        scenario,
        tmp_path,
        None,
        scheduled_due=True,
    ) == "scheduled"


def test_rollover_wait_is_not_allowed_for_unscheduled_flat_wake_checks(
    tmp_path: Path,
) -> None:
    scenario = {"books": [{"master_account": "Sim101"}]}

    def packet_at(minute: int, quantity: int = 0) -> dict:
        return {
            "packet_id": f"20260813T12{minute:02d}Z",
            "window_close_utc": f"2026-08-13T12:{minute:02d}:00Z",
            "frames": [{"portfolio_snapshot": {"accounts": [{
                "account": "Sim101",
                "positions": [] if quantity == 0 else [{
                    "instrument_root": "MNQ",
                    "market_position": "Long",
                    "quantity": quantity,
                }],
            }]}}],
        }

    assert DIRECT.packet_rollover_wait_allowed(packet_at(5), scenario, tmp_path) is True
    assert DIRECT.packet_rollover_wait_allowed(packet_at(6), scenario, tmp_path) is False
    assert DIRECT.packet_rollover_wait_allowed(packet_at(6, 1), scenario, tmp_path) is True


@pytest.mark.parametrize(
    ("cycle_request", "expected_wait"),
    [
        ({"kind": "scheduled"}, 20.0),
        ({"kind": "entry_range_supersession"}, 0.0),
    ],
)
def test_only_entry_reassessment_requests_bypass_scheduled_rollover_wait(
    tmp_path: Path,
    monkeypatch,
    cycle_request: dict,
    expected_wait: float,
) -> None:
    glitch_data = tmp_path / "GlitchData"
    exchange = tmp_path / "exchange"
    packet_path = exchange / "glitch" / "latest-decision-packet.json"
    packet_path.parent.mkdir(parents=True)
    packet = {
        "packet_id": "20260813T1205Z",
        "window_close_utc": "2026-08-13T12:05:00Z",
    }
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    monkeypatch.setattr(DIRECT, "trading_runtime_enabled", lambda _path: True)
    monkeypatch.setattr(DIRECT, "packet_is_current", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "pending_outbox", lambda _exchange: None)
    monkeypatch.setattr(DIRECT, "build_scenario", lambda _packet: {"books": []})
    monkeypatch.setattr(
        DIRECT,
        "packet_rollover_wait_allowed",
        lambda _packet, _scenario, _exchange: True,
    )

    class RolloverObserved(Exception):
        pass

    def observe_rollover(_path, wait_seconds, initial_packet):
        assert wait_seconds == expected_wait
        assert initial_packet == packet
        raise RolloverObserved

    monkeypatch.setattr(DIRECT, "read_packet_after_imminent_rollover", observe_rollover)

    with pytest.raises(RolloverObserved):
        DIRECT.run_once(
            SimpleNamespace(dry_run=False, packet_rollover_wait_seconds=20),
            glitch_data,
            exchange,
            direct_request=cycle_request,
        )


def test_held_trigger_nothing_gets_one_next_minute_full_followup(tmp_path: Path) -> None:
    exchange = tmp_path
    attempts = exchange / "hermes" / "model-attempts"
    outbox = exchange / "hermes" / "outbox"
    attempts.mkdir(parents=True)
    outbox.mkdir(parents=True)
    prior_cycle = "20260813T1206Z"
    (attempts / f"{prior_cycle}.json").write_text(json.dumps({
        "cycle_id": prior_cycle,
        "status": "completed",
        "decision_mode": "trigger_review",
        "invocation_reason": "condition_change",
    }), encoding="utf-8")
    (outbox / f"{prior_cycle}.json").write_text(json.dumps({
        "next_review_seconds": 60,
        "decisions": [{"action": "NOTHING"}],
    }), encoding="utf-8")
    packet = {
        "packet_id": "20260813T1207Z",
        "window_close_utc": "2026-08-13T12:07:00Z",
        "frames": [{"portfolio_snapshot": {"accounts": [{
            "account": "Sim101", "positions": [],
        }]}}],
    }
    scenario = {"books": [{"master_account": "Sim101"}]}

    assert DIRECT.condition_followup_due(exchange, packet) is True
    assert DIRECT.invocation_reason(packet, scenario, exchange, None) == "condition_followup"

    (attempts / "20260813T1207Z.json").write_text(json.dumps({
        "cycle_id": "20260813T1207Z",
        "status": "completed",
        "decision_mode": "flat_scan",
        "invocation_reason": "condition_followup",
    }), encoding="utf-8")
    later = {**packet, "packet_id": "20260813T1208Z", "window_close_utc": "2026-08-13T12:08:00Z"}
    assert DIRECT.condition_followup_due(exchange, later) is False

    scheduled_prior = "20260813T1209Z"
    (attempts / f"{scheduled_prior}.json").write_text(json.dumps({
        "cycle_id": scheduled_prior,
        "status": "completed",
        "decision_mode": "trigger_review",
        "invocation_reason": "condition_change",
    }), encoding="utf-8")
    (outbox / f"{scheduled_prior}.json").write_text(json.dumps({
        "next_review_seconds": 60,
        "decisions": [{"action": "NOTHING"}],
    }), encoding="utf-8")
    scheduled_followup = {
        **packet,
        "packet_id": "20260813T1210Z",
        "window_close_utc": "2026-08-13T12:10:00Z",
    }
    assert DIRECT.condition_followup_due(exchange, scheduled_followup) is True
    assert DIRECT.packet_rollover_wait_allowed(
        scheduled_followup, scenario, exchange
    ) is False


def test_condition_followup_does_not_rearm_decision_wake_triggers() -> None:
    assert DIRECT.decision_arms_wake_triggers("flat_scan", "scheduled") is True
    assert DIRECT.decision_arms_wake_triggers("flat_scan", "condition_followup") is False
    assert DIRECT.decision_arms_wake_triggers("trigger_review", "condition_change") is False


def test_human_override_flat_is_audited_as_superseded_no_op(tmp_path: Path) -> None:
    receipt = delivery_receipt({
        "executor": "failed",
        "executor_code": "group_exit_human_override_flat",
    })
    attempt_path = tmp_path / "hermes" / "model-attempts" / "cycle-1.json"
    attempt_path.parent.mkdir(parents=True)
    attempt_path.write_text(
        json.dumps({"schema_version": "glitch.hermes.model_attempt.v1", "status": "decision_ready"}),
        encoding="utf-8",
    )

    assert DIRECT.receipt_classification(receipt) == "superseded_no_op"
    assert "superseded_no_op" in DIRECT.COMPLETED_RECEIPT_CLASSIFICATIONS
    assert DIRECT.receipt_requires_new_packet_retry(receipt) is False

    DIRECT.mark_attempt_from_receipt(tmp_path, "cycle-1", receipt)

    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt["status"] == "completed"
    assert attempt["receipt_classification"] == "superseded_no_op"


def test_real_failure_takes_precedence_over_superseded_no_op() -> None:
    receipt = delivery_receipt(
        {
            "executor": "failed",
            "executor_code": "group_exit_human_override_flat",
        },
        {
            "executor": "failed",
            "executor_code": "opposite_position_exists",
        },
    )

    assert DIRECT.receipt_classification(receipt) == "terminal_rejection"
    assert DIRECT.receipt_requires_new_packet_retry(receipt) is True


def multibook_flat_scenario() -> dict:
    return {
        "cycle_id": "cycle-9",
        "market": {"snapshot_hash": "snapshot-9", "candidates": [{"instrument": "MNQ", "current_price": 105.0}]},
        "books": [
            {
                "route_id": "glitch",
                "master_account": "Sim101",
                "instrument_contexts": {"MNQ": {"current_signed_quantity": 0}},
            },
            {
                "route_id": "glitch-2",
                "master_account": "Sim301",
                "instrument_contexts": {"MNQ": {"current_signed_quantity": 0}},
            },
        ],
    }


def test_shared_flat_decision_expands_to_every_ordered_book() -> None:
    scenario = multibook_flat_scenario()
    batch, _ = valid_batch("2026-08-13T10:00:00Z")
    batch["cycle_id"] = "cycle-9"
    batch["decisions"][0]["snapshot_hash"] = "snapshot-9"

    expanded = DIRECT.expand_shared_flat_decision(batch, scenario)

    assert len(expanded["decisions"]) == 2
    assert [d["operator_profile"] for d in expanded["decisions"]] == ["glitch", "glitch-2"]
    assert [d["account"] for d in expanded["decisions"]] == ["Sim101", "Sim301"]
    assert len({d["intent_id"] for d in expanded["decisions"]}) == 2
    assert all(d["action"] == "NOTHING" for d in expanded["decisions"])
    assert (
        expanded["decisions"][0]["decision_audit"]
        == expanded["decisions"][1]["decision_audit"]
    )


def test_shared_flat_decision_expansion_requires_all_books_flat() -> None:
    scenario = multibook_flat_scenario()
    scenario["books"][1]["instrument_contexts"]["MNQ"]["current_signed_quantity"] = 1
    batch, _ = valid_batch("2026-08-13T10:00:00Z")

    assert len(DIRECT.expand_shared_flat_decision(batch, scenario)["decisions"]) == 1


def test_shared_flat_decision_expansion_ignores_multi_decision_output() -> None:
    scenario = multibook_flat_scenario()
    batch, _ = valid_batch("2026-08-13T10:00:00Z")
    batch["decisions"].append(dict(batch["decisions"][0]))

    assert len(DIRECT.expand_shared_flat_decision(batch, scenario)["decisions"]) == 2
    assert batch["decisions"][0]["account"] == "Sim101"


def comparison_ledger(sections: dict[str, list[str]]) -> str:
    lines = [DIRECT.CANDIDATE_COMPARISON_MARKER]
    for instrument, fields in sections.items():
        lines.append(f"INSTRUMENT {instrument}:")
        lines.extend(fields)
    lines.extend([
        "RANKING=MNQ > MES",
        "SELECTION_INSTRUMENT=MNQ",
        "SELECTION_ACTION=NOTHING",
        "SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=35-45%;now_ev=NEGATIVE;wait_price=5012;wait_ev=NEGATIVE;decisive_reason=fixture",
        "SELECTION_REASON=no candidate retains practical edge",
    ])
    return "\n".join(lines)


def test_nothing_selection_ev_arithmetic_mismatch_becomes_uncertain_without_changing_choice() -> None:
    batch, _ = valid_batch("2026-09-04T08:39:00Z")
    intent = batch["decisions"][0]
    original = (
        "SELECTION_EV=direction=SHORT;entry=29648;stop=29651.625;target=29629;"
        "risk_points=3.625;reward_points=19;friction_points=0.5;"
        "breakeven_target_first=0.17857143;estimated_target_first_range=0.35-0.45;"
        "now_ev=NEGATIVE;wait_price=29651.625;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    intent["decision_audit"]["decisive_evidence"] = original

    corrected = DIRECT.reconcile_nothing_selection_ev_verdict(batch)

    evidence = intent["decision_audit"]["decisive_evidence"]
    assert corrected == 1
    assert intent["action"] == "NOTHING"
    assert intent["decision_audit"]["final_choice"] == "NOTHING"
    assert "estimated_target_first_range=0.35-0.45" in evidence
    assert "now_ev=UNCERTAIN" in evidence
    assert evidence == original.replace("now_ev=NEGATIVE", "now_ev=UNCERTAIN")


def test_entry_selection_ev_arithmetic_mismatch_is_not_rewritten_or_admitted() -> None:
    batch, _ = valid_batch("2026-09-04T08:39:00Z")
    intent = batch["decisions"][0]
    intent["action"] = "ENTER_SHORT"
    intent["decision_audit"]["final_choice"] = "ENTER_SHORT"
    original = (
        "SELECTION_EV=direction=SHORT;entry=29648;stop=29651.625;target=29629;"
        "risk_points=3.625;reward_points=19;friction_points=0.5;"
        "breakeven_target_first=0.17857143;estimated_target_first_range=0.35-0.45;"
        "now_ev=NEGATIVE;wait_price=29651.625;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    intent["decision_audit"]["decisive_evidence"] = original

    corrected = DIRECT.reconcile_nothing_selection_ev_verdict(batch)

    assert corrected == 0
    assert intent["action"] == "ENTER_SHORT"
    assert intent["decision_audit"]["decisive_evidence"] == original


def test_normalize_batch_uses_valid_ledger_selection_as_serialized_instrument() -> None:
    complete = [f"{field}=supported evidence" for field in DIRECT.CANDIDATE_COMPARISON_FIELDS]
    batch, scenario = valid_batch("2026-08-13T10:00:00Z")
    scenario["market"]["candidates"] = [
        {"instrument": "MNQ", "current_price": 20000.0},
        {"instrument": "MES", "current_price": 5000.0},
    ]
    intent = batch["decisions"][0]
    intent["decision_audit"]["decisive_evidence"] = comparison_ledger({
        "MNQ": complete,
        "MES": complete,
    }).replace("RANKING=MNQ > MES", "RANKING=MES > MNQ").replace(
        "SELECTION_INSTRUMENT=MNQ", "SELECTION_INSTRUMENT=MES"
    )

    DIRECT.normalize_batch(batch, scenario)

    assert intent["instrument"] == "MES"
    DIRECT.validate_candidate_comparison(
        intent["decision_audit"]["decisive_evidence"],
        {"MNQ", "MES"},
        intent["instrument"],
        "NOTHING",
        0,
    )


def test_normalize_batch_does_not_accept_selection_outside_candidate_scope() -> None:
    complete = [f"{field}=supported evidence" for field in DIRECT.CANDIDATE_COMPARISON_FIELDS]
    batch, scenario = valid_batch("2026-08-13T10:00:00Z")
    scenario["market"]["candidates"] = [
        {"instrument": "MNQ", "current_price": 20000.0},
        {"instrument": "MES", "current_price": 5000.0},
    ]
    intent = batch["decisions"][0]
    intent["decision_audit"]["decisive_evidence"] = comparison_ledger({
        "MNQ": complete,
        "MES": complete,
    }).replace("SELECTION_INSTRUMENT=MNQ", "SELECTION_INSTRUMENT=NQ")

    DIRECT.normalize_batch(batch, scenario)

    assert intent["instrument"] == "MNQ"
    with pytest.raises(ValueError, match="candidate_comparison_selection_instrument_mismatch"):
        DIRECT.validate_candidate_comparison(
            intent["decision_audit"]["decisive_evidence"],
            {"MNQ", "MES"},
            intent["instrument"],
            "NOTHING",
            0,
        )


def test_flat_comparison_contract_is_compact_but_preserves_decision_dimensions() -> None:
    assert DIRECT.CANDIDATE_COMPARISON_FIELDS == (
        "CURRENT_AUCTION", "BULLISH_PATH", "BEARISH_PATH", "NEXT_TRANSITION",
        "PRIOR_TRIGGER_REVIEW", "FIVE_TO_TEN_BAR_FORECAST",
        "OBJECTIVE_INVALIDATION", "ENTRY_RANGE", "NOISE_AND_GEOMETRY", "ASYMMETRY",
    )
    assert DIRECT.TRIGGER_REVIEW_FIELDS == (
        "FIRED_TRIGGER", "PRIOR_TRIGGER_REVIEW", "CURRENT_AUCTION",
        "REMAINING_OBJECTIVE_INVALIDATION", "ENTRY_RANGE_NOISE_GEOMETRY",
        "ALTERNATIVE_CANDIDATES", "SELECTION_INSTRUMENT", "SELECTION_ACTION",
        "SELECTION_REASON",
    )


def test_missing_constant_prior_trigger_review_is_backfilled() -> None:
    complete = [f"{field}=supported evidence" for field in DIRECT.CANDIDATE_COMPARISON_FIELDS]
    omitted = [
        f"{field}=supported evidence"
        for field in DIRECT.CANDIDATE_COMPARISON_FIELDS
        if field != "PRIOR_TRIGGER_REVIEW"
    ]
    batch, _ = valid_batch("2026-08-13T10:00:00Z")
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = comparison_ledger(
        {"MNQ": complete, "MES": omitted}
    )

    DIRECT.backfill_constant_comparison_fields(batch)

    evidence = batch["decisions"][0]["decision_audit"]["decisive_evidence"]
    assert evidence.count("PRIOR_TRIGGER_REVIEW=") == 2
    assert "PRIOR_TRIGGER_REVIEW=NOT_APPLICABLE" in evidence
    assert evidence.count("PRIOR_TRIGGER_REVIEW=supported evidence") == 1
    DIRECT.validate_candidate_comparison(evidence, ["MNQ", "MES"], "MNQ", "NOTHING", 0)

    DIRECT.backfill_constant_comparison_fields(batch)
    assert evidence == batch["decisions"][0]["decision_audit"]["decisive_evidence"]


def test_backfill_never_touches_semantic_fields_or_non_comparison_evidence() -> None:
    batch, _ = valid_batch("2026-08-13T10:00:00Z")
    original = batch["decisions"][0]["decision_audit"]["decisive_evidence"]

    DIRECT.backfill_constant_comparison_fields(batch)

    assert batch["decisions"][0]["decision_audit"]["decisive_evidence"] == original


def test_empty_model_stdout_is_retried_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            raise DIRECT.EmptyModelResponseError("hermes_stdout_empty")
        batch, _ = valid_batch("2026-08-13T10:00:00Z")
        return batch

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    scenario = {
        "cycle_id": "cycle-1",
        "market": {"snapshot_hash": "snapshot-1"},
        "books": [{"route_id": "glitch", "master_account": "Sim101"}],
    }

    batch, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch", "PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    assert calls == ["PROMPT", "PROMPT"]
    assert output_repair_count == 0
    assert transport_retry_count == 1
    assert batch["decisions"][0]["action"] == "NOTHING"

    calls.clear()

    def always_empty(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        raise DIRECT.EmptyModelResponseError("hermes_stdout_empty")

    monkeypatch.setattr(DIRECT, "invoke_hermes", always_empty)
    with pytest.raises(DIRECT.EmptyModelResponseError):
        DIRECT.invoke_validated_batch(
            "glitch", "PROMPT", scenario, None, 30, decision_mode="flat_scan"
        )
    assert len(calls) == 2


def test_invalid_contract_is_retried_once_without_reconsidering_cognition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid, scenario = valid_batch("2026-08-13T10:00:00Z")
    invalid["decisions"][0]["decision_audit"].pop("bear_case")
    valid, _ = valid_batch("2026-08-13T10:00:00Z")
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        return invalid if len(calls) == 1 else valid

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)

    batch, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    assert batch["decisions"][0]["action"] == "NOTHING"
    assert output_repair_count == 1
    assert transport_retry_count == 0
    assert len(calls) == 2
    assert calls[1].startswith("FORMAT_CORRECTION_ONLY:")
    assert "ORIGINAL_PROMPT" not in calls[1]
    assert "Preserve the same market judgment" in calls[1]


def test_nothing_ev_verdict_mismatch_is_reconciled_without_model_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, scenario = valid_batch("2026-09-04T08:39:00Z")
    intent = first["decisions"][0]
    intent["decision_audit"]["decisive_evidence"] = (
        "SELECTION_EV=direction=SHORT;entry=29648;stop=29651.625;target=29629;"
        "risk_points=3.625;reward_points=19;friction_points=0.5;"
        "breakeven_target_first=0.17857143;estimated_target_first_range=0.35-0.45;"
        "now_ev=NEGATIVE;wait_price=29651.625;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        return first

    def validate(batch, *_args, **_kwargs):
        evidence = batch["decisions"][0]["decision_audit"]["decisive_evidence"]
        selection_ev = evidence.removeprefix("SELECTION_EV=")
        return DIRECT.validate_selection_ev(
            selection_ev,
            batch["decisions"][0]["action"],
            0,
            "candidate_comparison",
        )

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    monkeypatch.setattr(DIRECT, "validate_batch", validate)

    batch, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    assert calls == ["ORIGINAL_PROMPT"]
    assert output_repair_count == 0
    assert transport_retry_count == 0
    assert batch["decisions"][0]["action"] == "NOTHING"
    assert "now_ev=UNCERTAIN" in batch["decisions"][0]["decision_audit"]["decisive_evidence"]


def test_selection_ev_contradiction_gets_one_same_evidence_consistency_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, scenario = valid_batch("2026-09-03T16:15:00Z")
    scenario["market"]["candidates"] = [{
        "instrument": "MNQ",
        "current_price": 20000.25,
        "instrument_economics": {"point_value_usd": 2.0, "tick_size": 0.25},
    }]
    scenario["books"][0]["valid_entry_quantities"] = [1, 2]
    corrected = json.loads(json.dumps(first))
    corrected["decisions"][0]["reason"] = "Probability estimate corrected from the same evidence."
    calls: list[str] = []
    validations = 0

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        return first if len(calls) == 1 else corrected

    def validate(*_args, **_kwargs):
        nonlocal validations
        validations += 1
        return (
            ["selection_ev_verdict_range_mismatch:0:candidate_comparison"]
            if validations == 1 else []
        )

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    monkeypatch.setattr(DIRECT, "validate_batch", validate)

    batch, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    assert batch["decisions"][0]["reason"].startswith("Probability estimate corrected")
    assert output_repair_count == 1
    assert transport_retry_count == 0
    assert len(calls) == 2
    assert calls[1].startswith("SELECTION_EV_SELF_CONSISTENCY_CORRECTION_ONLY:")
    assert "ORIGINAL_PROMPT" not in calls[1]
    assert "code has not chosen an action" in calls[1]
    assert "Payoff ratio or break-even alone does not prove edge" in calls[1]
    assert "evidence-derived estimated target-first range" in calls[1]
    assert "must not originate or strengthen an entry" in calls[1]
    assert "For selection_ev_forecast_range_mismatch" in calls[1]
    assert "selection_ev_nothing_positive" in calls[1]
    assert "use NOTHING" in calls[1]
    assert "when the whole preserved range is below exact break-even" in calls[1]
    assert "A later fresh full-evidence cycle may choose an entry" in calls[1]
    assert "does not estimate probability or select a new setup" in calls[1]
    assert "Do not raise or lower the range" in calls[1]
    assert "this repair has no current market evidence" in calls[1]
    assert '"current_decision_price":20000.25' in calls[1]
    assert '"valid_entry_quantities_for_all_books":[1,2]' in calls[1]


def test_selection_consistency_repair_cannot_originate_or_strengthen_entry() -> None:
    previous, _ = valid_batch("2026-09-03T16:15:00Z")
    repaired = json.loads(json.dumps(previous))
    repaired["decisions"][0]["action"] = "ENTER_LONG"

    with pytest.raises(ValueError, match="selection_ev_repair_entry_admission_forbidden:0"):
        DIRECT.enforce_selection_repair_boundary(
            previous,
            repaired,
            ValueError("selection_ev_nothing_positive:0:candidate_comparison"),
        )

    previous["decisions"][0]["action"] = "ENTER_LONG"
    with pytest.raises(ValueError, match="selection_ev_repair_entry_admission_forbidden:0"):
        DIRECT.enforce_selection_repair_boundary(
            previous,
            repaired,
            ValueError("selection_ev_entry_not_positive:0:candidate_comparison"),
        )


def test_forecast_only_repair_may_preserve_but_not_originate_entry() -> None:
    previous, _ = valid_batch("2026-09-03T16:15:00Z")
    repaired = json.loads(json.dumps(previous))
    repaired["decisions"][0]["action"] = "ENTER_LONG"

    with pytest.raises(ValueError, match="selection_ev_repair_entry_admission_forbidden:0"):
        DIRECT.enforce_selection_repair_boundary(
            previous,
            repaired,
            ValueError("selection_ev_forecast_range_mismatch:0:candidate_comparison"),
        )

    previous["decisions"][0]["action"] = "ENTER_LONG"
    DIRECT.enforce_selection_repair_boundary(
        previous,
        repaired,
        ValueError("selection_ev_forecast_range_mismatch:0:candidate_comparison"),
    )

    repaired["decisions"][0]["action"] = "ENTER_SHORT"
    with pytest.raises(ValueError, match="selection_ev_repair_entry_admission_forbidden:0"):
        DIRECT.enforce_selection_repair_boundary(
            previous,
            repaired,
            ValueError("selection_ev_forecast_range_mismatch:0:candidate_comparison"),
        )


def test_selection_consistency_retry_enforces_non_entry_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous, scenario = valid_batch("2026-09-03T16:15:00Z")
    promoted = json.loads(json.dumps(previous))
    promoted["decisions"][0]["action"] = "ENTER_LONG"
    calls = 0
    validations = 0

    def invoke(_profile, _prompt, _timeout, **_kwargs):
        nonlocal calls
        calls += 1
        return previous if calls == 1 else promoted

    def validate(*_args, **_kwargs):
        nonlocal validations
        validations += 1
        return (
            ["selection_ev_forecast_range_mismatch:0:candidate_comparison"]
            if validations == 1 else []
        )

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    monkeypatch.setattr(DIRECT, "validate_batch", validate)

    with pytest.raises(ValueError, match="selection_ev_repair_entry_admission_forbidden:0"):
        DIRECT.invoke_validated_batch(
            "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
        )


def test_selection_ev_consistency_retry_does_not_accept_a_second_contradiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid, scenario = valid_batch("2026-09-03T16:15:00Z")

    monkeypatch.setattr(DIRECT, "invoke_hermes", lambda *_args, **_kwargs: invalid)
    monkeypatch.setattr(
        DIRECT,
        "validate_batch",
        lambda *_args, **_kwargs: [
            "selection_ev_nothing_positive:0:candidate_comparison"
        ],
    )

    with pytest.raises(ValueError, match="selection_ev_nothing_positive"):
        DIRECT.invoke_validated_batch(
            "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
        )


def test_other_selection_math_observations_remain_non_gating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch, scenario = valid_batch("2026-09-03T16:15:00Z")
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        return batch

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)
    monkeypatch.setattr(
        DIRECT,
        "validate_batch",
        lambda *_args, **_kwargs: [
            "selection_ev_arithmetic_mismatch:0:candidate_comparison"
        ],
    )

    _, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    assert calls == ["ORIGINAL_PROMPT"]
    assert output_repair_count == 0
    assert transport_retry_count == 0


def test_position_management_event_inversion_gets_one_bounded_consistency_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid, scenario = valid_batch("2026-09-02T02:30:24Z")
    scenario["books"][0]["instrument_contexts"] = {
        "M2K": {"current_signed_quantity": -1},
    }
    intent = invalid["decisions"][0]
    intent["instrument"] = "M2K"
    intent["action"] = "EXIT"
    intent["decision_audit"]["decisive_evidence"] = position_management_evidence(
        "EXIT", "NEGATIVE"
    )
    intent["decision_audit"]["final_choice"] = "EXIT"
    corrected = json.loads(json.dumps(invalid))
    corrected["decisions"][0]["decision_audit"]["decisive_evidence"] = (
        position_management_evidence("EXIT", "POSITIVE")
    )
    active_trade_state = {"trades": [{
        "route_id": "glitch",
        "master_account": "Sim101",
        "instrument": "M2K",
        "deterministic_management_math": {
            "status": "complete",
            "hold_target_before_stop_break_even_probability": 0.15789474,
        },
    }]}
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        return invalid if len(calls) == 1 else corrected

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)

    batch, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch",
        "ORIGINAL_PROMPT",
        scenario,
        None,
        30,
        decision_mode="position_management",
        active_trade_state=active_trade_state,
    )

    assert batch["decisions"][0]["action"] == "EXIT"
    assert output_repair_count == 1
    assert transport_retry_count == 0
    assert len(calls) == 2
    assert calls[1].startswith("POSITION_MANAGEMENT_SELF_CONSISTENCY_CORRECTION_ONLY:")
    assert "Do not make a new market judgment" in calls[1]
    assert "minimum P(TARGET_BEFORE_STOP)" in calls[1]
    assert "only where the corrected event meaning requires it" in calls[1]


def test_contract_retry_uses_the_pristine_model_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid, scenario = valid_batch("2026-08-13T10:00:00Z")
    intent = invalid["decisions"][0]
    for field in (
        "schema_version", "intent_id", "created_utc", "account", "operator_profile",
        "snapshot_hash", "model_version", "prompt_version",
    ):
        intent.pop(field)
    intent["decision_audit"].pop("bear_case")
    valid, _ = valid_batch("2026-08-13T10:00:00Z")
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        return invalid if len(calls) == 1 else valid

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)

    DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    repaired_prompt = calls[1]
    previous_response = repaired_prompt.split("\nPREVIOUS_RESPONSE=", 1)[1]
    assert '"account"' not in previous_response
    assert '"intent_id"' not in previous_response
    assert '"snapshot_hash"' not in previous_response
    assert "account" not in intent
    assert "intent_id" not in intent
    assert "snapshot_hash" not in intent


def test_unparseable_model_output_gets_one_contract_only_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid, scenario = valid_batch("2026-08-13T10:00:00Z")
    calls: list[str] = []

    def invoke(_profile, prompt, _timeout, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            cause = json.JSONDecodeError("missing closer", "{", 1)
            raise DIRECT.InvalidModelResponseError("BROKEN_RESPONSE", cause)
        return valid

    monkeypatch.setattr(DIRECT, "invoke_hermes", invoke)

    batch, output_repair_count, transport_retry_count = DIRECT.invoke_validated_batch(
        "glitch", "ORIGINAL_PROMPT", scenario, None, 30, decision_mode="flat_scan"
    )

    assert batch["decisions"][0]["action"] == "NOTHING"
    assert output_repair_count == 1
    assert transport_retry_count == 0
    assert len(calls) == 2
    assert "PREVIOUS_RESPONSE=BROKEN_RESPONSE" in calls[1]


def test_visual_context_is_reused_for_empty_transport_but_not_contract_repair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "market.png"
    image.write_bytes(b"png")
    valid, scenario = valid_batch("2026-08-13T10:00:00Z")
    attached: list[Path | None] = []

    def empty_then_valid(_profile, _prompt, _timeout, **kwargs):
        attached.append(kwargs.get("image_path"))
        if len(attached) == 1:
            raise DIRECT.EmptyModelResponseError("hermes_stdout_empty")
        return valid

    monkeypatch.setattr(DIRECT, "invoke_hermes", empty_then_valid)
    DIRECT.invoke_validated_batch(
        "glitch", "PROMPT", scenario, None, 30,
        decision_mode="flat_scan", image_path=image,
    )
    assert attached == [image, image]

    invalid, _ = valid_batch("2026-08-13T10:00:00Z")
    invalid["decisions"][0]["decision_audit"].pop("bear_case")
    attached.clear()

    def invalid_then_valid(_profile, _prompt, _timeout, **kwargs):
        attached.append(kwargs.get("image_path"))
        return invalid if len(attached) == 1 else valid

    monkeypatch.setattr(DIRECT, "invoke_hermes", invalid_then_valid)
    DIRECT.invoke_validated_batch(
        "glitch", "PROMPT", scenario, None, 30,
        decision_mode="flat_scan", image_path=image,
    )
    assert attached == [image, None]


def test_native_hermes_invocation_receives_one_image_argument(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    hermes = tmp_path / "hermes.exe"
    python = tmp_path / "python.exe"
    image = tmp_path / "market.png"
    for path in (hermes, python, image):
        path.write_bytes(b"fixture")
    completed = SimpleNamespace(returncode=0, stdout="{}", stderr="")
    calls = []

    monkeypatch.setattr(DIRECT.shutil, "which", lambda _name: str(hermes))
    monkeypatch.setattr(DIRECT, "resolve_python_invocation", lambda value: (value, {}))
    monkeypatch.setattr(DIRECT, "hermes_profile_lock", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(DIRECT.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)) or completed)
    monkeypatch.setattr(DIRECT, "extract_json", lambda *_args, **_kwargs: {"schema_version": "glitch.intent.batch.v1"})

    DIRECT.invoke_hermes("glitch", "PROMPT", 30, image_path=image)

    wrapper = calls[0][0][0][2]
    assert "'--image'" in wrapper
    assert repr(str(image)) in wrapper
    assert calls[0][1]["input"] == "PROMPT"


def test_market_perception_failure_is_observational_and_fail_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import market_structure

    def fail(*_args, **_kwargs):
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(market_structure, "build_market_perception", fail)
    packet = {"packet_id": "20260901T0100Z"}
    scenario = {"books": []}
    value, image = DIRECT.market_perception_context(
        packet, tmp_path, scenario, {"trades": []}, "flat_scan"
    )

    assert image is None
    assert value["status"] == "unavailable"
    assert value["decision_continues_from_authoritative_numeric_packet"] is True
    assert value["effect"] == "observation_only_no_execution_or_admission_effect"


def test_compacted_bars_preserve_native_completed_bar_without_relabeling_current_bar() -> None:
    packet = {
        "packet_id": "20260813T1009Z",
        "window_close_utc": "2026-08-13T10:09:00.0000000Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {
                "instruments": [{
                    "instrument": "MNQ",
                    "current_price": 20000.0,
                    "timeframe_bars": [{
                        "minutes": 1,
                        "utc_time": "2026-08-13T10:08:49.4000000Z",
                        "open": 1, "high": 2, "low": 0, "close": 1,
                        "descriptive_state": {
                            "native_observations": {
                                "last_completed_bar": {
                                    "utc_time": "2026-08-13T10:07:00Z",
                                    "closed_utc": "2026-08-13T10:08:00Z",
                                    "open": 10,
                                    "high": 12,
                                    "low": 9,
                                    "close": 11,
                                    "volume": 100,
                                    "completeness": "complete",
                                    "source": "ninjatrader_bars_ago_1",
                                },
                            },
                            "descriptive_state": {"path": {"state": "up"}},
                        },
                    }],
                }],
                "coverage": [],
            },
            "portfolio_snapshot": {"accounts": []},
        }],
    }
    scenario = {"books": [{"route_id": "glitch", "master_account": "Sim101", "followers": []}]}

    result = DIRECT.packet_for_model(packet, scenario)

    bar = result["frames"][0]["market_snapshot"]["instruments"][0]["timeframe_bars"][0]
    assert "bar_observation" not in bar
    assert bar["open"] == 1
    completed = bar["descriptive_state"]["native_observations"]["last_completed_bar"]
    assert completed["close"] == 11
    assert completed["completeness"] == "complete"
    assert "prior fully closed NinjaTrader candle" in result["observation_contract"]["last_completed_bar"]


def test_current_bar_keeps_nonduplicated_depth_and_order_flow_facts() -> None:
    bar = {
        "minutes": 1,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "indicators": {"cci": 42.0, "order_flow_hint": "bounded native hint"},
        "descriptive_state": {
            "native_observations": {"last_completed_bar": {"close": 100.0}},
            "descriptive_state": {
                "path": {"state": "progressing"},
                "flow": {
                    "classification_method": "quote_then_tick",
                    "quote_classified_volume": 20.0,
                    "tick_rule_volume": 4.0,
                    "ambiguous_volume": 1.0,
                    "price_impact_points_per_volume": 0.01,
                },
                "liquidity": {
                    "best_bid": 100.25,
                    "best_ask": 100.5,
                    "depth_levels": [{"price": 100.25, "size": 8}],
                    "book_reconstruction": "available",
                },
                "quality": {"packet_contiguity": "contiguous", "trading_day_id": "20260901"},
            },
        },
    }

    latest = DIRECT._compact_model_bar(bar, latest_frame=True)
    historical = DIRECT._compact_model_bar(bar, latest_frame=False)

    assert latest["indicators"]["cci"] == 42.0
    assert latest["indicators"]["order_flow_hint"] == "bounded native hint"
    state = latest["descriptive_state"]["descriptive_state"]
    assert state["flow"]["classification_method"] == "quote_then_tick"
    assert state["liquidity"]["depth_levels"][0]["size"] == 8
    assert state["quality"]["packet_contiguity"] == "contiguous"
    assert "indicators" not in historical
    assert "depth_levels" not in json.dumps(historical)


def test_compacted_bars_use_packet_session_as_canonical_location() -> None:
    packet = {
        "packet_id": "20260813T1009Z",
        "window_close_utc": "2026-08-13T10:09:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {
                "instruments": [{
                    "instrument": "M2K",
                    "current_price": 3066.0,
                    "session": {
                        "high": 3067.9,
                        "low": 3021.4,
                        "previous_high": 3050.0,
                        "previous_low": 3005.0,
                    },
                    "timeframe_bars": [{
                        "minutes": 1,
                        "descriptive_state": {"descriptive_state": {"location": {
                            "session_high": 3059.7,
                            "session_low": 3030.0,
                            "previous_session_high": 3040.0,
                            "previous_session_low": 3010.0,
                        }}},
                    }],
                }],
                "coverage": [],
            },
            "portfolio_snapshot": {"accounts": []},
        }],
    }
    scenario = {"books": [{"route_id": "glitch", "master_account": "Sim101", "followers": []}]}

    result = DIRECT.packet_for_model(packet, scenario)

    location = result["frames"][0]["market_snapshot"]["instruments"][0]["timeframe_bars"][0][
        "descriptive_state"
    ]["descriptive_state"]["location"]
    assert location == {
        "session_high": 3067.9,
        "session_low": 3021.4,
        "previous_session_high": 3050.0,
        "previous_session_low": 3005.0,
    }


def test_flat_ledger_excludes_recursive_guidance_but_preserves_facts() -> None:
    journals = {
        "decisions": [{"id": index} for index in range(5)],
        "executions": [{"id": index} for index in range(5)],
        "outcomes": [{"id": index} for index in range(8)],
        "current_guidance": {"verdict": "RECURSIVE_ABSTENTION_VETO"},
        "current_plan": {"instruction": "WAIT_FOR_MORE_CONFIRMATION"},
        "active_trade_state": {"instrument": "MNQ"},
    }

    compact = DIRECT.ledger_for_model(journals, positioned_only=False)

    assert [row["id"] for row in compact["decisions"]] == [2, 3, 4]
    assert [row["id"] for row in compact["executions"]] == [0, 1, 2, 3, 4]
    assert [row["id"] for row in compact["outcomes"]] == [2, 3, 4, 5, 6, 7]
    assert "current_guidance" not in compact
    assert "current_plan" not in compact
    assert "active_trade_state" not in compact
    assert compact["recent_exit_decisions"] == []


def test_flat_ledger_elevates_recent_exit_decisions_without_recursive_guidance() -> None:
    journals = {
        "decisions": [
            {"instrument": "MES", "action": "ENTER_SHORT", "reason": "initial path"},
            {
                "instrument": "MES",
                "action": "EXIT",
                "reason": "Buyer response reduced continuation below break-even.",
                "change_condition": "Renewed accepted downside response below 7732.75.",
            },
            {"instrument": "MNQ", "action": "NOTHING", "reason": "late location"},
        ],
        "executions": [],
        "outcomes": [],
        "current_guidance": {"verdict": "REENTER_MES"},
    }

    compact = DIRECT.ledger_for_model(journals, positioned_only=False)

    assert compact["recent_exit_decisions"] == [journals["decisions"][1]]
    assert "current_guidance" not in compact


def test_flat_prompt_treats_fresh_extreme_as_probabilistic_not_preaccepted() -> None:
    scenario = multibook_flat_scenario()
    for book in scenario["books"]:
        book["followers"] = []
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-13T10:05:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }

    prompt = DIRECT.build_prompt(
        packet,
        scenario,
        {"outcomes": [], "current_guidance": {"verdict": "RECURSIVE_ABSTENTION_VETO"}},
    )

    assert "does not require the future target to have traded already" in prompt
    assert "learner guidance is deliberately excluded from flat entry cognition" in prompt
    assert "(risk_points + friction_points) / (risk_points + reward_points)" in prompt
    assert "Estimate target-first probability from evidence before using payoff math" in prompt
    assert "never work backward from an attractive bracket" in prompt
    assert "without using payoff ratio or break-even as probability evidence" in prompt
    assert "Never raise or lower the probability range merely to preserve ENTER" in prompt
    assert "range wide enough to include all named probability uncertainty" in prompt
    assert "never keep the whole range above break-even" in prompt
    assert "UNCERTAIN is valid only when the range genuinely straddles break-even" in prompt
    assert "unconditional probability that the stated primary target prints before the stated stop" in prompt
    assert "It is not directional potential" in prompt
    assert "none remains as a separate setup-permission veto afterward" in prompt
    assert "not a fixed probability or reward/risk rule" in prompt
    assert "reconcile recent_glitch_ledger.recent_exit_decisions and completed native results before selection" in prompt
    assert "treat them as one correlated thesis" in prompt
    assert "NOTHING, HOLD, rejected candidates, and opposite-direction trades are observations" in prompt
    assert "their labels alone cannot lower its probability" in prompt
    assert "state in the decisive reason what post-exit market evidence materially changed" in prompt
    assert "Separate directional path quality from entry timing" in prompt
    assert "do not count it both as probability evidence and as untouched reward" in prompt
    assert "a concrete improvement in entry location, invalidation cost, or target-before-stop probability" in prompt
    assert "never shorthand for perfect confirmation or a required retest" in prompt
    assert "rank the evidence-supported auction path, not the easiest bracket" in prompt
    assert "A low break-even probability alone is not edge" in prompt
    assert "Use microstructure to time the entry, not to manufacture the larger path" in prompt
    assert "Cheap risk comes from favorable entry near that genuine invalidation" in prompt
    assert "is noise, not the trade thesis" in prompt
    assert "initial risk around $20 or less is presumptively ordinary noise" in prompt
    assert "About $10 risk for only $10-$20 gross reward is plainly a noise probe" in prompt
    assert "prefer structural room around 3:1 gross reward to risk or better as error margin" in prompt
    assert "treat 1:1 to 2:1 as exceptional" in prompt
    assert "not deterministic gates" in prompt
    assert "Map an objective ladder before choosing geometry" in prompt
    assert "nearby response levels manage the trade" in prompt
    assert "not the primary target merely because it is first" in prompt
    assert "infer a discounted continuation objective" in prompt
    assert "evidence, not checklist prerequisites" in prompt
    assert "not whether the primary target must be reached inside that window" in prompt
    assert "Anticipatory entry remains allowed near genuine invalidation" in prompt
    assert "higher timeframes are context, not mandatory alignment" in prompt
    assert "Immediately before returning ENTER, audit the meaning of your own NOISE_AND_GEOMETRY conclusion" in prompt
    assert "one-contract initial risk is around $20 or less without explicit supplied evidence" in prompt
    assert "both planned loss and primary capture are merely noise-probe scale" in prompt
    assert "ENTER is internally contradictory regardless of a named level" in prompt
    assert "semantic self-consistency requirement" in prompt
    assert "a supported short-horizon rotation remains eligible" not in prompt
    assert "A range wholly above break-even requires positive now_ev" in prompt
    assert "never by back-solving probability from payoff" in prompt
    assert "not a fixed probability, margin, dollar, ATR, reward/risk, confirmation, or cooldown gate" in prompt
    assert "A completed close through a named level proves that crossing, not acceptance by itself" in prompt
    assert "no retest or extra completed-bar sequence is mandatory" in prompt
    assert "price-only delivery revalidation cannot upgrade the original evidence" in prompt
    assert "do not acknowledge them and then ignore them because the payoff hurdle is low" in prompt
    assert "survives one-minute noise but not five-minute excursion" in prompt
    assert "adverse probability evidence, not a positive noise-survival claim or a fixed ATR gate" in prompt
    assert "must not raise estimated probability or confidence" in prompt
    assert "not a general penalty on an instrument or direction" in prompt
    assert "realized P&L and win/loss labels are not market evidence" in prompt
    assert "Same instrument and direction alone do not prove correlation" in prompt
    assert "A completed new leg, break-and-hold, or pullback/retest can establish a distinct setup" in prompt
    assert "If qualitative evidence disagrees with that implication, revise the estimated range" not in prompt
    assert "This check never supplies or revises probability, geometry, instrument, or action" in prompt
    assert "This consistency rule does not choose probability, geometry, instrument, or action" in prompt
    assert "This is cognitive continuity, not a cooldown or deterministic execution gate" in prompt
    assert "seconds_until_must_flat as the actual schedule horizon" in prompt
    assert "RECURSIVE_ABSTENTION_VETO" not in prompt


def test_position_prompt_rebases_earned_profit_without_changing_flat_cognition() -> None:
    positioned = multibook_flat_scenario()
    positioned["books"] = positioned["books"][:1]
    positioned["books"][0]["instrument_contexts"]["MNQ"]["current_signed_quantity"] = -1
    flat = multibook_flat_scenario()
    for scenario in (positioned, flat):
        for book in scenario["books"]:
            book["followers"] = []
            book["exposure"] = []
            book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-13T10:05:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }

    positioned_prompt = DIRECT.build_prompt(packet, positioned, {"outcomes": []})
    flat_prompt = DIRECT.build_prompt(packet, flat, {"outcomes": []})

    assert '"decision_mode":"position_management"' in positioned_prompt
    assert "when deterministic_management_math.status is complete" in positioned_prompt
    assert "When its price_basis.status is complete" in positioned_prompt
    assert "This resolves factual basis only and does not prefer a management action" in positioned_prompt
    assert "the supplied math is decision support, never an execution gate" in positioned_prompt
    assert "The break-even event is TARGET_BEFORE_STOP" in positioned_prompt
    assert "not below an 84.21% requirement" in positioned_prompt
    assert "gross_hold_terminal_ev=POSITIVE|NEGATIVE|STRADDLES" in positioned_prompt
    assert "gross_hold_terminal_ev=REPLACE_WITH_POSITIVE_NEGATIVE_OR_STRADDLES" in positioned_prompt
    assert "Chart history before entry is setup context only" in positioned_prompt
    assert "do not claim price visited or rebounded from the favorable target area" in positioned_prompt
    assert "Begin CURRENT_SETUP exactly with HELD: or FAILED:" in positioned_prompt
    assert "absent immediate follow-through, a trigger recross" in positioned_prompt
    assert "as its causal review baseline, not an automatic exit gate" in positioned_prompt
    assert "while CURRENT_SETUP is HELD, EXIT at or below breakeven is internally contradictory" in positioned_prompt
    assert "This does not require waiting for the hard stop after actual failure" in positioned_prompt
    assert "as its causal review baseline, not an automatic exit gate" not in flat_prompt
    assert "rollback relative to peak MFE and initial risk" in positioned_prompt
    assert "HOLD must explain why rebased continuation value clearly exceeds EXIT" in positioned_prompt
    assert "After material MFE, EXIT does not require original invalidation or accepted reversal" in positioned_prompt
    assert "derive and evaluate at least one candidate protection level" in positioned_prompt.lower()
    assert "cannot reject both MOVE_STOP and EXIT" in positioned_prompt
    assert "Never use a fixed MFE percentage" in positioned_prompt
    assert "Estimate target-first probability from evidence before using payoff math" not in positioned_prompt
    assert "rank the evidence-supported auction path, not the easiest bracket" not in positioned_prompt
    assert "Map an objective ladder before choosing geometry" not in positioned_prompt
    assert "never by back-solving probability from payoff" not in positioned_prompt
    assert "rollback relative to peak MFE and initial risk" not in flat_prompt
    assert "when deterministic_management_math.status is complete" not in flat_prompt
    assert "When its price_basis.status is complete" not in flat_prompt
    assert "cannot reject both MOVE_STOP and EXIT" not in flat_prompt
    assert "recent_exit_decisions and completed native results take precedence" not in positioned_prompt
    assert "seconds_until_must_flat as the actual schedule horizon" not in positioned_prompt


def test_flat_multibook_prompt_requests_one_shared_decision() -> None:
    scenario = multibook_flat_scenario()
    for book in scenario["books"]:
        book["followers"] = []
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-13T10:05:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }

    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []})

    assert '"decision_mode":"flat_scan"' in prompt
    assert '"operator_profile"' not in prompt
    assert "return exactly one decision object" in prompt
    assert "binds the identical decision to every ordered master book" in prompt
    assert "Estimate target-first probability from evidence before using payoff math" in prompt
    assert "runtime deterministically supplies schema, intent ID, time, route, account" in prompt
    assert "decision_audit closes before wake_triggers" in prompt


def test_prompt_mirrors_change_condition_prices_into_wake_triggers() -> None:
    scenario = multibook_flat_scenario()
    for book in scenario["books"]:
        book["followers"] = []
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-13T10:05:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }

    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []})

    assert "Keep the decision-level wake_triggers field empty" in prompt
    assert "never place wake_triggers inside decision_audit" in prompt
    assert "mirrors explicit instrument-labeled above/below prices from change_condition" in prompt
    assert "the first crossing wakes one immediate reassessment" in prompt


def test_fired_trigger_wakes_one_flat_review_between_scheduled_scans(tmp_path: Path, monkeypatch) -> None:
    scenario = {"books": [{"master_account": "Sim101"}]}

    def packet_at(minute: int, quantity: int = 0) -> dict:
        return {
            "packet_id": f"20260813T12{minute:02d}Z",
            "window_close_utc": f"2026-08-13T12:{minute:02d}:00Z",
            "frames": [{"portfolio_snapshot": {"accounts": [{
                "account": "Sim101",
                "positions": [] if quantity == 0 else [{
                    "instrument_root": "MNQ",
                    "market_position": "Long",
                    "quantity": quantity,
                }],
            }]}}],
        }

    fired = [{"type": "PRICE_CROSS", "instrument": "MNQ", "direction": "ABOVE", "price": 100.0}]
    monkeypatch.setattr(DIRECT, "fired_wake_triggers", lambda *_args: fired)

    assert DIRECT.invocation_reason(packet_at(6), scenario, tmp_path, None) == "condition_change"
    # A scheduled boundary scan supersedes the fired trigger with a full review.
    assert DIRECT.invocation_reason(packet_at(5), scenario, tmp_path, None) == "scheduled"
    # Positioned books never dispatch a flat trigger review.
    assert DIRECT.invocation_reason(packet_at(6, 1), scenario, tmp_path, None) == "positioned"


def test_shared_flat_trigger_review_requests_one_shared_decision() -> None:
    scenario = multibook_flat_scenario()
    for book in scenario["books"]:
        book["followers"] = []
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-13T10:06:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }
    context = {
        "reason": "condition_change",
        "fired_triggers": [{
            "source_cycle_id": "source",
            "instrument": "MNQ",
            "direction": "ABOVE",
            "price": 100.0,
        }],
    }

    prompt = DIRECT.build_prompt(
        packet,
        scenario,
        {"outcomes": []},
        invocation_reason="condition_change",
        invocation_context=context,
    )

    assert '"decision_mode":"trigger_review"' in prompt
    assert '"operator_profile"' not in prompt
    assert "return exactly one decision object" in prompt
    assert "binds the identical decision to every ordered master book" in prompt
    assert "Map an objective ladder before choosing geometry" in prompt
    assert "never by back-solving probability from payoff" in prompt


def test_latest_prior_cognition_uses_one_canonical_decision_from_latest_prior_cycle(
    tmp_path: Path,
) -> None:
    outbox = tmp_path / "hermes" / "outbox"
    outbox.mkdir(parents=True)

    def write_batch(cycle_id: str, instrument: str, evidence: str) -> None:
        decisions = []
        for account, route in (("Sim101", "glitch"), ("Sim301", "glitch-2")):
            decisions.append({
                "intent_id": f"{cycle_id}-{route}",
                "instrument": instrument,
                "account": account,
                "operator_profile": route,
                "action": "NOTHING",
                "confidence": 0.81,
                "prompt_version": "prior-prompt",
                "reason": f"{instrument} prior path remains conditional.",
                "decision_audit": {
                    "decisive_evidence": evidence,
                    "change_condition": f"{instrument} above 101.0 or below 99.0",
                    "final_choice": "NOTHING",
                },
            })
        (outbox / f"{cycle_id}.json").write_text(json.dumps({
            "schema_version": "glitch.intent.batch.v1",
            "cycle_id": cycle_id,
            "decisions": decisions,
        }), encoding="utf-8")

    write_batch("20260813T1430Z", "MNQ", "OLDER_LEDGER")
    write_batch("20260813T1435Z", "MES", "INSTRUMENT_COMPARISON_V1\nLATEST_LEDGER")
    write_batch("20260813T1440Z", "M2K", "CURRENT_CYCLE_MUST_NOT_BE_READ")

    prior = DIRECT.latest_prior_cognition(tmp_path, "20260813T1440Z")

    assert prior == {
        "schema_version": "glitch.hermes.prior_cognition.v1",
        "source_cycle_id": "20260813T1435Z",
        "source_prompt_version": "prior-prompt",
        "selected_instrument": "MES",
        "action": "NOTHING",
        "confidence": 0.81,
        "reason": "MES prior path remains conditional.",
        "decisive_evidence": "INSTRUMENT_COMPARISON_V1\nLATEST_LEDGER",
        "change_condition": "MES above 101.0 or below 99.0",
        "final_choice": "NOTHING",
    }


def test_latest_trigger_review_keeps_the_prior_full_comparison_baseline(
    tmp_path: Path,
) -> None:
    outbox = tmp_path / "hermes" / "outbox"
    outbox.mkdir(parents=True)

    def write_batch(cycle_id: str, evidence: str) -> None:
        (outbox / f"{cycle_id}.json").write_text(json.dumps({
            "schema_version": "glitch.intent.batch.v1",
            "cycle_id": cycle_id,
            "decisions": [{
                "instrument": "MES",
                "action": "NOTHING",
                "confidence": 0.8,
                "prompt_version": "prior-prompt",
                "reason": "Prior market reasoning.",
                "decision_audit": {
                    "decisive_evidence": evidence,
                    "change_condition": "MES above 101.0",
                    "final_choice": "NOTHING",
                },
            }],
        }), encoding="utf-8")

    write_batch("20260813T1430Z", "INSTRUMENT_COMPARISON_V1\nFULL_BASELINE")
    write_batch("20260813T1431Z", "TRIGGER_REVIEW_V1\nLATEST_REVIEW")

    prior = DIRECT.latest_prior_cognition(tmp_path, "20260813T1435Z")

    assert prior is not None
    assert prior["source_cycle_id"] == "20260813T1431Z"
    assert prior["decisive_evidence"] == "TRIGGER_REVIEW_V1\nLATEST_REVIEW"
    assert prior["baseline_comparison"]["source_cycle_id"] == "20260813T1430Z"
    assert (
        prior["baseline_comparison"]["decisive_evidence"]
        == "INSTRUMENT_COMPARISON_V1\nFULL_BASELINE"
    )


def test_latest_prior_cognition_carries_exact_selection_math_without_action_effect(
    tmp_path: Path,
) -> None:
    outbox = tmp_path / "hermes" / "outbox"
    outbox.mkdir(parents=True)
    (outbox / "20260813T1435Z.json").write_text(json.dumps({
        "cycle_id": "20260813T1435Z",
        "decisions": [{
            "instrument": "MNQ",
            "action": "NOTHING",
            "confidence": 0.8,
            "prompt_version": "prior-prompt",
            "reason": "Prior path was rejected.",
            "forecast": {
                "event": "STOP_BEFORE_PRIMARY_TARGET",
                "probability": 0.55,
                "method": "fixture",
                "confidence": 0.7,
            },
            "decision_audit": {
                "decisive_evidence": (
                    "INSTRUMENT_COMPARISON_V1\n"
                    "SELECTION_EV=direction=LONG;entry=100;stop=95;target=110;"
                    "risk_points=5;reward_points=10;friction_points=0;"
                    "breakeven_target_first=0.5;estimated_target_first_range=40-50%;"
                    "now_ev=NEGATIVE;wait_price=99;wait_ev=POSITIVE;decisive_reason=fixture"
                ),
                "change_condition": "MNQ above 101.0",
                "final_choice": "NOTHING",
            },
        }],
    }), encoding="utf-8")

    prior = DIRECT.latest_prior_cognition(tmp_path, "20260813T1440Z")

    assert prior is not None
    support = prior["deterministic_selection_math"]
    assert support["effect"] == "decision_support_only_no_execution_effect"
    assert support["computed_risk_points"] == 5
    assert support["computed_reward_points"] == 10
    assert support["computed_breakeven_target_first"] == pytest.approx(1 / 3)
    assert support["calculation_issues"] == [
        "declared_breakeven_mismatch",
        "verdict_range_mismatch",
    ]


def test_latest_completed_exit_supersedes_the_pre_exit_market_thesis(
    tmp_path: Path,
) -> None:
    outbox = tmp_path / "hermes" / "outbox"
    outbox.mkdir(parents=True)
    (outbox / "20260827T2024Z.json").write_text(json.dumps({
        "cycle_id": "20260827T2024Z",
        "decisions": [{
            "instrument": "MES",
            "action": "ENTER_SHORT",
            "confidence": 0.62,
            "prompt_version": "prior-prompt",
            "reason": "Bearish continuation below 7734.5.",
            "decision_audit": {
                "decisive_evidence": "INSTRUMENT_COMPARISON_V1\nBEARISH_PATH=held",
                "change_condition": "MES above 7742.25 or below 7711.25",
                "final_choice": "ENTER_SHORT",
            },
        }],
    }), encoding="utf-8")
    (outbox / "20260827T2042Z.json").write_text(json.dumps({
        "cycle_id": "20260827T2042Z",
        "decisions": [{
            "instrument": "MES",
            "action": "EXIT",
            "confidence": 0.74,
            "prompt_version": "prior-prompt",
            "reason": "Buyer response reduced continuation below break-even.",
            "decision_audit": {
                "decisive_evidence": "POSITION_MANAGEMENT_V1\nEXIT_EV=selected",
                "change_condition": "Renewed accepted downside response below 7732.75.",
                "final_choice": "EXIT",
            },
        }],
    }), encoding="utf-8")

    prior = DIRECT.latest_prior_cognition(tmp_path, "20260827T2050Z")

    assert prior is not None
    assert prior["source_cycle_id"] == "20260827T2042Z"
    assert prior["action"] == "EXIT"
    assert prior["change_condition"] == "Renewed accepted downside response below 7732.75."
    assert prior["baseline_comparison"]["source_cycle_id"] == "20260827T2024Z"


def test_flat_prompt_injects_prior_cognition_and_requires_reconciliation() -> None:
    scenario = multibook_flat_scenario()
    for book in scenario["books"]:
        book["followers"] = []
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-13T10:05:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }
    prior = {
        "schema_version": "glitch.hermes.prior_cognition.v1",
        "source_cycle_id": "cycle-8",
        "selected_instrument": "MNQ",
        "action": "NOTHING",
        "decisive_evidence": "INSTRUMENT_COMPARISON_V1\nPRIOR_PATH_STATE",
        "change_condition": "MNQ above 101.0 or below 99.0",
        "deterministic_selection_math": {
            "effect": "decision_support_only_no_execution_effect",
            "computed_breakeven_target_first": 0.4,
        },
    }

    prompt = DIRECT.build_prompt(
        packet,
        scenario,
        {"outcomes": []},
        prior_cognition=prior,
    )

    assert '"prior_cognition":{"schema_version":"glitch.hermes.prior_cognition.v1"' in prompt
    assert "PRIOR_PATH_STATE" in prompt
    assert "Reconcile every supplied prior path as HELD, FAILED, or EXPIRED" in prompt
    assert "NOT_APPLICABLE only when no prior path exists" in prompt
    assert "deterministic_geometry_context as the arithmetic authority" in prompt
    assert "lower is a price improvement for a long" in prompt
    assert "exact arithmetic correction to the prior SELECTION_EV levels" in prompt


def test_trigger_review_injects_exit_continuity_for_alternative_candidates() -> None:
    scenario = multibook_flat_scenario()
    for book in scenario["books"]:
        book["followers"] = []
        book["exposure"] = []
        book["position_building_context"] = {"instrument": "MNQ"}
    packet = {
        "packet_id": "cycle-9",
        "window_close_utc": "2026-08-27T20:51:00Z",
        "policy": {},
        "frames": [{
            "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
            "portfolio_snapshot": {"accounts": [{"account": "Sim101"}, {"account": "Sim301"}]},
        }],
    }
    prior = {
        "schema_version": "glitch.hermes.prior_cognition.v1",
        "source_cycle_id": "20260827T2042Z",
        "selected_instrument": "MES",
        "action": "EXIT",
        "reason": "Buyer response reduced short continuation below break-even.",
        "decisive_evidence": "POSITION_MANAGEMENT_V1\nEXIT_EV=selected",
        "change_condition": "Renewed accepted downside response below 7732.75.",
    }
    context = {
        "reason": "condition_change",
        "fired_triggers": [{
            "source_cycle_id": "source",
            "instrument": "MNQ",
            "direction": "BELOW",
            "price": 29627.25,
        }],
    }
    journals = {
        "decisions": [{
            "instrument": "MES",
            "action": "EXIT",
            "reason": prior["reason"],
            "change_condition": prior["change_condition"],
        }],
        "executions": [{
            "code": "master_exit_fill_observed",
            "message": "account=Sim101|contract=MES 09-26|fill=7734",
        }],
        "outcomes": [],
    }

    prompt = DIRECT.build_prompt(
        packet,
        scenario,
        journals,
        invocation_reason="condition_change",
        invocation_context=context,
        prior_cognition=prior,
    )

    assert '"decision_mode":"trigger_review"' in prompt
    assert '"prior_cognition":{"schema_version":"glitch.hermes.prior_cognition.v1"' in prompt
    assert '"recent_exit_decisions":[{"instrument":"MES","action":"EXIT"' in prompt
    assert "reconcile recent_glitch_ledger.recent_exit_decisions and completed native results before selection" in prompt
    assert "Without such a change, do not present the attempt as fresh" in prompt


def test_journal_tail_deduplicates_shared_decisions_and_preserves_instrument(
    tmp_path: Path,
) -> None:
    intents = tmp_path / "intents"
    intents.mkdir()
    rows = []
    for account, route in (("Sim101", "glitch"), ("Sim301", "glitch-2")):
        rows.append({
            "schema_version": "glitch.hermes.decision_record.v1",
            "cycle_id": "20260813T1435Z",
            "recorded_utc": "2026-08-13T14:36:00Z",
            "status": "accepted",
            "intent": {
                "intent_id": f"intent-{route}",
                "created_utc": "2026-08-13T14:35:45Z",
                "instrument": "MES",
                "account": account,
                "operator_profile": route,
                "action": "NOTHING",
                "confidence": 0.82,
                "prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
                "reason": "Shared market cognition.",
                "decision_audit": {
                    "change_condition": "MES above 101.0",
                    "final_choice": "NOTHING",
                },
            },
        })
    (intents / "decisions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = DIRECT.journal_tail(tmp_path)

    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["cycle_id"] == "20260813T1435Z"
    assert result["decisions"][0]["instrument"] == "MES"


def test_journal_tail_preserves_exit_continuity_beyond_the_visible_decision_tail(
    tmp_path: Path,
) -> None:
    intents = tmp_path / "intents"
    intents.mkdir()
    rows = [{
        "schema_version": "glitch.hermes.decision_record.v1",
        "cycle_id": "20260827T2042Z",
        "recorded_utc": "2026-08-27T20:42:50Z",
        "status": "accepted",
        "intent": {
            "intent_id": "exit-intent",
            "created_utc": "2026-08-27T20:42:49Z",
            "instrument": "MES",
            "action": "EXIT",
            "confidence": 0.74,
            "prompt_version": DIRECT.DIRECT_PROMPT_REVISION + "-previousbundle",
            "reason": "Buyer response reduced continuation below break-even.",
            "decision_audit": {
                "change_condition": "Renewed accepted downside response below 7732.75.",
                "final_choice": "EXIT",
            },
        },
    }]
    rows.extend({
        "schema_version": "glitch.hermes.decision_record.v1",
        "cycle_id": f"20260827T20{43 + index:02d}Z",
        "recorded_utc": f"2026-08-27T20:{43 + index:02d}:00Z",
        "status": "accepted",
        "intent": {
            "intent_id": f"nothing-{index}",
            "created_utc": f"2026-08-27T20:{43 + index:02d}:00Z",
            "instrument": "MES",
            "action": "NOTHING",
            "confidence": 0.7,
            "prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
            "reason": "No current entry.",
            "decision_audit": {
                "change_condition": "MES above 7742.25 or below 7711.25.",
                "final_choice": "NOTHING",
            },
        },
    } for index in range(10))
    (intents / "decisions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = DIRECT.journal_tail(tmp_path)

    assert all(row["action"] == "NOTHING" for row in result["decisions"])
    assert result["recent_exit_decisions"] == [{
        "cycle_id": "20260827T2042Z",
        "recorded_utc": "2026-08-27T20:42:50Z",
        "status": "accepted",
        "intent_id": "exit-intent",
        "created_utc": "2026-08-27T20:42:49Z",
        "instrument": "MES",
        "action": "EXIT",
        "confidence": 0.74,
        "reason": "Buyer response reduced continuation below break-even.",
        "change_condition": "Renewed accepted downside response below 7732.75.",
        "final_choice": "EXIT",
    }]


def test_journal_tail_retains_native_exit_result_until_full_outcome_exists(
    tmp_path: Path,
) -> None:
    intents = tmp_path / "intents"
    intents.mkdir()
    entry_intent = "11111111-1111-4111-8111-111111111111"
    rows = [
        {
            "recorded_utc": "2026-08-17T13:11:05Z",
            "intent_id": entry_intent,
            "status": "executed",
            "code": "master_entry_fill_observed",
            "message": "account=Sim101|contract=MES 09-26|fill=7805.5",
        },
        {
            "recorded_utc": "2026-08-17T13:34:02Z",
            "intent_id": entry_intent,
            "status": "executed",
            "code": "master_stop_exit_fill_observed",
            "message": (
                "account=Sim101|contract=MES 09-26|entry=7805.5|fill=7800.25"
                "|point_value_usd=5|realized_pnl_usd=-26.25"
            ),
        },
    ]
    rows.extend({
        "recorded_utc": f"2026-08-17T13:{35 + index:02d}:00Z",
        "intent_id": f"nothing-{index}",
        "status": "executed",
        "code": "no_native_action_requested",
        "message": "NOTHING",
    } for index in range(8))
    (intents / "executions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = DIRECT.journal_tail(tmp_path)

    codes = [row["code"] for row in result["executions"]]
    assert "master_entry_fill_observed" in codes
    assert "master_stop_exit_fill_observed" in codes
    stop = next(
        row for row in result["executions"]
        if row["code"] == "master_stop_exit_fill_observed"
    )
    assert "realized_pnl_usd=-26.25" in stop["message"]
    prompt_ledger = DIRECT.ledger_for_model(result, positioned_only=False)
    assert "master_stop_exit_fill_observed" in {
        row["code"] for row in prompt_ledger["executions"]
    }


def test_journal_tail_uses_full_outcome_after_old_lifecycle_result(
    tmp_path: Path,
) -> None:
    intents = tmp_path / "intents"
    intents.mkdir()
    entry_intent = "11111111-1111-4111-8111-111111111111"
    lifecycle = [{
        "recorded_utc": "2026-08-17T13:34:02Z",
        "intent_id": entry_intent,
        "status": "executed",
        "code": "master_stop_exit_fill_observed",
        "message": "realized_pnl_usd=-26.25",
    }]
    lifecycle.extend({
        "recorded_utc": f"2026-08-17T14:{index:02d}:00Z",
        "intent_id": f"nothing-{index}",
        "status": "executed",
        "code": "no_native_action_requested",
        "message": "NOTHING",
    } for index in range(8))
    (intents / "executions.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in lifecycle),
        encoding="utf-8",
    )
    (intents / "hermes-trade-outcomes.jsonl").write_text(
        json.dumps({
            "intent_id": entry_intent,
            "cycle_id": "20260817T1310Z",
            "origin": "ai",
            "master_learning_eligible": True,
            "master_account": "Sim101",
            "instrument": "MES",
            "action": "ENTER_LONG",
            "master_realized_pnl_usd": -26.25,
        }) + "\n",
        encoding="utf-8",
    )

    result = DIRECT.journal_tail(tmp_path)

    assert all(
        row["code"] != "master_stop_exit_fill_observed"
        for row in result["executions"]
    )
    assert result["outcomes"][0]["master_realized_pnl_usd"] == -26.25


def test_cognitive_bundle_hash_includes_hot_path_runner_contract() -> None:
    assert "SOUL.md" in DIRECT.COGNITIVE_BUNDLE_RELATIVE_PATHS
    assert "scripts/run-direct-glitch-cycle.py" in DIRECT.COGNITIVE_BUNDLE_RELATIVE_PATHS


def test_prior_cognition_disables_not_applicable_backfill() -> None:
    batch, _ = valid_batch("2026-08-13T14:35:45Z")
    evidence = "\n".join([
        DIRECT.CANDIDATE_COMPARISON_MARKER,
        "INSTRUMENT MNQ:",
        "CURRENT_AUCTION=accepted above prior transition",
    ])
    batch["decisions"][0]["decision_audit"]["decisive_evidence"] = evidence

    DIRECT.backfill_constant_comparison_fields(
        batch,
        allow_not_applicable=False,
    )

    assert "PRIOR_TRIGGER_REVIEW=NOT_APPLICABLE" not in (
        batch["decisions"][0]["decision_audit"]["decisive_evidence"]
    )
