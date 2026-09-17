"""Entry thesis and native action results must survive the entry/management handoff."""
import copy
import json

import pytest

from test_direct_cycle_contracts import DIRECT


@pytest.mark.parametrize("action,path", (("ENTER_LONG", "BULLISH_PATH"), ("ENTER_SHORT", "BEARISH_PATH")))
def test_geometry_keeps_only_selected_instrument_and_direction(action, path):
    evidence = (
        "INSTRUMENT_COMPARISON_V1\nINSTRUMENT MES:\nNOISE_AND_GEOMETRY=wrong instrument\n"
        "INSTRUMENT MNQ:\nCURRENT_AUCTION=parent rotation\n"
        "BULLISH_PATH=long path\nBEARISH_PATH=short path\n"
        "OBJECTIVE_INVALIDATION=destination and parent failure\n"
        "ENTRY_RANGE=translated edges\nNOISE_AND_GEOMETRY=allowed pullback\n"
        "including a probe below the trigger\nASYMMETRY=not required again\n"
        "RANKING=MNQ,MES\nSELECTION_REASON=not the plan\n"
    )
    intent = {"instrument": "MNQ 12-26", "action": action, "decision_audit": {"decisive_evidence": evidence}}
    original = copy.deepcopy(intent)
    context = DIRECT.entry_plan_geometry(intent)
    assert context == {
        "CURRENT_AUCTION": "parent rotation", path: "long path" if action == "ENTER_LONG" else "short path",
        "OBJECTIVE_INVALIDATION": "destination and parent failure", "ENTRY_RANGE": "translated edges",
        "NOISE_AND_GEOMETRY": "allowed pullback\nincluding a probe below the trigger",
    }
    assert intent == original


def test_trigger_geometry_carries_wager_and_allowed_pullback_without_inventing_fields():
    intent = {"instrument": "MNQ", "action": "ENTER_LONG", "decision_audit": {"decisive_evidence": (
        "TRIGGER_REVIEW_V1\nCURRENT_AUCTION=parent recovery\n"
        "REMAINING_OBJECTIVE_INVALIDATION=29592.5 target; parent failure29557.5\n"
        "ENTRY_RANGE_NOISE_GEOMETRY=29569 stop lies inside permitted pullback\n"
        "ALTERNATIVE_CANDIDATES=MES not chosen\nSELECTION_ACTION=ENTER_LONG\n"
    )}}
    context = DIRECT.entry_plan_geometry(intent)
    assert list(context) == ["CURRENT_AUCTION", "REMAINING_OBJECTIVE_INVALIDATION", "ENTRY_RANGE_NOISE_GEOMETRY"]
    assert "permitted pullback" in context["ENTRY_RANGE_NOISE_GEOMETRY"]
    for legacy in ({}, {"decision_audit": None}, {"decision_audit": {"decisive_evidence": "unstructured older note"}}):
        assert DIRECT.entry_plan_geometry(legacy) == {}
    intent["decision_audit"]["decisive_evidence"] = "INSTRUMENT_COMPARISON_V1\nINSTRUMENT MES:\nNOISE_AND_GEOMETRY=not MNQ"
    assert DIRECT.entry_plan_geometry(intent) == {}


