"""SIM advisory integration: causal identity, no-authority boundaries and fail-open reads."""
import copy
import json
import time

import pytest

import jev_evidence as ev
import jev_provider as provider
from jev_observation import build_state, decode_cache, digest, encoded
from test_jev_observation import NOW, iso, sample_cache
from test_jev_shadow import shadow, records


def authored(now=NOW):
    return {"recorded_utc": iso(now), "trades": [{
        "master_account": "Sim101", "account_status": "Sim", "instrument_full_name": "MNQ 12-26",
        "native_observed_utc": iso(now), "instrument": "MNQ", "side": "long", "quantity": 1,
        "average_price": 100, "entry_decision_utc": iso(now - 120), "entry_intent_ids": ["private-native-id"],
        "unrealized_pnl_usd": 2, "peak_unrealized_pnl_usd": 4, "trough_unrealized_pnl_usd": -2,
        "rollback_from_peak_usd": 2, "working_orders": [{"stop_price": 98, "name": "private-order"}],
        "entry_plans": [{"reason": "Buy accepted recovery; pullback to 99 can hold, failure below 98.",
                         "disconfirming_evidence": "Accepted trade below 98.", "change_condition": "Failed recovery.",
                         "planned_stop": 97.75, "planned_targets": [105]}]}]}


def provider_value():
    return {"model": provider.MODEL, "answers": {
        key: {"type": "choice", "choice": next(iter(q["criteria"])), "confidence": 1,
              "probabilities": {label: int(i == 0) for i, label in enumerate(q["criteria"])}}
        for key, q in ev.QUESTIONS.items()}}


def make_record(now=NOW, position=None, key=None):
    raw = encoded(sample_cache(now))
    instruments = decode_cache(raw, now)
    instruments["MNQ 12-26"]["frames"]["1"]["descriptive"]["path.signed_movement.15.points"] = 3
    state = ev.build_advisory_state(instruments, "MNQ 12-26", "epoch:1:abc", digest(raw), [],
                                   position or {"status": "unavailable"})
    result = {"eligible_for_research_scoring": True, "raw_response": json.dumps(provider_value()),
              "request_id": "1" * 32, "observation_id": state["observation_id"], "observation_hash": digest(raw),
              "state_hash": digest(state), "start_utc": iso(now + .1), "end_utc": iso(now + .5), "latency_ms": 400}
    return ev.evidence_record(result, state, key), state


def sink(tmp_path, row=None):
    root = tmp_path / "jev-shadow"; root.mkdir()
    row = row or make_record()[0]
    (root / "health.json").write_bytes(encoded({"schema_version": "glitch.jev.health.v1", "updated_utc": iso(NOW),
                "mode": "EVIDENCE", "status": "running", "process_epoch": "epoch"}))
    (root / "hermes-evidence.json").write_bytes(encoded({"schema_version": ev.SCHEMA, "updated_utc": iso(NOW),
        "mode": "EVIDENCE", "process_epoch": "epoch", "account": "Sim101", "predictions": {"MNQ 12-26": row}}))
    packet = {"frames": [{"market_snapshot": {"instruments": [{"instrument": "MNQ", "instrument_full_name": "MNQ 12-26"}]},
                         "portfolio_snapshot": {"accounts": [{"account": "Sim101", "account_status": "Sim"}]}}]}
    return root, packet, {"books": [{"master_account": "Sim101"}]}


def test_fresh_advisory_keeps_probabilities_separate_from_native_bracket_forecast(tmp_path):
    root, packet, scenario = sink(tmp_path)
    result = ev.load_for_hermes(tmp_path, packet, scenario, {}, NOW + 1)
    assert result["status"] == "available" and result["included_request_ids"] == ["1" * 32]
    p = result["predictions"][0]
    assert p["answers"]["endpoint_15m"]["probabilities"] == {"UP": 1, "DOWN": 0, "FLAT": 0}
    assert "thesis_state" not in p["answers"]
    assert p["reference"]["recent_path_15m"] == {"points": 3, "direction": "UP"}
    assert result["effect"] == "advisory_only" and "uncalibrated" in result["calibration"]


@pytest.mark.parametrize("field,value", [
    ("returned_model", "jev-latest"), ("provider", "other"), ("question_hash", "old"),
    ("state_schema_version", "old"), ("source_utc", iso(NOW - 31)), ("end_utc", iso(NOW + 10)),
    ("position_key", "stale-position"), ("contract", "MNQ 09-26"), ("latency_ms", 2000),
    ("observation_id", "prior-epoch:1:abc"), ("state_hash", "corrupt")])
def test_ineligible_advisory_is_omitted_without_affecting_native_packet(tmp_path, field, value):
    row, _ = make_record(); row[field] = value
    _, packet, scenario = sink(tmp_path, row); before = copy.deepcopy(packet)
    result = ev.load_for_hermes(tmp_path, packet, scenario, {}, NOW + 1)
    assert result["status"] == "unavailable" and not result["included_request_ids"]
    assert packet == before


