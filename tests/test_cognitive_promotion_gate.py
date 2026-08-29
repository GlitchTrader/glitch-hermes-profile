import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_hermes_learning_cycle_gate",
    ROOT / "scripts" / "run-hermes-learning-cycle.py",
)
LEARNING = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LEARNING)
DIRECT = LEARNING.DIRECT


def episode(episode_id: str, group_id: str, session_date: str, prompt_version: str) -> dict:
    return {
        "schema_version": "glitch.hermes.decision_episode.v2",
        "episode_id": episode_id,
        "recorded_utc": f"{session_date}T15:00:00Z",
        "decision_utc": f"{session_date}T15:00:00Z",
        "instrument": "TEST",
        "action": "NOTHING",
        "prompt_version": prompt_version,
        "opportunity_group_id": group_id,
        "evidence_context": {"session_date_et": session_date, "session_phase": "observed"},
        "master_learning_eligible": True,
        "native_outcome_reconciliation_status": "reconciled",
    }


def candidate(evidence_ids: list[str]) -> dict:
    return {
        "cognitive_change_candidate": {
            "propose": True,
            "candidate_id": "candidate-1",
            "operation": "replace",
            "target": "core_prompt",
            "expected_old_text": "Treat incomplete evidence as uncertainty.",
            "replacement_text": "Treat incomplete evidence as an uncertainty cost and keep alternatives comparable.",
            "evidence_episode_ids": evidence_ids,
            "expected_effect": "Improve calibration without suppressing valid intent.",
            "evaluation_metric": "Compare target-before-stop calibration on later completed master outcomes.",
            "rollback_condition": "Rollback if calibration degrades or abstention rises without better outcomes.",
        }
    }


def decision(candidate_id: str, action: str, evidence_ids: list[str]) -> dict:
    return {
        "cognitive_change_decision": {
            "candidate_id": candidate_id,
            "action": action,
            "evidence_episode_ids": evidence_ids,
            "contradiction_reviewed_episode_ids": evidence_ids,
            "contradiction_review": "Reviewed supporting and contradicting later outcomes.",
            "metric_assessment": "The declared calibration metric improved without a suppression increase.",
            "reason": "Independent later evidence supports the action.",
        }
    }


def write_rows(path: Path, rows: list[dict]) -> None:
    LEARNING.write_jsonl_atomic(path, rows)


