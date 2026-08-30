import importlib.util
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evaluate_frozen_cognition",
    ROOT / "scripts" / "evaluate-frozen-cognition.py",
)
EVALUATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EVALUATOR)
DIRECT = EVALUATOR.load_direct_module(ROOT)


def trade_episode(episode_id: str, prompt_version: str) -> dict:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "episode_id": episode_id,
        "recorded_utc": now,
        "decision_utc": now,
        "intent_id": f"intent-{episode_id}",
        "instrument": "MES",
        "prompt_version": prompt_version,
        "evidence_context": {
            "session_date_et": datetime.now(timezone.utc).date().isoformat(),
            "atr_1m": 1.0,
            "path": {"trend_efficiency": {"15": 0.4}},
        },
        "facts": {
            "master_result": {
                "quantity": 1,
                "realized_pnl_usd": 20.0,
                "point_value_usd": 5.0,
                "tick_size": 0.25,
            },
            "entry_decision_context": {
                "decision_utc": now,
                "decision_reference_price": 5000.0,
                "selection_ev_arithmetic": {
                    "inputs": {"risk_points": 2.0, "reward_points": 4.0},
                    "estimated_target_first_range": {"low": 0.55, "high": 0.65},
                },
                "evidence_context": {
                    "session_date_et": datetime.now(timezone.utc).date().isoformat(),
                    "atr_1m": 1.0,
                    "path": {"trend_efficiency": {"15": 0.4}},
                },
            },
            "master_outcome": {
                "intent_id": f"intent-{episode_id}",
                "instrument": "MES",
                "forecast_outcome": {
                    "event": "STOP_BEFORE_PRIMARY_TARGET",
                    "probability": 0.4,
                    "observed": False,
                },
                "execution_diagnostics": {
                    "intent_fidelity": {
                        "signed_adverse_drift_ticks": 1.0,
                        "entry_range_fill_quality": {"status": "inside_declared_range"},
                        "coverage": {
                            "native_state": "fully_protected",
                            "unprotected_quantity": 0,
                        },
                        "timing": {
                            "decision_to_submission_ms": 1000,
                            "submission_to_fill_ms": 50,
                        },
                    }
                },
            },
        },
    }


def nothing_episode(episode_id: str, prompt_version: str) -> dict:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "episode_id": episode_id,
        "recorded_utc": now,
        "decision_utc": now,
        "instrument": "MES",
        "action": "NOTHING",
        "prompt_version": prompt_version,
        "instrument_point_value_usd": 5.0,
        "instrument_tick_size": 0.25,
        "opportunity_group_id": "group-1",
        "evidence_context": {"session_date_et": datetime.now(timezone.utc).date().isoformat()},
        "selection_ev_arithmetic": {
            "inputs": {"risk_points": 1.0, "reward_points": 2.0},
            "estimated_target_first_range": {"low": 0.6, "high": 0.8},
            "deterministic_breakeven_target_first": 0.5,
        },
        "decision_audit": {
            "decisive_evidence": (
                "SELECTION_EV=direction=LONG;entry=100;stop=99;target=102;"
                "risk_points=1;reward_points=2;estimated_target_first_range=60%-80%"
            )
        },
        "forward_observations": [
            {"high": 100.5, "low": 99.5},
            {"high": 102.0, "low": 99.25},
        ],
    }


def test_trade_score_uses_explicit_cost_and_numeric_expected_value() -> None:
    policy = EVALUATOR.build_cost_policy(4.0, ["MES=5.00"], "operator statement")
    score = EVALUATOR.trade_score(trade_episode("trade-1", DIRECT.DIRECT_PROMPT_VERSION), policy)

    assert score is not None
    assert score["evaluation_cost_usd"] == 5.0
    assert score["net_pnl_usd"] == 15.0
    assert score["probability_target_first"] == 0.6
    assert score["expected_net_usd"] == 3.0
    assert score["brier_score"] == 0.16


def test_nothing_score_reconstructs_target_first_without_claiming_a_fill() -> None:
    policy = EVALUATOR.build_cost_policy(4.0, [], None)
    score = EVALUATOR.nothing_score(
        nothing_episode("nothing-1", DIRECT.DIRECT_PROMPT_VERSION), policy, {}
    )

    assert score is not None
    assert score["counterfactual_chronology"] == "target_before_stop"
    assert score["expected_net_usd"] == 0.5
    assert score["brier_score"] == 0.09


def test_free_text_chronology_is_reduced_to_a_bounded_audit_state() -> None:
    assert EVALUATOR.normalize_chronology(
        "OBJECTIVE_REACHED_BEFORE_OBSERVED_INVALIDATION; favorable path only"
    ) == "target_before_stop"
    assert EVALUATOR.normalize_chronology(
        "invalidation_reached_before_objective; target was not reached"
    ) == "stop_before_target"
    assert EVALUATOR.normalize_chronology(
        "SAME_BAR_OR_UNORDERED_AMBIGUITY; exact sequence unavailable"
    ) == "ambiguous_or_unresolved"
    assert EVALUATOR.normalize_chronology(
        "NOT_REACHED; neither objective nor invalidation was reached"
    ) == "neither_reached"