@pytest.mark.parametrize("failure", ["missing", "corrupt", "oversize", "stopped", "shadow", "old_health", "real_account"])
def test_failure_modes_fail_open(tmp_path, failure):
    root, packet, scenario = sink(tmp_path)
    path = root / "hermes-evidence.json"
    if failure == "missing": path.unlink()
    elif failure == "corrupt": path.write_text('{"broken":')
    elif failure == "oversize": path.write_bytes(b" " * (ev.MAX_FILE_BYTES + 1))
    elif failure == "stopped": (root / "STOP").touch()
    elif failure == "real_account": packet["frames"][0]["portfolio_snapshot"]["accounts"][0]["account_status"] = "Live"
    else:
        health = json.loads((root / "health.json").read_text())
        health.update({"mode": "SHADOW"} if failure == "shadow" else {"updated_utc": iso(NOW - 11)})
        (root / "health.json").write_bytes(encoded(health))
    assert ev.load_for_hermes(tmp_path, packet, scenario, {}, NOW + 1)["status"] == "unavailable"


def test_position_is_original_native_bound_and_private_identity_stays_local(tmp_path):
    trades = authored()
    trades["trades"][0]["entry_plans"][0]["reason"] += " Sim101 private-native-id private-order"
    trades["trades"][0]["entry_plans"][0]["geometry_context"] = {"OBJECTIVE_INVALIDATION": "Allowed pullback to 99; failure below 98."}
    position, key = ev.position_context(trades, "MNQ 12-26", "Sim101", NOW)
    assert position["status"] == "available"
    assert b"private" not in encoded(position) and b"Sim101" not in encoded(position)
    assert position["original_plans"][0]["geometry"]["OBJECTIVE_INVALIDATION"].startswith("Allowed pullback")
    row, state = make_record(position=position, key=key)
    _, packet, scenario = sink(tmp_path, row)
    result = ev.load_for_hermes(tmp_path, packet, scenario, trades, NOW + 1)
    assert "thesis_state" in result["predictions"][0]["answers"]
    trades["trades"][0]["working_orders"][0]["stop_price"] = 99
    assert ev.load_for_hermes(tmp_path, packet, scenario, trades, NOW + 1)["status"] == "unavailable"
    assert ev.position_context(authored(), "MNQ 09-26", "Sim101", NOW)[0]["status"] == "unavailable"
    assert ev.position_context(authored(), "MNQ 12-26", "Sim101", NOW + 76)[0]["status"] == "unavailable"


def test_state_preserves_numeric_neutral_band_and_does_not_invent_missing_flow():
    _, state = make_record()
    assert state["reference"]["neutral_bands_atr15"]["15"] == .5
    assert state["timeframes"]["1"]["values"]["OrderFlowVwap"] is None
    assert "RawScore" not in state["timeframes"]["1"]["values"]
    assert state["schema_version"] == ev.STATE_VERSION
    assert len(encoded({"state": state, "model": provider.MODEL, "questions": ev.QUESTIONS})) < provider.MAX_REQUEST_BYTES


def test_floating_point_tie_is_not_a_material_choice_repair():
    value = provider_value(); a = value["answers"]["endpoint_15m"]
    a.update(choice="UP", probabilities={"UP": .3, "DOWN": .30000000000000004, "FLAT": .4 - 1e-16})
    with pytest.raises(ValueError, match="named_choice_discrepancy"):
        provider.validate_response(value, ev.QUESTIONS)
    a.update(probabilities={"UP": .4, "DOWN": .4000000000000001, "FLAT": .1999999999999999})
    _, notes = provider.validate_response(value, ev.QUESTIONS)
    assert "endpoint_15m:floating_point_argmax_tie" in notes
    a["probabilities"] = {"UP": .39, "DOWN": .41, "FLAT": .2}
    with pytest.raises(ValueError, match="named_choice_discrepancy"):
        provider.validate_response(value, ev.QUESTIONS)


def test_bounded_rotation_uses_one_slot_and_preserves_legacy_shadow_cadence(tmp_path, monkeypatch):
    args = shadow.parse_args(["--mode", "EVIDENCE", "--cache", str(tmp_path / "cache.json"),
        "--output", str(tmp_path / "jev-shadow"), "--contracts", "MNQ 12-26", "MES 12-26", "M2K 12-26",
        "--account", "Sim101", "--duration-seconds", "60", "--max-usd", "4"])
    now = time.time(); cache = sample_cache(now)
    for name in ("MES 12-26", "M2K 12-26"): cache["Instruments"] += sample_cache(now, name)["Instruments"]
    args.cache.write_bytes(encoded(cache)); store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store, {"TYPESAFE_API_KEY": "unused"}); calls = []
    monkeypatch.setattr(observer.slot, "start", lambda *a: calls.append(a))
    observer.step(); observer.next_call = 0; observer.step(); observer.next_call = 0; observer.step()
    assert [a[3]["reference"]["instrument"] for a in calls] == args.contracts
    observer.next_call = 0; observer.step()
    assert len(calls) == 3 and store.calls == 3
    assert all(r["authority"] == "hermes_evidence_sim" and r["influenced"] is None
               for r in records(args.output) if r["kind"] == "request")
    store.close()


