import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_hermes_learning_cycle_p0",
    ROOT / "scripts" / "run-hermes-learning-cycle.py",
)
LEARNING = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LEARNING)


def test_learning_admission_delegates_to_the_shared_live_market_rail(tmp_path, monkeypatch) -> None:
    packet_path = tmp_path / "hermes" / "exchange" / "glitch" / "latest-decision-packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text(json.dumps({"packet_id": "packet-1"}), encoding="utf-8")
    observed = []

    def shared_gate(glitch_data, packet):
        observed.append((glitch_data, packet))
        return "market_session_closed"

    monkeypatch.setattr(LEARNING.DIRECT, "model_call_admission_reason", shared_gate)

    assert LEARNING.learning_model_call_admission_reason(tmp_path) == "market_session_closed"
    assert observed == [(tmp_path.resolve(), {"packet_id": "packet-1"})]


def test_deferred_learner_retries_inside_the_same_scheduled_worker(tmp_path, monkeypatch) -> None:
    args = SimpleNamespace(glitch_data=tmp_path, dry_run=False)
    status_path = tmp_path / "learning-worker-status.json"
    refreshes = []

    def run_once(_args, *, refresh_derived=True):
        refreshes.append(refresh_derived)
        if len(refreshes) == 1:
            raise LEARNING.LearningDeferred("trading_decision_waiting")
        return {"hourly": True}

    monkeypatch.setattr(LEARNING, "run_once", run_once)
    monkeypatch.setattr(LEARNING, "ai_trading_is_paused", lambda _path: False)
    monkeypatch.setattr(LEARNING.time, "sleep", lambda _seconds: None)

    result = LEARNING.run_with_defer_retries(args, status_path)

    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert result == {"hourly": True}
    assert refreshes == [True, False]
    assert status["status"] == "deferred"
    assert status["retrying"] is True
    assert status["retry_count"] == 1


def test_deferred_learner_does_not_retry_while_ai_is_paused(tmp_path, monkeypatch) -> None:
    args = SimpleNamespace(glitch_data=tmp_path, dry_run=False)
    status_path = tmp_path / "learning-worker-status.json"
    def defer(_args, *, refresh_derived=True):
        del refresh_derived
        raise LEARNING.LearningDeferred("hermes_profile_busy")

    monkeypatch.setattr(LEARNING, "run_once", defer)
    monkeypatch.setattr(LEARNING, "ai_trading_is_paused", lambda _path: True)
    slept = []
    monkeypatch.setattr(LEARNING.time, "sleep", slept.append)

    with pytest.raises(LEARNING.LearningDeferred, match="hermes_profile_busy"):
        LEARNING.run_with_defer_retries(args, status_path)

    assert slept == []


def test_market_or_data_admission_deferral_waits_for_next_cron(tmp_path, monkeypatch) -> None:
    args = SimpleNamespace(glitch_data=tmp_path, dry_run=False)
    status_path = tmp_path / "learning-worker-status.json"
    calls = []

    def defer(_args, *, refresh_derived=True):
        calls.append(refresh_derived)
        raise LEARNING.LearningNotAdmitted("market_session_closed")

    monkeypatch.setattr(LEARNING, "run_once", defer)
    slept = []
    monkeypatch.setattr(LEARNING.time, "sleep", slept.append)

    with pytest.raises(LEARNING.LearningNotAdmitted, match="market_session_closed"):
        LEARNING.run_with_defer_retries(args, status_path)

    assert calls == [True]
    assert slept == []


def test_learning_repair_rechecks_model_call_admission(tmp_path, monkeypatch) -> None:
    args = SimpleNamespace(
        glitch_data=tmp_path,
        profile="glitch",
        timeout_seconds=30,
    )
    admission_calls = 0
    model_calls = 0

    def admission(_args):
        nonlocal admission_calls
        admission_calls += 1
        if admission_calls == 2:
            raise LEARNING.LearningNotAdmitted("stale_market_package")

    def invoke(*_args, **_kwargs):
        nonlocal model_calls
        model_calls += 1
        return {"invalid": True}

    monkeypatch.setattr(LEARNING, "require_learning_model_call_admission", admission)
    monkeypatch.setattr(LEARNING, "invoke_hermes", invoke)
    monkeypatch.setattr(LEARNING, "build_prompt", lambda *_args, **_kwargs: "PROMPT")
    monkeypatch.setattr(LEARNING, "output_template", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(LEARNING, "continuity", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        LEARNING,
        "validate_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid")),
    )

    with pytest.raises(LEARNING.LearningNotAdmitted, match="stale_market_package"):
        LEARNING.invoke_loop(args, "hourly", {}, ["review-1"], tmp_path)

    assert model_calls == 1
    assert admission_calls == 2


