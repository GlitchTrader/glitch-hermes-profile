"""Causal excursion and bounded post-exit evidence; never orders or LLM calls."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from test_direct_cycle_contracts import DIRECT
from test_learning_p0_repairs import LEARNING


BASE = datetime(2026, 9, 18, 3, tzinfo=timezone.utc)


def frame(minute, high=104, low=98, contract="MNQ 12-26"):
    start = BASE + timedelta(minutes=minute)
    end = start + timedelta(minutes=1)
    return {"minute_id": end.strftime("%Y%m%dT%H%MZ"), "captured_utc": end.isoformat(),
            "market_snapshot": {"instruments": [{"instrument": "MNQ", "instrument_full_name": contract,
                "timeframe_bars": [{"minutes": 1, "descriptive_state": {"native_observations": {
                    "last_completed_bar": {"utc_time": start.isoformat(), "closed_utc": end.isoformat(),
                        "open": 100, "high": high, "low": low, "close": 100,
                        "volume": 5, "completeness": "complete"}}}}]}]}}


def excursion(frames, side="long", previous=None, **kwargs):
    args = dict(contract="MNQ 12-26", start=BASE + timedelta(seconds=30),
                as_of=BASE + timedelta(minutes=5), side=side, entry_price=100, quantity=1,
                point_value=2, previous=previous)
    args.update(kwargs)
    return DIRECT.post_entry_bar_excursion(frames, **args)


@pytest.mark.parametrize("side,mfe,mae", [("long", 18.5, -10), ("short", 10, -18.5)])
def test_excursion_uses_only_known_completed_post_entry_contract_bars(side, mfe, mae):
    frames = [frame(0, 999), frame(1, 109.25, 95), frame(2, 999, contract="MNQ 09-26"), frame(6, 999)]
    before = copy.deepcopy(frames)
    value = excursion(frames, side)
    assert value["status"] == "observed"
    assert value["mfe_gross_usd"] == mfe
    assert value["mae_gross_usd"] == mae
    assert value["observed_bars"] == 1
    assert value["basis"] == "completed_bar_prices_not_executable_pnl"
    assert frames == before


def test_excursion_carries_peak_without_recounting_overlapping_bars():
    first = excursion([frame(1, 110)])
    value = excursion([frame(1, 110), frame(2, 103)], previous=first)
    assert value["mfe_gross_usd"] == 20
    assert value["observed_bars"] == 2
    for changes in ({"entry_price": 101}, {"quantity": 2}, {"contract": "MNQ 03-27"},
                    {"start": BASE + timedelta(minutes=1)}, {"as_of": BASE}):
        assert excursion([], previous=first, **changes)["status"] == "unavailable"


@pytest.mark.parametrize("damage", ["future_observation", "partial", "invalid_high", "missing_time", "duplicate_contract", "native_contract_mismatch"])
def test_unreliable_bars_are_not_excursions(damage):
    item = frame(1)
    bar = item["market_snapshot"]["instruments"][0]["timeframe_bars"][0]["descriptive_state"]["native_observations"]["last_completed_bar"]
    if damage == "future_observation":
        item["captured_utc"] = (BASE + timedelta(minutes=9)).isoformat()
    elif damage == "partial":
        bar["completeness"] = "partial"
    elif damage == "invalid_high":
        bar["high"] = 50
    elif damage == "missing_time":
        bar.pop("closed_utc")
    elif damage == "native_contract_mismatch":
        item["market_snapshot"]["instruments"][0]["timeframe_bars"][0]["descriptive_state"]["native_observations"]["instrument_full_name"] = "MNQ 09-26"
    else:
        item["market_snapshot"]["instruments"] *= 2
    assert excursion([item])["status"] == "unavailable"


def outcome():
    return {"contract": "MNQ 12-26", "instrument": "MNQ", "action": "ENTER_LONG",
            "exit_utc": (BASE + timedelta(seconds=30)).isoformat(), "planned_stop": 90,
            "planned_target": 110}


def save_frames(root, values):
    path = root / "hermes/exchange/glitch/minute-frames"
    path.mkdir(parents=True, exist_ok=True)
    for item in values:
        (path / (item["minute_id"] + ".json")).write_text(json.dumps(item), encoding="utf-8")


def test_post_exit_reaches_original_target_without_rewriting_realized_outcome(tmp_path):
    row = outcome()
    original = copy.deepcopy(row)
    save_frames(tmp_path, [frame(i, 112 if i == 6 else 104) for i in range(30)])
    value = LEARNING.post_exit_bracket_review(tmp_path, row, BASE + timedelta(hours=1))
    assert value["chronology"] == "target_before_stop"
    assert value["first_touch_bar_utc"] == (BASE + timedelta(minutes=6)).isoformat()
    assert value["window_minutes"] == 30
    assert value["effect"] == "retrospective_only_not_fill_or_forecast_label"
    assert row == original
    compact = LEARNING.compact_episode({"facts": {"post_exit_bracket_review": value}})
    assert compact["deterministic_facts"]["post_exit_bracket_review"] == value


@pytest.mark.parametrize("damage,expected", [("same_bar", "ambiguous_same_bar"),
    ("exit_bar", "ambiguous_exit_bar"), ("gap", "unresolved_gap"), ("rollover", "unresolved_gap"),
    ("no_touch", "neither_reached"), ("stop", "stop_before_target")])
def test_post_exit_does_not_invent_touch_order(tmp_path, damage, expected):
    values = [frame(i, 112 if i == 6 else 104, 88 if damage == "stop" and i == 3 else 98) for i in range(30)]
    if damage == "same_bar":
        values[6] = frame(6, 112, 88)
    elif damage == "exit_bar":
        values[0] = frame(0, 112)
    elif damage == "gap":
        values.pop(2)
    elif damage == "rollover":
        values[2] = frame(2, contract="MNQ 03-27")
    elif damage == "no_touch":
        values[6] = frame(6)
    save_frames(tmp_path, values)
    value = LEARNING.post_exit_bracket_review(tmp_path, outcome(), BASE + timedelta(hours=1))
    assert value["chronology"] == expected


def test_post_exit_review_cannot_read_future_evidence(tmp_path):
    save_frames(tmp_path, [frame(i, 112 if i == 6 else 104) for i in range(30)])
    value = LEARNING.post_exit_bracket_review(tmp_path, outcome(), BASE + timedelta(minutes=4))
    assert value["chronology"] == "pending_window"
    assert value["first_touch_bar_utc"] is None
    assert not LEARNING.debrief_window_mature(outcome(), BASE + timedelta(minutes=29))
    assert LEARNING.debrief_window_mature(outcome(), BASE + timedelta(minutes=31))


def test_management_uses_one_standard_not_pnl_color():
    from test_management_continuity import positioned_scope
    from test_direct_cycle_contracts import fresh_model_admission_packet
    scope = positioned_scope("MNQ")
    scope.update(cycle_id="test", market={"candidates": [{"instrument": "MNQ"}]})
    prompt = DIRECT.build_prompt(fresh_model_admission_packet(), scope, {})
    assert "same decision standard while green and red" in prompt
    assert "post_entry_bar_excursion" in prompt
    assert "probability estimate alone is not changed market evidence" in prompt
    assert "do not wait for it to turn red" in prompt
    assert "EXIT need not await original invalidation" in prompt


@pytest.mark.parametrize("quantity,expected", [(1, "observed"), (2, "unavailable")])
def test_active_state_delivers_bar_excursion_without_overwriting_native_pnl(tmp_path, quantity, expected):
    data, exchange = tmp_path / "data", tmp_path / "exchange"
    (data / "intents").mkdir(parents=True)
    stamp = (BASE + timedelta(seconds=30)).isoformat()
    intent = {"intent_id": "entry", "created_utc": stamp, "action": "ENTER_LONG", "account": "Sim101",
              "instrument": "MNQ", "quantity": 1, "stop_loss": 90, "take_profit_1": 120}
    (data / "intents/decisions.jsonl").write_text(json.dumps({"intent": intent}))
    records = [{"intent_id": "entry", "recorded_utc": stamp, "code": "master_entry_submitted"},
               {"intent_id": "entry", "recorded_utc": stamp, "code": "group_structural_brackets_submitted",
                "message": "account=Sim101|fill=100|point_value_usd=2|tick_size=0.25|leg1_qty=1|sl1=90|tp1=120"}]
    (data / "intents/executions.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    item = frame(1, 109.25)
    item["portfolio_snapshot"] = {"created_utc": item["captured_utc"], "accounts": [{"account": "Sim101",
        "positions": [{"instrument": "MNQ 12-26", "instrument_root": "MNQ", "market_position": "Long",
                       "quantity": quantity, "average_price": 100, "unrealized_pnl": 12}],
        "working_order_details": []}]}
    packet = {"frames": [item]}
    scenario = {"books": [{"master_account": "Sim101", "instrument_contexts": {"MNQ": {
        "current_price": 106, "point_value_usd": 2, "tick_size": .25}}}]}
    before = copy.deepcopy(packet)
    trade = DIRECT.active_trade_state(packet, scenario, data, exchange)["trades"][0]
    assert trade["post_entry_bar_excursion"]["status"] == expected
    if expected == "observed":
        assert trade["post_entry_bar_excursion"]["mfe_gross_usd"] == 18.5
    assert trade["peak_unrealized_pnl_usd"] == 12
    assert trade["unrealized_pnl_usd"] == 12
    assert packet == before
    assert DIRECT.ledger_for_model({"active_trade_state": {"trades": [trade]}}, True)["active_trade_state"]["trades"][0] == trade


def test_post_exit_short_and_unavailable_geometry(tmp_path):
    save_frames(tmp_path, [frame(i, 104, 88 if i == 6 else 98) for i in range(30)])
    row = {**outcome(), "action": "ENTER_SHORT", "planned_stop": 110, "planned_target": 90}
    assert LEARNING.post_exit_bracket_review(tmp_path, row, BASE + timedelta(hours=1))["chronology"] == "target_before_stop"
    for change in ({"planned_stop": None}, {"planned_target": float("nan")}, {"contract": "MNQ"},
                   {"exit_utc": "not-a-time"}, {"planned_stop": 80}):
        assert LEARNING.post_exit_bracket_review(tmp_path, {**row, **change})["chronology"] == "unavailable"


def test_learner_debrief_matures_once_and_keeps_retrospective_evidence_separate():
    import ast
    from pathlib import Path
    tree = ast.parse(Path(LEARNING.__file__).read_text(encoding="utf-8"))
    source = ast.unparse(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_once"))
    assert "debrief_window_mature(row, now)" in source
    prompt = LEARNING.build_prompt("debrief", [], LEARNING.output_template("debrief", []), {})
    assert "post_exit_bracket_review" in prompt
    assert "not information available at exit" in prompt
    assert "plausible exit prose" in prompt
