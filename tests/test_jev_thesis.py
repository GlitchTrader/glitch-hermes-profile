"""Thesis inputs cannot see future/native outcomes; probes wait for response time."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/jev"))
import thesis

T = thesis.timestamp("2026-09-09T00:00:00Z")


def mark(second=60, price=101, contract="MES 09-26"):
    return {"source": T+second, "available": T+second+1, "contract": contract, "price": price,
            "snapshot_id": str(second), "frames": {"1": {"atr": 2}}, "flow": {"delta_change": 5, "vwap": 100},
            "movement_points": {}, "efficiency": {}, "quality": {}}


def trade():
    return {"symbol":"MES 09-26", "side":"Long", "entry":"2026-09-09T00:00:00Z", "entry_price":100,
            "planned_stop":98, "planned_target":104, "quantity":1, "gross":15,
            "exit":"2026-09-09T00:10:00Z", "authored_entry_reason":"Recovery above 100.",
            "authored_disconfirming_evidence":"Sustained failure below 98.",
            "trade_id":"SIM101|private", "net":14, "authored_future_action":"EXIT"}


def response(failed=.1, deteriorating=.7):
    return {"status":"ok", "returned_model":"jev-1.13.0", "latency_ms":500,
            "response":{"answers":{"thesis_state":{"type":"choice", "choice":"DETERIORATING",
             "probabilities":{"HELD":1-failed-deteriorating,"DETERIORATING":deteriorating,"FAILED":failed,"UNKNOWN":0}}}}}


def test_future_history_and_terminal_outcomes_cannot_change_inference_state():
    t=trade();m=mark();state=thesis.build_state(t,m,[m])
    changed=copy.deepcopy(t);changed.update(gross=-10000,net=-10000,exit="2030-01-01T00:00:00Z",authored_future_action="HOLD")
    future=mark(120,10000)
    assert thesis.build_state(changed,m,[m,future]) == state
    assert not {"net","gross","exit","trade_id","authored_future_action"} & state.keys()
    assert "SIM101" not in str(state)
    assert len(state["recent_marks"]) == 1


def test_paired_arms_differ_only_in_authored_text():
    a=thesis.build_state(trade(),mark(),[mark()]);b=thesis.build_state(trade(),mark(),[mark()],False)
    assert a.pop("authored_thesis") is not None
    assert b.pop("authored_thesis") is None
    assert a == b


def test_contract_and_entry_time_are_hard_input_boundaries():
    with pytest.raises(ValueError,match="contract"):
        thesis.build_state(trade(),mark(contract="MES 12-26"),[])
    with pytest.raises(ValueError,match="before_entry"):
        thesis.build_state(trade(),mark(0),[])


def test_persistence_breaks_on_unknown_result_gap_and_duplicate_source():
    a={"mark":mark(),"response":response()};b={"mark":mark(120),"response":response()}
    assert thesis.first_signal([a,b]) is b
    assert thesis.first_signal([a,{"mark":mark(300),"response":response()}]) is None
    assert thesis.first_signal([a,{"mark":mark(180),"response":response()}]) is None  # one missing publication
    assert thesis.first_signal([a,{"mark":mark(90),"response":{}},b]) is None
    assert thesis.first_signal([a,a]) is None


def test_provider_mismatch_or_named_choice_disagreement_cannot_signal():
    a={"mark":mark(),"response":response()};b={"mark":mark(120),"response":response()}
    b["response"]["returned_model"]="jev-latest"
    assert thesis.first_signal([a,b]) is None
    b["response"]=response();b["response"]["response"]["answers"]["thesis_state"]["choice"]="HELD"
    assert thesis.first_signal([a,b]) is None


def test_exit_price_must_be_observed_after_response_and_before_native_close():
    t=trade();signal={"mark":mark(120),"response":response()}
    old=mark(121,1000);old["available"]=T+140  # published later, source before inference ready
    fresh=mark(180,102)
    probe=thesis.exit_probe(t,signal,[old,fresh,mark(700,2000)])
    assert probe["fill_price"] == 102
    assert probe["gross_advantage"] == -5  # damages the actual winner
    assert probe["extra_exit_cost"] == 2.425
    assert probe["cost_penalized_advantage"] == -7.425
    assert thesis.exit_probe(t,signal,[mark(700)])["status"] == "no_post_response_mark_before_native_exit"


def test_null_descriptive_data_does_not_manufacture_flow():
    snap={"created_utc":"2026-09-09T00:01:01Z","snapshot_id":"s","instruments":[{
        "instrument_full_name":"MES 09-26","timestamp_utc":"2026-09-09T00:01:00Z","is_fresh":True,"current_price":101,
        "descriptive_state":None,"timeframe_bars":[{"minutes":1,"utc_time":"2026-09-09T00:01:00Z", "descriptive_state":None,
        "indicators":{"atr":2,"order_flow_vwap":100,"order_flow_delta_change":500}}]}]}
    m=thesis.mark_from_snapshot(snap,"MES 09-26")
    assert not m["quality"]["flow_available"]
    assert m["flow"]["vwap"] is None and m["flow"]["delta_change"] is None
    assert m["frames"]["1"]["completeness"] == "unknown"


def test_embedded_wrong_contract_cannot_supply_flow_or_frame_indicators():
    envelope={"native_observations":{"instrument_full_name":"MES 12-26"},"descriptive_state":{
        "quality":{"as_of_utc":"2026-09-09T00:01:00Z","order_flow_status":"available"},
        "flow":{"delta_change":999}}}
    snap={"created_utc":"2026-09-09T00:01:01Z","snapshot_id":"s","instruments":[{
        "instrument_full_name":"MES 09-26","timestamp_utc":"2026-09-09T00:01:00Z","is_fresh":True,"current_price":101,
        "descriptive_state":envelope,"timeframe_bars":[{"minutes":1,"utc_time":"2026-09-09T00:01:00Z",
        "descriptive_state":envelope,"indicators":{"atr":2}}]}]}
    with pytest.raises(ValueError,match="embedded_contract_mismatch"):
        thesis.mark_from_snapshot(snap,"MES 09-26")


def test_negative_cost_cannot_manufacture_exit_benefit():
    with pytest.raises(ValueError,match="cost"):
        thesis.exit_probe(trade(),None,[],commission=-1)