def test_deferred_learner_retry_window_spans_a_full_scheduler_interval() -> None:
    assert LEARNING.LEARNING_DEFER_RETRY_WINDOW_SECONDS >= 3600


def test_eval_profit_lock_is_not_cognitive_failure_evidence() -> None:
    result = {
        "http_status": 422,
        "body": {"failed_check_code": "eval_target_locked"},
    }
    assert LEARNING.is_cognitive_rejection(result) is False


def test_entry_context_uses_the_selected_instruments_price_and_economics(tmp_path, monkeypatch) -> None:
    packet_path = tmp_path / "hermes" / "exchange" / "glitch" / "decision-packets" / "cycle-1.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text(json.dumps({"packet_id": "cycle-1", "packet_hash": "hash-1"}), encoding="utf-8")
    scenario = {
        "market": {
            "snapshot_hash": "snapshot-1",
            "candidates": [
                {"instrument": "MNQ", "current_price": 20000, "instrument_economics": {"point_value_usd": 2}},
                {"instrument": "MES", "current_price": 5000, "instrument_economics": {"point_value_usd": 5}},
            ],
        },
        "books": [{"master_account": "Sim101", "position_building_context": {"next_entry_role": "initial_position"}}],
    }
    captured = {}
    monkeypatch.setattr(LEARNING.DIRECT, "build_scenario", lambda _packet: scenario)

    def risk_legs(_intent, reference_price, economics):
        captured.update(reference_price=reference_price, economics=economics)
        return [{"planned_risk_usd": 25, "risk_points_per_contract": 5}]

    monkeypatch.setattr(LEARNING.DIRECT, "entry_risk_legs", risk_legs)
    context = LEARNING.entry_decision_context(
        tmp_path,
        {"cycle_id": "cycle-1", "instrument": "MES", "master_account": "Sim101"},
        {
            "intent_id": "intent-1",
            "instrument": "MES",
            "account": "Sim101",
            "action": "ENTER_LONG",
            "quantity": 1,
            "take_profit_1": 5010,
            "snapshot_hash": "snapshot-1",
            "decision_audit": {
                "decisive_evidence": (
                    "SELECTION_EV=direction=LONG;entry=5000;stop=4995;target=5010;"
                    "risk_points=5;reward_points=10;friction_points=0;"
                    "breakeven_target_first=0.333;estimated_target_first_range=40-50%;"
                    "now_ev=POSITIVE;wait_price=5001;wait_ev=NEGATIVE;decisive_reason=fixture"
                )
            },
        },
        None,
    )
    assert context["decision_reference_price"] == 5000
    assert captured == {"reference_price": 5000, "economics": {"point_value_usd": 5}}
    assert context["selection_ev_arithmetic"]["status"] == "reconciled"


def test_selection_ev_arithmetic_mismatch_is_audit_only() -> None:
    audit = LEARNING.selection_ev_arithmetic_audit({
        "decisive_evidence": (
            "SELECTION_EV=direction=LONG;entry=7740;stop=7737.5;target=7746;"
            "risk_points=2.5;reward_points=6;friction_points=0.25;"
            "breakeven_target_first=0.50;estimated_target_first_range=55-65%;"
            "now_ev=POSITIVE;wait_price=7741;wait_ev=NEGATIVE;decisive_reason=fixture"
        )
    })

    assert audit["status"] == "mismatch"
    assert audit["effect"] == "audit_only_no_execution_effect"
    assert audit["deterministic_breakeven_target_first"] == 0.32352941
    assert audit["absolute_error_percentage_points"] == 17.6471


def test_selection_ev_probability_and_verdict_mismatch_is_audit_only() -> None:
    audit = LEARNING.selection_ev_arithmetic_audit(
        {
            "decisive_evidence": (
                "SELECTION_EV=direction=LONG;entry=100;stop=95;target=110;"
                "risk_points=5;reward_points=10;friction_points=0;"
                "breakeven_target_first=0.333;estimated_target_first_range=20-30%;"
                "now_ev=POSITIVE;wait_price=101;wait_ev=NEGATIVE;decisive_reason=fixture"
            )
        },
        {"event": "STOP_BEFORE_PRIMARY_TARGET", "probability": 0.75},
    )

    assert audit["status"] == "mismatch"
    assert audit["effect"] == "audit_only_no_execution_effect"
    assert audit["arithmetic_status"] == "reconciled"
    assert audit["forecast_range_status"] == "reconciled"
    assert audit["range_vs_break_even"] == "below_break_even"
    assert audit["expected_now_ev_from_range"] == "NEGATIVE"
    assert audit["now_ev_status"] == "mismatch"