def test_hermes_prompt_receives_exact_advice_without_changing_native_packet():
    from test_direct_cycle_contracts import DIRECT, multibook_flat_scenario
    scenario = multibook_flat_scenario(); scenario["books"] = scenario["books"][:1]
    for book in scenario["books"]:
        book.update(followers=[], exposure=[], position_building_context={"instrument": "MNQ"})
    packet = {"packet_id": "cycle-9", "window_close_utc": iso(NOW), "policy": {}, "frames": [{
        "market_snapshot": {"instruments": [{"instrument": "MNQ"}], "coverage": []},
        "portfolio_snapshot": {"accounts": [{"account": "Sim101"}]}}]}
    evidence = {"status": "available", "predictions": [make_record()[0]], "included_request_ids": ["1" * 32]}
    before = copy.deepcopy(packet)
    prompt = DIRECT.build_prompt(packet, scenario, {"outcomes": []}, jev_evidence=evidence)
    envelope = json.loads(prompt.split("CURRENT_CYCLE=", 1)[1].split("\nOUTPUT_CLOSURE:", 1)[0])
    assert envelope["jev_evidence"] == evidence and packet == before
    assert "not independent votes to multiply or average" in prompt
    assert "endpoint direction is not original-target-before-stop probability" in prompt
    assert "No Jev threshold" in prompt and "Unavailable evidence is neutral" in prompt
    assert "jev_evidence" not in envelope["decision_packet"]


def test_provider_failure_clears_offered_advice_without_a_hermes_call(tmp_path, monkeypatch):
    args = shadow.parse_args(["--mode", "EVIDENCE", "--cache", str(tmp_path / "cache.json"),
        "--output", str(tmp_path / "jev-shadow"), "--contracts", "MNQ 12-26",
        "--account", "Sim101", "--duration-seconds", "60"])
    args.cache.write_bytes(encoded(sample_cache(time.time())))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store, {"TYPESAFE_API_KEY": "unused"})
    monkeypatch.setattr(observer.slot, "start", lambda *a: None)
    observer.step(); observer.offered["MNQ 12-26"] = {"old": "advice"}
    observer.prediction({"status": "transport_error", "request_id": "1" * 32,
                         "superseded": False, "expired": False})
    assert json.loads((args.output / "hermes-evidence.json").read_text())["predictions"] == {}
    assert records(args.output)[-1]["eligible_for_research_scoring"] is False
    store.close()


def test_observer_publication_is_consumable_with_exact_journal_identity(tmp_path, monkeypatch):
    args = shadow.parse_args(["--mode", "EVIDENCE", "--cache", str(tmp_path / "cache.json"),
        "--output", str(tmp_path / "jev-shadow"), "--contracts", "MNQ 12-26",
        "--account", "Sim101", "--duration-seconds", "60"])
    now = time.time()
    args.cache.write_bytes(encoded(sample_cache(now)))
    store = shadow.EvidenceStore(args.output, 4 * 1024 * 1024)
    observer = shadow.Observer(args, store, {"TYPESAFE_API_KEY": "unused"})
    calls = []
    monkeypatch.setattr(observer.slot, "start", lambda *a: calls.append(a))
    observer.step()
    request_id, observation_id, raw_hash, state, _, questions = calls[0]
    observer.prediction({"status": "ok", "request_id": request_id, "observation_id": observation_id,
        "observation_hash": raw_hash, "state_hash": digest(state), "start_utc": iso(now),
        "end_utc": iso(now), "latency_ms": 100, "superseded": False, "expired": False,
        "raw_response": json.dumps(provider_value())})
    observer.health()
    packet = {"frames": [{"market_snapshot": {"instruments": [{"instrument_full_name": "MNQ 12-26"}]},
        "portfolio_snapshot": {"accounts": [{"account": "Sim101", "account_status": "Sim"}]}}]}
    result = ev.load_for_hermes(tmp_path, packet, {"books": [{"master_account": "Sim101"}]}, {}, time.time())
    journal = records(args.output)
    assert questions == ev.QUESTIONS and result["status"] == "available"
    assert result["included_request_ids"] == [request_id]
    assert journal[-1]["kind"] == "prediction" and journal[-1]["request_id"] == request_id
    assert result["predictions"][0]["state_hash"] == journal[-1]["state_hash"]
    assert journal[-1]["influenced"] is None  # Consumption and final-choice attribution remain separate.
    store.close()