@pytest.mark.parametrize("as_of,status", (("19:54:41.650000", "pending"), ("19:55:00", "failed")))
def test_management_preserves_requested_protection_and_asof_native_result(tmp_path, as_of, status):
    data, exchange = tmp_path / "data", tmp_path / "exchange"
    (data / "intents").mkdir(parents=True)
    entry = {"intent_id": "entry", "created_utc": "2026-09-17T19:39:00Z", "action": "ENTER_LONG",
             "instrument": "MES", "account": "Sim101", "quantity": 1, "stop_loss": 7706.5, "take_profit_1": 7722.25,
             "decision_audit": {"decisive_evidence": "TRIGGER_REVIEW_V1\nCURRENT_AUCTION=parent recovery\nENTRY_RANGE_NOISE_GEOMETRY=allowed pullback to7706.75"}}
    move = {"intent_id": "move", "created_utc": "2026-09-17T19:54:41Z", "action": "MOVE_STOP", "instrument": "MES",
            "account": "Sim101", "protection_updates": [{"leg_id": "leg1", "stop_loss": 7711.25}]}
    hold = {**move, "intent_id": "hold", "action": "HOLD"}
    hold.pop("protection_updates")
    (data / "intents" / "decisions.jsonl").write_text("\n".join(json.dumps({"intent": i}) for i in (entry, move, hold)))
    failed = {"intent_id": "move", "recorded_utc": "2026-09-17T19:54:41.6660969Z", "status": "failed",
              "code": "native_protection_change_rejected", "message": "protection_market_side_invalid/stop=7711.25/market=7711.25"}
    results = [
        {"intent_id": "entry", "recorded_utc": entry["created_utc"], "code": "master_entry_submitted"},
        failed,  # File ordering cannot turn the later failure back into pending.
        {"intent_id": "move", "recorded_utc": "2026-09-17T19:54:41.6566149Z", "status": "pending", "code": "intent_dispatched"},
        {"intent_id": "move", "recorded_utc": "2026-09-17T19:54:41.600000Z", "status": "pending", "code": "intent_dispatched"},
        {"intent_id": "move", "recorded_utc": "2026-09-17T19:56:00Z", "status": "executed", "code": "future_result"},
        {"intent_id": "other", "recorded_utc": "2026-09-17T19:54:50Z", "status": "executed", "code": "unrelated"},
    ]
    (data / "intents" / "executions.jsonl").write_text("\n".join(json.dumps(r) for r in results))
    packet = {"frames": [{"created_utc": f"2026-09-17T{as_of}Z", "portfolio_snapshot": {"accounts": [{
        "account": "Sim101", "positions": [{"instrument_root": "MES", "market_position": "Long", "quantity": 1,
        "average_price": 7710.5, "unrealized_pnl": 3.75}], "working_order_details": [{"instrument_root": "MES",
        "name": "GL1-command-HS0-leg1", "order_type": "StopMarket", "order_state": "Working", "quantity": 1,
        "filled": 0, "stop_price": 7706.5, "leg_id": "leg1"}]}]}}]}
    scenario = {"books": [{"master_account": "Sim101", "instrument_contexts": {"MES": {
        "current_price": 7711.25, "point_value_usd": 5, "tick_size": .25}}}]}
    original = copy.deepcopy(packet)
    state = DIRECT.active_trade_state(packet, scenario, data, exchange)
    trade = state["trades"][0]
    assert "allowed pullback" in trade["entry_plans"][0]["geometry_context"]["ENTRY_RANGE_NOISE_GEOMETRY"]
    history = trade["recent_management"]
    assert history[0]["protection_updates"] == move["protection_updates"]
    assert history[0]["latest_execution_result"]["status"] == status
    if status == "failed":
        assert history[0]["latest_execution_result"]["code"] == failed["code"]
        assert history[0]["latest_execution_result"]["message"] == failed["message"]
    assert history[1]["protection_updates"] == []
    assert history[1]["latest_execution_result"] is None
    assert trade["working_orders"][0]["stop_price"] == 7706.5  # A request never rewrites native truth.
    assert packet == original
    assert DIRECT.ledger_for_model({"active_trade_state": state}, True)["active_trade_state"] == state


def test_prompt_preserves_entry_thesis_and_native_rejection_feedback():
    from test_management_continuity import positioned_scope
    from test_direct_cycle_contracts import fresh_model_admission_packet
    scope = positioned_scope("MES")
    scope.update(cycle_id="test", market={"candidates": [{"instrument": "MES"}]})
    prompt = DIRECT.build_prompt(fresh_model_admission_packet(), scope, {})
    assert "geometry_context" in prompt
    assert "review level is not automatically the chosen wager's failure" in prompt
    assert "latest_execution_result" in prompt
    assert "rejected protection request did not change the stop" in prompt
    assert "EXIT need not await original invalidation" in prompt
