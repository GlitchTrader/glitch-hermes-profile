"""Causal cache/producer and typed-provider contracts; no live data or network."""
import copy
import json
from datetime import datetime, timezone
import urllib.error

import pytest

import jev_observation as obs
import jev_provider as provider

NOW = datetime(2026, 9, 19, 13, tzinfo=timezone.utc).timestamp()


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def sample_cache(now=NOW, contract="MNQ 12-26", publisher="glitch_analytics_bridge"):
    root = contract.split()[0]
    readings = []
    for minutes in (1, 5, 15, 60):
        desc = {
            "schema_version": "glitch.market.descriptive.v1",
            "native_observations": {
                "instrument_full_name": contract, "instrument_root": root,
                "bar": {"utc_time": iso(now), "minutes": minutes},
                "last_completed_bar": {"utc_time": iso(now - 60), "closed_utc": iso(now),
                                       "open": 100, "high": 102, "low": 99, "close": 101, "volume": 123},
                "instrument_economics": {"tick_size": .25, "point_value_usd": 2}},
            "descriptive_state": {
                "quality": {"as_of_utc": iso(now), "bar_completeness": "in_progress"},
                "flow": {"delta_velocity": 0}, "liquidity": {"last_quote_age_seconds": 45}},
            "heuristic_projections": {"source": "glitch_analytics_bridge_legacy"
                                      if publisher == "glitch_analytics_bridge" else "glitch_ai_market_ingest"},
        }
        readings.append({"InstrumentFullName": contract, "InstrumentRoot": root, "Minutes": minutes,
                         "Publisher": publisher, "UtcTime": iso(now), "CurrentPrice": 101,
                         "Open": 100, "High": 102, "Low": 99, "Volume": 123, "Atr": 2,
                         "InstrumentTickSize": .25, "InstrumentPointValueUsd": 2,
                         "Cci": 0, "Rsi": 51, "DescriptiveStateJson": json.dumps(desc)})
    return {"Instruments": [{"InstrumentFullName": contract, "InstrumentRoot": root, "Readings": readings}]}


def decode(cache, now=NOW):
    return obs.decode_cache(obs.encoded(cache), now)


def change_desc(cache, edit, index=0):
    reading = cache["Instruments"][0]["Readings"][index]
    desc = json.loads(reading["DescriptiveStateJson"])
    edit(desc)
    reading["DescriptiveStateJson"] = json.dumps(desc)


def response():
    return {"model": provider.MODEL, "usage": {"input_tokens": 100}, "answers": {
        key: {"type": "choice", "choice": next(iter(q["criteria"])), "confidence": 1,
              "probabilities": {option: int(i == 0) for i, option in enumerate(q["criteria"])}}
        for key, q in provider.QUESTIONS.items()}}


def test_fresh_partial_state_has_exact_relations_and_explicit_missingness():
    instruments = decode(sample_cache())
    assert instruments["MNQ 12-26"]["eligible"]
    state = obs.build_state(instruments, "MNQ 12-26", "obs-1", "hash")
    assert state["reference"]["neutral_bands_atr15"]["60"] == .5
    assert state["timeframes"]["1"]["completeness"] == "in_progress"
    assert state["timeframes"]["1"]["values"]["OrderFlowVwap"] is None
    assert state["timeframes"]["1"]["descriptive"]["flow.delta_velocity"] == 0
    assert state["timeframes"]["1"]["descriptive"]["liquidity.last_quote_age_seconds"] == 45


def test_different_contracts_same_root_do_not_merge():
    cache = sample_cache()
    cache["Instruments"] += sample_cache(contract="MNQ 03-27")["Instruments"]
    assert set(decode(cache)) == {"MNQ 12-26", "MNQ 03-27"}
    cache["Instruments"].append(copy.deepcopy(cache["Instruments"][0]))
    with pytest.raises(ValueError, match="contract_identity"):
        decode(cache)


@pytest.mark.parametrize("mutate,issue", [
    (lambda c: c["Instruments"][0]["Readings"][0].update(InstrumentFullName="MES 12-26"), "mixed_contract"),
    (lambda c: change_desc(c, lambda d: d["native_observations"].update(instrument_full_name="MNQ 09-26")), "descriptive_identity"),
    (lambda c: c["Instruments"][0]["Readings"][0].update(Publisher=None), "publisher_unreported_1"),
    (lambda c: change_desc(c, lambda d: d["native_observations"]["instrument_economics"].update(tick_size=1)), "economics_mismatch"),
    (lambda c: change_desc(c, lambda d: d["descriptive_state"]["quality"].update(as_of_utc=iso(NOW - 30))), "stale_descriptive"),
    (lambda c: change_desc(c, lambda d: d["native_observations"]["bar"].update(utc_time=iso(NOW - 3600))), "stale_native_bar"),
    (lambda c: c["Instruments"][0]["Readings"][0].update(UtcTime=iso(NOW + 10)), "stale_primary"),
])
def test_ineligible_evidence_is_preserved_without_inference(mutate, issue):
    cache = sample_cache()
    mutate(cache)
    data = decode(cache)
    assert issue in data["MNQ 12-26"]["issues"]
    with pytest.raises(ValueError, match="ineligible_primary"):
        obs.build_state(data, "MNQ 12-26", "id", "hash")