def test_completed_bar_observation_uses_authoritative_last_completed_bar() -> None:
    frame = {
        "minute_id": "20260817T0531Z",
        "market_snapshot": {
            "instruments": [{
                "instrument": "MNQ",
                "current_price": 101,
                "descriptive_state": {
                    "native_observations": {
                        "last_completed_bar": {
                            "utc_time": "20260817T0530Z",
                            "closed_utc": "20260817T0531Z",
                            "high": 102,
                            "low": 99,
                            "close": 100,
                        }
                    }
                },
                "timeframe_bars": [{"minutes": 1, "high": 999, "low": 1, "close": 50}],
            }]
        },
    }
    observed = LEARNING._instrument_observation(frame, "MNQ")
    assert observed == {
        "minute_id": "20260817T0530Z",
        "closed_utc": "20260817T0531Z",
        "completed": True,
        "high": 102.0,
        "low": 99.0,
        "close": 100.0,
    }


def test_compact_episode_preserves_prompt_and_opportunity_identity() -> None:
    compact = LEARNING.compact_episode({
        "schema_version": "glitch.hermes.decision_episode.v2",
        "episode_id": "episode-1",
        "prompt_version": "prompt-v2",
        "cognitive_bundle_hash": "hash-1",
        "opportunity_group_id": "group-1",
        "correlated_episode_ids": ["episode-1", "episode-2"],
        "instrument_point_value_usd": 2,
        "instrument_tick_size": 0.25,
        "entry_range_supersession": {"favorable_supersession": True},
        "selection_ev_arithmetic": {
            "status": "mismatch",
            "effect": "audit_only_no_execution_effect",
        },
        "prior_cognition": {"source_cycle_id": "prior"},
    })
    assert compact["prompt_version"] == "prompt-v2"
    assert compact["opportunity_group_id"] == "group-1"
    assert compact["correlated_episode_ids"] == ["episode-1", "episode-2"]
    assert compact["instrument_point_value_usd"] == 2
    assert compact["selection_ev_arithmetic"]["status"] == "mismatch"
    assert "prior" in compact["prior_cognition"]


def test_rebuilt_decision_episode_uses_each_instruments_own_path(tmp_path, monkeypatch) -> None:
    exchange = tmp_path / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    cycle = "20260812T120000Z"
    for relative in (
        f"hermes/outbox/{cycle}.json",
        f"hermes/receipts/{cycle}.json",
        f"glitch/decision-packets/{cycle}.json",
    ):
        (exchange / relative).parent.mkdir(parents=True, exist_ok=True)
    intent = {
        "intent_id": "intent-mes",
        "created_utc": "2026-08-12T12:00:00Z",
        "instrument": "MES",
        "account": "Sim101",
        "operator_profile": "glitch",
        "action": "NOTHING",
    }
    (exchange / f"hermes/outbox/{cycle}.json").write_text(json.dumps({"decisions": [intent]}), encoding="utf-8")
    (exchange / f"hermes/receipts/{cycle}.json").write_text(json.dumps({"complete": True, "results": []}), encoding="utf-8")
    (exchange / f"glitch/decision-packets/{cycle}.json").write_text(json.dumps({"packet_id": cycle}), encoding="utf-8")
    frames = exchange / "glitch" / "minute-frames"
    frames.mkdir(parents=True)
    for index in range(1, 6):
        frame = {
            "minute_id": f"m{index}",
            "market_snapshot": {"instruments": [
                {"instrument": "MNQ 09-26", "current_price": 20000 + index, "timeframe_bars": [{"minutes": 1, "high": 20000 + index, "low": 19999 + index, "close": 20000 + index}]},
                {"instrument": "MES 09-26", "current_price": 5000 + index, "timeframe_bars": [{"minutes": 1, "high": 5000 + index, "low": 4999 + index, "close": 5000 + index}]},
            ]},
        }
        (frames / f"20260812T12000{index}Z.json").write_text(json.dumps(frame), encoding="utf-8")
    scenario = {
        "market": {"candidates": [{"instrument": "MNQ", "current_price": 20000}, {"instrument": "MES", "current_price": 5000}]},
        "books": [{
            "route_id": "glitch",
            "exposure": [{"current_quantity_by_selected_scope": 0}],
            "position_building_context": {},
            "instrument_contexts": {"MES": {"instrument": "MES", "point_value_usd": 5}},
            "valid_entry_quantities": [1, 4],
        }],
    }
    scenario["market"]["candidates"][0]["instrument_economics"] = {
        "point_value_usd": 2, "tick_size": 0.25,
    }
    scenario["market"]["candidates"][1]["instrument_economics"] = {
        "point_value_usd": 5, "tick_size": 0.25,
    }
    monkeypatch.setattr(LEARNING.DIRECT, "build_scenario", lambda _packet: scenario)
    monkeypatch.setattr(LEARNING.DIRECT, "receipt_classification", lambda _receipt: "successful")
    monkeypatch.setattr(
        LEARNING.DIRECT,
        "latest_prior_cognition",
        lambda *_args: {"source_cycle_id": "prior", "decisive_evidence": "MNQ bearish path"},
    )

    episodes = LEARNING.collect_decision_episodes(tmp_path, exchange, supervisor, rebuild=True)
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["pre_decision_state"]["initial_price"] == 5000
    assert episode["upward_excursion_points"] == 5
    assert episode["candidate_forward_summaries"]["MNQ"]["initial_price"] == 20000
    assert episode["candidate_forward_summaries"]["MES"]["initial_price"] == 5000
    assert episode["candidate_forward_summaries"]["MNQ"]["point_value_usd"] == 2
    assert episode["candidate_forward_summaries"]["MNQ"]["available_quantities"] == [1, 4]
    assert episode["candidate_forward_summaries"]["MNQ"]["one_contract_upward_mfe_usd"] == 10
    assert episode["candidate_forward_summaries"]["MNQ"]["max_quantity_upward_mfe_usd"] == 40
    assert episode["pre_decision_state"]["position_building_context"]["instrument"] == "MES"
    assert episode["prior_cognition"]["source_cycle_id"] == "prior"


