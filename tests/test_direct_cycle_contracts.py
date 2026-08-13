import importlib.util
import json
import sys
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
