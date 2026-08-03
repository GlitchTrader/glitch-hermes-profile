import importlib.util
import json
import sys
from pathlib import Path

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


def test_validator_rejects_compact_created_utc() -> None:
    batch, scenario = valid_batch("20260803T070241.0414980Z")

    with pytest.raises(ValueError, match=r"^intent_created_utc_invalid:0$"):
        DIRECT.validate_batch(batch, scenario)


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
            "wake_triggers": [],
        }],
    }

    DIRECT.submit_batch(batch, glitch_data, exchange)

    assert posted[0]["created_utc"] == "2026-08-03T07:02:41.5000000Z"
    assert "wake_triggers" not in posted[0]


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
