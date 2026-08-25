import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
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


def test_normalize_batch_relocates_misplaced_audit_wake_triggers() -> None:
    batch, scenario = valid_batch("2026-08-03T07:02:41.0414987Z")
    intent = batch["decisions"][0]
    intent["decision_audit"]["wake_triggers"] = []

    DIRECT.normalize_batch(batch, scenario)

    assert intent["wake_triggers"] == []
    assert set(intent["decision_audit"]) == DIRECT.DECISION_AUDIT_FIELDS
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
    scenario = {"books": [{"route_id": "glitch", "master_account": "Sim101"}]}

    state = DIRECT.active_trade_state(packet, scenario, glitch_data, exchange)
    trade = state["trades"][0]

    assert trade["entry_decision_utc"] == native_entry_utc
    assert trade["trade_age_seconds"] is not None and trade["trade_age_seconds"] < 10
    assert trade["working_orders"][0]["stop_price"] == 29569.75
    assert trade["working_orders"][1]["limit_price"] == 29459.75


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


def test_selection_ev_positive_nothing_is_observed_without_gating() -> None:
    value = (
        "direction=LONG;entry=100;stop=95;target=110;risk_points=5;reward_points=10;"
        "friction_points=0;breakeven_target_first=0.333;estimated_target_first_range=40-50%;"
        "now_ev=POSITIVE;wait_price=105;wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    assert DIRECT.validate_selection_ev(value, "NOTHING", 0, "test") == [
        "selection_ev_nothing_positive:0:test"
    ]


def test_selection_ev_numeric_arithmetic_is_audit_only() -> None:
    value = (
        "direction=LONG;entry=100;stop=95;target=110;"
        "risk_points=approximately 5 points (20 ticks);reward_points=10 pts;"
        "friction_points=not material;breakeven_target_first=about 33.3%;"
        "estimated_target_first_range=40-50%;now_ev=NEGATIVE;wait_price=105;"
        "wait_ev=NEGATIVE;decisive_reason=fixture"
    )
    DIRECT.validate_selection_ev(value, "NOTHING", 0, "test")

    inconsistent_audit = value.replace(
        "friction_points=not material",
        "friction_points=0",
    ).replace(
        "breakeven_target_first=about 33.3%",
        "breakeven_target_first=62% after qualitative discount",
    ).replace("now_ev=NEGATIVE", "now_ev=NEGATIVE (wait dominates)")
    DIRECT.validate_selection_ev(inconsistent_audit, "NOTHING", 0, "test")


def test_selection_ev_forecast_range_and_verdict_are_audit_only() -> None:
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

    DIRECT.validate_selection_ev(
        value, "ENTER_LONG", 0, "test", {**forecast, "probability": 0.8}
    )
    DIRECT.validate_selection_ev(
        value.replace("40-50%", "20-30%"),
        "ENTER_LONG",
        0,
        "test",
        {**forecast, "probability": 0.75},
    )


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
    assert "(risk_points + friction_points) / (risk_points + reward_points)" not in prompt
    assert "reconcile 1 - forecast.probability with estimated_target_first_range" not in prompt
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
    assert "rollback relative to peak MFE and initial risk" in positioned_prompt
    assert "HOLD must explain why rebased continuation value clearly exceeds EXIT" in positioned_prompt
    assert "EXIT after material MFE does not require original invalidation or accepted reversal" in positioned_prompt
    assert "derive and evaluate at least one candidate protection level" in positioned_prompt.lower()
    assert "cannot reject both MOVE_STOP and EXIT" in positioned_prompt
    assert "Never use a fixed MFE percentage" in positioned_prompt
    assert "rollback relative to peak MFE and initial risk" not in flat_prompt
    assert "cannot reject both MOVE_STOP and EXIT" not in flat_prompt


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
    assert "reconcile 1 - forecast.probability with estimated_target_first_range" not in prompt
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