def evaluation_report(
    candidate_id: str,
    prompt_version: str,
    evidence_ids: list[str],
    *,
    local_eligible: bool = True,
    distribution_eligible: bool = True,
) -> dict:
    value = {
        "schema_version": "glitch.hermes.cognition_evaluation_publication.v1",
        "report_id": "report-1",
        "experiment_id": "experiment-1",
        "candidate_id": candidate_id,
        "expected_prompt_version": prompt_version,
        "cognitive_bundle_hash": DIRECT.cognitive_bundle_hash_from_prompt_version(prompt_version),
        "effect": "lesson_lifecycle_only_no_trade_or_execution_effect",
        "covered_trade_episode_ids": evidence_ids,
        "cost_policy": {"verified": distribution_eligible},
        "sample": {"exact_completed_trades": len(evidence_ids)},
        "performance": {"net_pnl_usd": 10.0},
        "calibration": {"beats_climatology": True},
        "promotion_gate": {
            "local_continuation": {
                "eligible": local_eligible,
                "checks": [{"name": "local", "passed": local_eligible}],
            },
            "distribution": {
                "eligible": distribution_eligible,
                "checks": [{"name": "distribution", "passed": distribution_eligible}],
            },
        },
    }
    value["publication_sha256"] = hashlib.sha256(json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return value


def test_trade_fact_envelope_gets_system_owned_prompt_and_opportunity_identity() -> None:
    facts = {
        "master_outcome": {"instrument": "MES", "action": "ENTER_LONG"},
        "entry_decision_context": {
            "decision_utc": "2026-08-17T14:00:00Z",
            "prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
            "evidence_context": {"session_date_et": "2026-08-17"},
        },
    }
    enriched = LEARNING.attach_fact_envelopes([{"episode_id": "trade-1"}], [facts])[0]

    assert enriched["prompt_version"] == DIRECT.DIRECT_PROMPT_VERSION
    assert enriched["cognitive_bundle_hash"] == DIRECT.cognitive_bundle_hash_from_prompt_version(
        DIRECT.DIRECT_PROMPT_VERSION
    )
    assert enriched["opportunity_group_id"]
    assert enriched["evidence_context"] == {"session_date_et": "2026-08-17"}


def test_proposal_requires_independent_cross_session_evidence_and_general_language(tmp_path) -> None:
    supervisor = tmp_path / "supervisor"
    supervisor.mkdir()
    same_session = [
        episode("idea-1", "group-1", "2026-08-17", DIRECT.DIRECT_PROMPT_VERSION),
        episode("idea-2", "group-2", "2026-08-17", DIRECT.DIRECT_PROMPT_VERSION),
    ]
    write_rows(supervisor / "decision-episodes.jsonl", same_session)

    LEARNING.activate_cognitive_candidate(candidate(["idea-1", "idea-2"]), supervisor)
    assert not (supervisor / "proposed-cognitive-overlay.json").exists()

    same_session[1]["recorded_utc"] = "2026-08-18T15:00:00Z"
    same_session[1]["decision_utc"] = "2026-08-18T15:00:00Z"
    same_session[1]["evidence_context"]["session_date_et"] = "2026-08-18"
    same_session[1]["prompt_version"] = (
        DIRECT.DIRECT_PROMPT_VERSION + DIRECT.COGNITIVE_OVERLAY_VERSION_MARKER + "other"
    )
    write_rows(supervisor / "decision-episodes.jsonl", same_session)
    LEARNING.activate_cognitive_candidate(candidate(["idea-1", "idea-2"]), supervisor)
    assert not (supervisor / "proposed-cognitive-overlay.json").exists()

    same_session[1]["prompt_version"] = DIRECT.DIRECT_PROMPT_VERSION
    write_rows(supervisor / "decision-episodes.jsonl", same_session)
    specific = candidate(["idea-1", "idea-2"])
    specific["cognitive_change_candidate"]["replacement_text"] = "Always enter MES long at 09:30."

    LEARNING.activate_cognitive_candidate(specific, supervisor)
    assert not (supervisor / "proposed-cognitive-overlay.json").exists()

    LEARNING.activate_cognitive_candidate(candidate(["idea-1", "idea-2"]), supervisor)
    proposed = DIRECT.read_json(supervisor / "proposed-cognitive-overlay.json")
    assert proposed["gate_version"] == DIRECT.COGNITIVE_GATE_VERSION
    assert proposed["proposal_evidence"]["session_dates_et"] == ["2026-08-17", "2026-08-18"]
    assert proposed["auto_install"] is False


def test_activation_and_distribution_require_new_exactly_attributed_master_evidence(tmp_path) -> None:
    supervisor = tmp_path / "supervisor"
    supervisor.mkdir()
    discovery = [
        episode("idea-1", "group-1", "2026-08-15", DIRECT.DIRECT_PROMPT_VERSION),
        episode("idea-2", "group-2", "2026-08-16", DIRECT.DIRECT_PROMPT_VERSION),
    ]
    write_rows(supervisor / "decision-episodes.jsonl", discovery)
    LEARNING.activate_cognitive_candidate(candidate(["idea-1", "idea-2"]), supervisor)

    confirmation = [
        episode("trade-1", "trade-group-1", "2026-08-17", DIRECT.DIRECT_PROMPT_VERSION),
        episode("trade-2", "trade-group-2", "2026-08-18", DIRECT.DIRECT_PROMPT_VERSION),
    ]
    write_rows(supervisor / "trade-episodes.jsonl", confirmation)
    all_ids = LEARNING.cognitive_evidence_ids(supervisor)

    LEARNING.apply_cognitive_decision(decision("candidate-1", "activate", ["trade-1"]), supervisor, all_ids)
    assert not (supervisor / "active-cognitive-overlay.json").exists()

    LEARNING.apply_cognitive_decision(
        decision("candidate-1", "activate", ["trade-1", "trade-2"]), supervisor, all_ids
    )
    active_path = supervisor / "active-cognitive-overlay.json"
    active = DIRECT.read_json(active_path)
    assert active["status"] == "active"
    assert active["effective_prompt_version"].startswith(
        DIRECT.DIRECT_PROMPT_VERSION + DIRECT.COGNITIVE_OVERLAY_VERSION_MARKER
    )
    assert DIRECT.cognitive_overlay_is_current(active)

    unattributed_validation = [
        episode("trade-3", "trade-group-3", "2026-08-19", DIRECT.DIRECT_PROMPT_VERSION),
        episode("trade-4", "trade-group-4", "2026-08-20", DIRECT.DIRECT_PROMPT_VERSION),
    ]
    write_rows(supervisor / "trade-episodes.jsonl", confirmation + unattributed_validation)
    all_ids = LEARNING.cognitive_evidence_ids(supervisor)
    LEARNING.apply_cognitive_decision(
        decision("candidate-1", "promote", ["trade-3", "trade-4"]), supervisor, all_ids
    )
    assert DIRECT.read_json(active_path)["status"] == "active"
    assert not (supervisor / "distribution-candidates.jsonl").exists()

    validation = [
        episode("trade-3", "trade-group-3", "2026-08-19", active["effective_prompt_version"]),
        episode("trade-4", "trade-group-4", "2026-08-20", active["effective_prompt_version"]),
    ]
    write_rows(supervisor / "trade-episodes.jsonl", confirmation + validation)
    all_ids = LEARNING.cognitive_evidence_ids(supervisor)
    LEARNING.apply_cognitive_decision(
        decision("candidate-1", "promote", ["trade-3", "trade-4"]), supervisor, all_ids
    )

    assert DIRECT.read_json(active_path)["status"] == "active"
    assert not (supervisor / "distribution-candidates.jsonl").exists()

    tampered = evaluation_report(
        "candidate-1",
        active["effective_prompt_version"],
        ["trade-3", "trade-4"],
    )
    tampered["publication_sha256"] = "tampered"
    write_rows(supervisor / "cognition-evaluation-reports.jsonl", [tampered])
    LEARNING.apply_cognitive_decision(
        decision("candidate-1", "promote", ["trade-3", "trade-4"]), supervisor, all_ids
    )
    assert DIRECT.read_json(active_path)["status"] == "active"

    write_rows(
        supervisor / "cognition-evaluation-reports.jsonl",
        [evaluation_report(
            "candidate-1",
            active["effective_prompt_version"],
            ["trade-3", "trade-4"],
        )],
    )
    LEARNING.apply_cognitive_decision(
        decision("candidate-1", "promote", ["trade-3", "trade-4"]), supervisor, all_ids
    )

    promoted = DIRECT.read_json(active_path)
    dossiers = LEARNING.read_jsonl(supervisor / "distribution-candidates.jsonl")
    assert promoted["status"] == "promoted"
    assert len(dossiers) == 1
    assert dossiers[0]["status"] == "human_review_required"
    assert dossiers[0]["auto_install"] is False
    assert dossiers[0]["validation_scope"] == "single_installation_local"
    assert promoted["deterministic_evaluation"]["report_id"] == "report-1"


def test_unreconciled_trade_episode_cannot_activate_a_lesson(tmp_path) -> None:
    supervisor = tmp_path / "supervisor"
    supervisor.mkdir()
    discovery = [
        episode("idea-1", "group-1", "2026-08-15", DIRECT.DIRECT_PROMPT_VERSION),
        episode("idea-2", "group-2", "2026-08-16", DIRECT.DIRECT_PROMPT_VERSION),
    ]
    write_rows(supervisor / "decision-episodes.jsonl", discovery)
    LEARNING.activate_cognitive_candidate(candidate(["idea-1", "idea-2"]), supervisor)

    reconciled = episode(
        "trade-1", "trade-group-1", "2026-08-17", DIRECT.DIRECT_PROMPT_VERSION
    )
    quarantined = episode(
        "trade-2", "trade-group-2", "2026-08-18", DIRECT.DIRECT_PROMPT_VERSION
    )
    quarantined["master_learning_eligible"] = False
    quarantined["native_outcome_reconciliation_status"] = "quarantined"
    write_rows(supervisor / "trade-episodes.jsonl", [reconciled, quarantined])

    assert LEARNING.trade_evidence_ids(supervisor) == ["trade-1"]
    LEARNING.apply_cognitive_decision(
        decision("candidate-1", "activate", ["trade-1", "trade-2"]),
        supervisor,
        LEARNING.cognitive_evidence_ids(supervisor),
    )
    assert not (supervisor / "active-cognitive-overlay.json").exists()


def test_expired_or_legacy_overlay_cannot_change_prompt_or_prompt_identity() -> None:
    old = "Treat incomplete evidence as uncertainty."
    replacement = "Treat incomplete evidence as an uncertainty cost."
    base = {
        "status": "active",
        "gate_version": DIRECT.COGNITIVE_GATE_VERSION,
        "activation_evidence_kind": "completed_master_outcomes",
        "decision_prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
        "candidate_id": "candidate-1",
        "operation": "replace",
        "target": "core_prompt",
        "expected_old_text": old,
        "expected_old_sha256": hashlib.sha256(old.encode("utf-8")).hexdigest(),
        "replacement_text": replacement,
    }
    active = {
        **base,
        "expires_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    effective = DIRECT.effective_prompt_version(active)
    batch = DIRECT.stamp_decision_prompt_version(
        DIRECT.stamp_decision_created_utc({"decisions": [{}]}), effective
    )

    assert DIRECT.apply_cognitive_overlay(old, active) == replacement
    assert batch["decisions"][0]["prompt_version"] == effective
    assert DIRECT.base_prompt_version(effective) == DIRECT.DIRECT_PROMPT_VERSION

    expired = {
        **base,
        "expires_utc": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    }
    legacy = {**active, "gate_version": "glitch.hermes.cognitive_gate.v1"}
    assert DIRECT.apply_cognitive_overlay(old, expired) == old
    assert DIRECT.apply_cognitive_overlay(old, legacy) == old
    assert DIRECT.effective_prompt_version(expired) == DIRECT.DIRECT_PROMPT_VERSION
