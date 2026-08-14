import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_hermes_learning_cycle_p0",
    ROOT / "scripts" / "run-hermes-learning-cycle.py",
)
LEARNING = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LEARNING)


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
        },
        None,
    )
    assert context["decision_reference_price"] == 5000
    assert captured == {"reference_price": 5000, "economics": {"point_value_usd": 5}}


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
            "valid_entry_quantities": [1],
        }],
    }
    monkeypatch.setattr(LEARNING.DIRECT, "build_scenario", lambda _packet: scenario)
    monkeypatch.setattr(LEARNING.DIRECT, "receipt_classification", lambda _receipt: "successful")

    episodes = LEARNING.collect_decision_episodes(tmp_path, exchange, supervisor, rebuild=True)
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["pre_decision_state"]["initial_price"] == 5000
    assert episode["upward_excursion_points"] == 5
    assert episode["candidate_forward_summaries"]["MNQ"]["initial_price"] == 20000
    assert episode["candidate_forward_summaries"]["MES"]["initial_price"] == 5000


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

    review = LEARNING.output_template("hourly", ["review-1"])["records"][0][
        "opportunity_review"
    ]
    assert set(review) == {
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