def test_ingest_masks_unproduced_zero_fields_and_uses_native_boundary():
    cache = sample_cache(publisher="glitch_ai_market_ingest")
    data = decode(cache)["MNQ 12-26"]
    assert data["eligible"]
    assert data["frames"]["1"]["values"]["Cci"] is None
    assert data["frames"]["1"]["values"]["Rsi"] == 51
    change_desc(cache, lambda d: d["native_observations"]["last_completed_bar"].update(closed_utc=iso(NOW - 3600)))
    assert "stale_native_bar" in decode(cache)["MNQ 12-26"]["issues"]


def test_native_interval_end_is_not_a_future_observation():
    cache = sample_cache()
    change_desc(cache, lambda d: d["native_observations"]["bar"].update(utc_time=iso(NOW + 59)))
    assert decode(cache)["MNQ 12-26"]["eligible"]


def test_state_is_allowlisted_and_history_cannot_see_future_or_other_contract():
    cache = sample_cache()
    cache["Instruments"][0]["account"] = "secret-account"
    cache["Instruments"][0]["Readings"][0]["TrendHint"] = "secret-key"
    history = [{"contract": c, "source_utc": iso(t), "price": 99}
               for c, t in (("MNQ 12-26", NOW - 1), ("MNQ 12-26", NOW + 1), ("MES 12-26", NOW))]
    state = obs.build_state(decode(cache), "MNQ 12-26", "id", "hash", history)
    assert len(state["history"]) == 1
    assert b"secret" not in obs.encoded(state)
    assert not decode(cache, NOW + 16)["MNQ 12-26"]["eligible"]


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b"[" * 25 + b"]" * 25,
                                 b" " * (obs.MAX_BYTES + 1), b'{"incomplete":'],
                         ids=["duplicate", "nan", "depth", "size", "torn"])
def test_json_resource_and_ambiguity_bounds(raw):
    with pytest.raises(ValueError):
        obs.strict_json(raw)


def test_dotnet_time_and_timezone_requirement():
    assert obs.timestamp("/Date(1000)/") == 1
    assert obs.timestamp("2026-09-19T12:00:00") is None


def test_typed_probabilities_retain_quantization_without_repairing_choice():
    value = response()
    answer = value["answers"]["endpoint_5m"]
    answer["probabilities"] = {"UP": .34, "DOWN": .33, "FLAT": .34}
    normalized, notes = provider.validate_response(value)
    assert sum(normalized["endpoint_5m"].values()) == pytest.approx(1)
    assert notes == ["endpoint_5m:rounded_probability_sum"]
    assert answer["probabilities"]["UP"] == .34
    answer["choice"] = "DOWN"
    with pytest.raises(ValueError, match="named_choice_discrepancy"):
        provider.validate_response(value)


@pytest.mark.parametrize("edit", [
    lambda v: v.update(model="jev-latest"),
    lambda v: v["answers"]["endpoint_5m"].update(type="noul"),
    lambda v: v["answers"]["endpoint_5m"].update(confidence=float("nan")),
    lambda v: v["answers"]["endpoint_5m"]["probabilities"].update(UP=1.2),
    lambda v: v["answers"].pop("path_state"),
])
def test_malformed_and_unknown_model_rejected(edit):
    value = response()
    edit(value)
    with pytest.raises(ValueError):
        provider.validate_response(value)


def test_transport_and_secrets(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TYPESAFE_API_KEY=direct-test-secret\nOPENROUTER_API_KEY=router-test-secret\n")
    keys = provider.credentials(env_file)
    value = response()
    value["echo"] = keys["OPENROUTER_API_KEY"]
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return obs.encoded(value)
    class FakeOpener:
        def open(self, req, timeout):
            assert req.full_url == provider.ENDPOINT and timeout == 2
            assert req.headers["Authorization"] == "Bearer direct-test-secret"
            assert b"secret" not in req.data
            return FakeResponse()
    monkeypatch.setattr(provider.urllib.request, "build_opener", lambda *args: FakeOpener())
    result = provider.request({"market": 1}, keys)
    assert result["status"] == "ok"
    assert "router-test-secret" not in result["raw_response"]
    assert result["estimated_cost_usd"] == pytest.approx(.0000042)


def test_http_failure_retains_only_status_and_redirects_are_rejected(monkeypatch):
    class Failure:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError(provider.ENDPOINT, 429, "key-in-error", {}, None)
    monkeypatch.setattr(provider.urllib.request, "build_opener", lambda *args: Failure())
    assert provider.request({}, {"TYPESAFE_API_KEY": "key"}) == {"status": "http_error", "http_status": 429}
    assert provider.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com") is None