def test_correlated_account_outcomes_are_one_learning_idea() -> None:
    outcomes = [
        {"intent_id": "a", "cycle_id": "cycle-1", "instrument": "MNQ", "action": "ENTER_LONG", "exit_utc": "2026-08-12T12:01:00Z"},
        {"intent_id": "b", "cycle_id": "cycle-1", "instrument": "MNQ", "action": "ENTER_LONG", "exit_utc": "2026-08-12T12:01:01Z"},
    ]
    ideas = LEARNING.deduplicate_market_ideas(outcomes)
    assert len(ideas) == 1
    assert ideas[0]["_correlated_intent_ids"] == ["a", "b"]


def test_management_evidence_is_bounded_but_preserves_non_hold_actions() -> None:
    rows = []
    for index in range(100):
        action = "MOVE_STOP" if index == 5 else "HOLD"
        rows.append({
            "recorded_utc": f"2026-08-12T12:{index // 60:02d}:{index % 60:02d}Z",
            "intent": {"intent_id": f"i-{index}", "action": action},
        })
    bounded = LEARNING.bounded_management_decisions(rows)
    assert len(bounded) <= LEARNING.MAX_DEBRIEF_MANAGEMENT_DECISIONS
    assert any(row.get("intent", {}).get("action") == "MOVE_STOP" for row in bounded)


def test_debrief_evidence_fits_oldest_complete_slice_with_repair_room(tmp_path, monkeypatch) -> None:
    outcomes = [{"intent_id": f"intent-{index}"} for index in range(4)]

    monkeypatch.setattr(LEARNING, "MAX_PROMPT_CHARS", 150)
    monkeypatch.setattr(LEARNING, "LEARNING_REPAIR_PROMPT_RESERVE_CHARS", 20)
    monkeypatch.setattr(
        LEARNING,
        "debrief_evidence",
        lambda _glitch_data, rows: [{"intent_id": row["intent_id"]} for row in rows],
    )
    monkeypatch.setattr(LEARNING, "continuity", lambda _supervisor: {})
    monkeypatch.setattr(LEARNING, "output_template", lambda *_args: {})
    monkeypatch.setattr(
        LEARNING,
        "build_prompt",
        lambda _loop, evidence, _template, _continuity: "x" * (10 + 40 * len(evidence)),
    )

    batch, evidence = LEARNING.fit_debrief_evidence(tmp_path, outcomes, tmp_path)

    assert [row["intent_id"] for row in batch] == ["intent-0", "intent-1", "intent-2"]
    assert [row["intent_id"] for row in evidence] == ["intent-0", "intent-1", "intent-2"]