def test_report_is_observational_and_fails_closed_on_small_sample(tmp_path: Path) -> None:
    started = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": EVALUATOR.FREEZE_SCHEMA,
        "experiment_id": "test-experiment",
        "candidate_id": "candidate-1",
        "experiment_started_utc": started,
        "expected_prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
        "cognitive_bundle_hash": DIRECT.cognitive_bundle_hash(),
        "distribution_version": "test",
        "baseline_evidence_ids": [],
        "cost_policy": EVALUATOR.build_cost_policy(4.0, ["MES=5.00"], "operator statement"),
    }
    report = EVALUATOR.build_report(
        manifest,
        ROOT,
        [nothing_episode("nothing-1", DIRECT.DIRECT_PROMPT_VERSION)],
        [trade_episode("trade-1", DIRECT.DIRECT_PROMPT_VERSION)],
        [],
    )

    assert report["effect"] == "lesson_lifecycle_only_no_trade_or_execution_effect"
    assert report["performance"]["net_pnl_usd"] == 15.0
    assert report["promotion_gate"]["local_continuation"]["eligible"] is False
    assert report["promotion_gate"]["distribution"]["eligible"] is False

    supervisor = tmp_path / "supervisor"
    EVALUATOR.publish_report(supervisor, report)
    published = EVALUATOR.read_jsonl(supervisor / EVALUATOR.REPORT_LEDGER)
    assert len(published) == 1
    assert published[0]["report_id"] == report["report_id"]
    assert published[0]["publication_sha256"] == EVALUATOR.canonical_sha256({
        key: value for key, value in published[0].items() if key != "publication_sha256"
    })
    assert "trade_scores" not in published[0]


def test_profile_hot_bundle_excludes_evaluator_and_learner() -> None:
    protected = set(DIRECT.COGNITIVE_BUNDLE_RELATIVE_PATHS)

    assert "scripts/evaluate-frozen-cognition.py" not in protected
    assert "scripts/run-hermes-learning-cycle.py" not in protected


def test_evaluator_has_no_model_network_or_process_execution_surface() -> None:
    source = (ROOT / "scripts" / "evaluate-frozen-cognition.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert imported.isdisjoint({"http", "requests", "socket", "subprocess", "urllib"})
    assert "invoke_hermes" not in source
    assert "persist_outbox" not in source


def test_freeze_preserves_profile_bytes_and_evaluates_only_later_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    glitch_data = tmp_path / "GlitchData"
    supervisor = EVALUATOR.supervisor_root(glitch_data)
    for name in ("decision-episodes.jsonl", "trade-episodes.jsonl", "observations.jsonl"):
        EVALUATOR.write_jsonl_atomic(supervisor / name, [])
    monkeypatch.setattr(EVALUATOR, "assert_freeze_is_quiescent", lambda *_: None)

    experiment = EVALUATOR.freeze_experiment(
        glitch_data,
        ROOT,
        "test-freeze",
        EVALUATOR.build_cost_policy(4.0, [], None),
    )
    manifest = EVALUATOR.read_json(experiment / "freeze.json")
    EVALUATOR.verify_experiment_checkpoint(experiment, manifest)
    assert manifest["expected_prompt_version"] == DIRECT.DIRECT_PROMPT_VERSION
    assert manifest["cognitive_bundle_hash"] == DIRECT.cognitive_bundle_hash()
    assert all((experiment / row["checkpoint_path"]).is_file() for row in manifest["profile_checkpoint_files"])

    later = EVALUATOR.parse_utc(manifest["experiment_started_utc"]) + timedelta(seconds=1)
    stamp = later.isoformat().replace("+00:00", "Z")
    decision_row = nothing_episode("nothing-later", DIRECT.DIRECT_PROMPT_VERSION)
    decision_row.update({"recorded_utc": stamp, "decision_utc": stamp})
    trade_row = trade_episode("trade-later", DIRECT.DIRECT_PROMPT_VERSION)
    trade_row.update({"recorded_utc": stamp, "decision_utc": stamp})
    trade_row["facts"]["entry_decision_context"]["decision_utc"] = stamp
    EVALUATOR.write_jsonl_atomic(supervisor / "decision-episodes.jsonl", [decision_row])
    EVALUATOR.write_jsonl_atomic(supervisor / "trade-episodes.jsonl", [trade_row])

    report_path, report = EVALUATOR.evaluate_experiment(
        glitch_data, ROOT, experiment, publish=False
    )
    assert report_path.is_file()
    assert report["sample"]["exact_completed_trades"] == 1
    assert report["sample"]["exact_nothing_decisions"] == 1


def test_freeze_staging_path_does_not_repeat_experiment_id(
    tmp_path: Path, monkeypatch
) -> None:
    glitch_data = tmp_path / "GlitchData"
    supervisor = EVALUATOR.supervisor_root(glitch_data)
    for name in ("decision-episodes.jsonl", "trade-episodes.jsonl", "observations.jsonl"):
        EVALUATOR.write_jsonl_atomic(supervisor / name, [])
    monkeypatch.setattr(EVALUATOR, "assert_freeze_is_quiescent", lambda *_: None)
    copied_destinations = []
    real_copy2 = EVALUATOR.shutil.copy2

    def recording_copy2(source, destination, *args, **kwargs):
        copied_destinations.append(Path(destination))
        return real_copy2(source, destination, *args, **kwargs)

    monkeypatch.setattr(EVALUATOR.shutil, "copy2", recording_copy2)
    experiment_id = "identifier-that-must-not-inflate-the-staging-path"
    experiment = EVALUATOR.freeze_experiment(
        glitch_data,
        ROOT,
        experiment_id,
        EVALUATOR.build_cost_policy(4.0, [], None),
    )

    assert experiment.name == experiment_id
    assert copied_destinations
    assert all(".cognition-tmp" in destination.parts for destination in copied_destinations)
    assert all(experiment_id not in destination.parts for destination in copied_destinations)
    assert not (glitch_data / "hermes-checkpoints" / ".cognition-tmp").exists()
