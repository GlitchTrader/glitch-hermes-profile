"""End-to-end joins from synthetic native bytes to offline probability scores."""
import base64
import copy
import json
import sys
from pathlib import Path

import pytest
import jev_observation as obs
from test_jev_observation import NOW, iso, sample_cache

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/jev"))
import score_recorder as scorer


def fixture_rows():
    observations = []
    for minute in range(7):
        now = NOW + minute * 60
        raw = obs.encoded(sample_cache(now))
        observations.append({"kind": "observation", "recorded_utc": iso(now), "read_end_utc": iso(now),
                             "observation_id": str(minute), "raw_hash": obs.digest(raw),
                             "raw_cache_base64": base64.b64encode(raw).decode(), "influenced": False})
    first = observations[0]
    state = obs.build_state(obs.decode_cache(obs.encoded(sample_cache()), NOW), "MNQ 12-26", "0", first["raw_hash"])
    request = {"kind": "request", "recorded_utc": iso(NOW), "request_id": "r1", "observation_id": "0",
               "observation_hash": first["raw_hash"], "state": state, "state_hash": obs.digest(state),
               "provider": "typesafe-direct", "question_hash": "frozen", "influenced": False}
    prediction = {"kind": "prediction", "recorded_utc": iso(NOW + 1), "end_utc": iso(NOW + 1),
                  "request_id": "r1", "observation_id": "0", "observation_hash": first["raw_hash"],
                  "state_hash": obs.digest(state), "question_hash": "frozen", "provider": "typesafe-direct",
                  "requested_model": "jev-1.13.0", "returned_model": "jev-1.13.0", "influenced": False,
                  "status": "ok", "expired": False, "superseded": False, "input_stale_or_invalid": False,
                  "eligible_for_research_scoring": True,
                  "probabilities_for_scoring": {f"endpoint_{h}m": {"UP": .1, "DOWN": .1, "FLAT": .8} for h in scorer.HORIZONS}}
    return [first, request, prediction, *observations[1:]]


def write_evidence(root, rows):
    (root / "observer.json").write_text(json.dumps({"owner": "glitch.jev.shadow.v1"}))
    (root / "evidence-fixture.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_complete_join_scores_one_ready_horizon_and_keeps_others_pending(tmp_path):
    write_evidence(tmp_path, fixture_rows())
    report, outcomes = scorer.evaluate(tmp_path, NOW + 361)
    assert report["outcome_status"] == {"OK": 1, "PENDING": 3}
    assert len(report["metrics_by_frozen_epoch"]) == 2  # all and exact endpoints
    assert outcomes[0]["label"]["first_excursion"] == "LOWER_FIRST"
    assert outcomes[0]["label"]["label"] == "FLAT"
    assert outcomes[0]["economic_probes"]["1"]["entry_source_time"] == NOW + 60


def test_advisory_epoch_keeps_inclusion_unknown_and_only_scores_asked_horizons(tmp_path):
    rows = fixture_rows()
    for row in rows[1:3]:
        row.update(authority="hermes_evidence_sim", influenced=None, question_hash="advisory-frozen")
    rows[1]["state"]["input_epoch"] = "live-hybrid-advisory-v1"
    rows[1]["state_hash"] = obs.digest(rows[1]["state"])
    rows[2]["state_hash"] = rows[1]["state_hash"]
    rows[2]["probabilities_for_scoring"].pop("endpoint_5m")
    write_evidence(tmp_path, rows)
    report, outcomes = scorer.evaluate(tmp_path, NOW + 361)
    assert report["outcome_status"] == {"PENDING": 3}
    assert all(x["influenced"] is None and x["authority"] == "hermes_evidence_sim" for x in outcomes)
    assert all(x["input_epoch"] == "live-hybrid-advisory-v1" for x in outcomes)


def test_next_bar_timestamp_does_not_shift_completed_ohlc_forward(tmp_path):
    write_evidence(tmp_path, fixture_rows())
    _, _, _, timeline, _, _, _ = scorer.collect(tmp_path, NOW + 301)
    assert max(b["time"] for b in timeline.bars["MNQ 12-26"]) == NOW + 240
    _, outcomes = scorer.evaluate(tmp_path, NOW + 301)
    assert outcomes[0]["label"]["excursion_quality"] == "sampled_lower_bounds"
    assert outcomes[0]["label"]["first_excursion"] == "UNRESOLVED"


@pytest.mark.parametrize("field,value", [("returned_model", "jev-latest"), ("state_hash", "wrong"),
                                        ("observation_id", "wrong"), ("provider", "other")])
def test_identity_mismatch_cannot_contribute_metrics(tmp_path, field, value):
    rows = fixture_rows();rows[2][field] = value
    write_evidence(tmp_path, rows)
    report, outcomes = scorer.evaluate(tmp_path, NOW + 301)
    assert not outcomes
    assert report["excluded_predictions"] == {"identity_mismatch": 1}


def test_raw_bytes_must_match_hash(tmp_path):
    rows = fixture_rows();rows[0]["raw_hash"] = "wrong"
    write_evidence(tmp_path, rows)
    with pytest.raises(ValueError, match="observation_hash"):
        scorer.evaluate(tmp_path, NOW + 301)


@pytest.mark.parametrize("field,value", [("expired", True), ("superseded", True),
                                        ("status", "malformed_response"), ("input_stale_or_invalid", True)])
def test_unusable_result_is_excluded_even_if_eligibility_flag_is_wrong(tmp_path, field, value):
    rows = fixture_rows();rows[2][field] = value
    write_evidence(tmp_path, rows)
    report, outcomes = scorer.evaluate(tmp_path, NOW + 301)
    assert not outcomes
    assert report["excluded_predictions"] == {"missing_request_or_ineligible_prediction": 1}


def test_duplicate_prediction_cannot_double_sample(tmp_path):
    rows = fixture_rows();rows.append(copy.deepcopy(rows[2]))
    write_evidence(tmp_path, rows)
    with pytest.raises(ValueError, match="duplicate_prediction_identity"):
        scorer.evaluate(tmp_path, NOW + 301)


def test_regressed_native_source_cannot_be_used_as_future_mark(tmp_path):
    rows = fixture_rows()
    # A newly published cache regresses source time by five seconds, still within the freshness limit.
    raw = obs.encoded(sample_cache(NOW + 55))
    rows.insert(4, {"kind": "observation", "recorded_utc": iso(NOW + 61), "read_end_utc": iso(NOW + 61),
                    "observation_id": "regression", "raw_hash": obs.digest(raw),
                    "raw_cache_base64": base64.b64encode(raw).decode(), "influenced": False})
    write_evidence(tmp_path, rows)
    observations, _, _, timeline, _, issues, _ = scorer.collect(tmp_path, NOW + 301)
    assert issues["source_time_regression"] == 1
    assert not observations["regression"]["instruments"]["MNQ 12-26"]["eligible"]
    assert all(m["time"] != NOW + 55 for m in timeline.marks["MNQ 12-26"])