def test_hourly_evidence_fits_oldest_complete_slice_with_repair_room(tmp_path, monkeypatch) -> None:
    rows = [{"episode_id": f"episode-{index}", "payload": "x" * 40} for index in range(5)]

    monkeypatch.setattr(LEARNING, "MAX_PROMPT_CHARS", 150)
    monkeypatch.setattr(LEARNING, "LEARNING_REPAIR_PROMPT_RESERVE_CHARS", 20)
    monkeypatch.setattr(LEARNING, "compact_episode", lambda row: dict(row))
    monkeypatch.setattr(LEARNING, "continuity", lambda _supervisor: {})
    monkeypatch.setattr(LEARNING, "output_template", lambda *_args: {})
    monkeypatch.setattr(
        LEARNING,
        "build_prompt",
        lambda _loop, evidence, _template, _continuity: "x" * (10 + 50 * len(evidence["episodes"])),
    )

    batch, evidence = LEARNING.fit_hourly_evidence(rows, tmp_path)

    assert [row["episode_id"] for row in batch] == ["episode-0", "episode-1"]
    assert evidence["scope"]["evidence_episode_ids"] == ["episode-0", "episode-1"]
    assert [row["episode_id"] for row in evidence["episodes"]] == ["episode-0", "episode-1"]


def test_hourly_prompt_reviews_nothing_with_bounded_counterfactual_geometry() -> None:
    prompt = LEARNING.build_prompt(
        "hourly",
        {"episodes": []},
        LEARNING.output_template("hourly", []),
        {},
    )

    assert "conservative noise-aware counterfactual zone" in prompt
    assert "absence of an actual trade" in prompt
    assert "target-before-stop chronology" in prompt
    assert "Classify every supplied flat NOTHING episode exactly once" in prompt
    assert "cite representative episode IDs" in prompt
    assert "strongest rejected candidate" in prompt
    assert "point_value_usd and available_quantities" in prompt

    review = LEARNING.output_template("hourly", ["review-1"])["records"][0][
        "opportunity_review"
    ]
    assert set(review) == {
        "results",
        "missed_opportunity_episode_ids",
        "disciplined_abstention_episode_ids",
        "uncertain_episode_ids",
        "summary",
    }


def test_compact_review_preserves_structured_opportunity_accountability() -> None:
    value = {
        "review_id": "review-1",
        "opportunity_review": {
            "missed_opportunity_episode_ids": ["episode-1"],
            "disciplined_abstention_episode_ids": [],
            "uncertain_episode_ids": ["episode-2"],
            "summary": "Repeated geometry veto affected episode-1.",
        },
    }

    assert LEARNING.compact_review(value)["opportunity_review"] == value["opportunity_review"]


def test_planning_episode_projection_drops_raw_packet_repetition() -> None:
    value = {
        "episode_id": "episode-1",
        "instrument": "MNQ",
        "action": "NOTHING",
        "reason": "r" * 20_000,
        "pre_decision_state": {"raw": "x" * 100_000},
        "forward_observations": [{"raw": "x" * 100_000}],
        "candidate_forward_summaries": {"MNQ": {"objective": "x" * 20_000}},
        "proposed_geometry": {"entry": 100, "stop": 90, "target": 120},
        "instrument_point_value_usd": 2,
    }

    compact = LEARNING.compact_planning_episode(value)
    encoded = json.dumps(compact, separators=(",", ":"), ensure_ascii=False)

    assert "pre_decision_state" not in compact
    assert "forward_observations" not in compact
    assert compact["instrument_point_value_usd"] == 2
    assert len(encoded) < 15_000


def test_planning_evidence_keeps_newest_rows_inside_repair_budget(tmp_path, monkeypatch) -> None:
    rows = [{"episode_id": f"episode-{index}"} for index in range(3)]
    monkeypatch.setattr(LEARNING, "MAX_PROMPT_CHARS", 100)
    monkeypatch.setattr(LEARNING, "LEARNING_REPAIR_PROMPT_RESERVE_CHARS", 10)
    monkeypatch.setattr(LEARNING, "compact_review", lambda row: row)
    monkeypatch.setattr(LEARNING, "compact_planning_episode", lambda row: row)
    monkeypatch.setattr(LEARNING, "performance_summary", lambda _rows: {})
    monkeypatch.setattr(LEARNING.DIRECT, "read_optional_json", lambda _path: {})
    monkeypatch.setattr(LEARNING, "continuity", lambda _supervisor: {})
    monkeypatch.setattr(LEARNING, "output_template", lambda *_args: {})
    monkeypatch.setattr(
        LEARNING,
        "build_prompt",
        lambda _loop, evidence, _template, _continuity: "x" * (60 + 20 * len(evidence["recent_episodes"])),
    )

    evidence, review_ids = LEARNING.fit_planning_evidence(
        [{"review_id": "review-1"}], rows, [], tmp_path, "plan-1"
    )

    assert [row["episode_id"] for row in evidence["recent_episodes"]] == ["episode-2"]
    assert review_ids == ["review-1"]
