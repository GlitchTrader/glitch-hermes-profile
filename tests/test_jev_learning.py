"""Leakage and candidate lifecycle contracts for source-only feature research."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/jev"))
import learning


def row(utc, root="MES"):
    return {"observation_id": utc+root, "utc": utc, "day": utc[:10], "root": root,
            "split": "train", "state": {"price": 1}}


def test_label_window_and_purge_apply_to_all_instruments():
    rows = [row("2024-04-01T00:00:00Z", "MES"), row("2024-03-31T23:00:00Z", "MNQ"),
            row("2024-03-31T22:59:00Z", "M2K"), row("2024-04-02T00:00:00Z"),
            row("2024-06-30T23:00:00Z")]
    fit, score = learning.partition(rows, "2024-04-02", "2024-07-01")
    assert fit == [2]  # strict boundary; label must finish before purge begins
    assert score == [3]  # last label overlaps the score fold's exclusive end


@pytest.mark.parametrize("utc", ["2025-02-01T00:00:00Z", "2026-02-01T00:00:00Z"])
def test_confirmation_or_opened_test_cannot_enter_feedback(utc):
    with pytest.raises(ValueError, match="outside_development"):
        learning.feedback([row(utc)], [], [])


def test_duplicate_and_foreign_feedback_rows_are_rejected():
    r = row("2024-02-01T00:00:00Z")
    with pytest.raises(ValueError, match="duplicate"):
        learning.validate_development([r, copy.deepcopy(r)])
    with pytest.raises(ValueError, match="foreign"):
        learning.feedback([r], [{"observation_id": "other"}], [])


def test_retention_requires_size_consistency_and_no_horizon_damage():
    before = {f"{f}:{h}": .7 for f in range(3) for h in learning.HORIZONS}
    after = {k: v-.003 for k, v in before.items()}
    assert learning.accept_change(before, after)["accepted"]
    assert not learning.accept_change(before, {k: v-.001 for k, v in before.items()})["accepted"]
    one_fold = {k: v-.03 if k.startswith("0:") else v+.001 for k,v in before.items()}
    assert not learning.accept_change(before, one_fold)["accepted"]
    damaged = {k: v+.004 if k.endswith(":60") else v-.01 for k,v in before.items()}
    assert not learning.accept_change(before, damaged)["accepted"]
    with pytest.raises(ValueError, match="unmatched"):
        learning.accept_change(before, {"0:15": .6})


def test_independent_noul_values_do_not_form_a_choice_distribution():
    record = {"status": "ok", "returned_model": "jev-1.13.0", "response": {"answers": {
        "a": {"type": "noul", "noul": .9}, "b": {"type": "noul", "noul": .8}}}}
    assert learning.probability(record, "a") == .9
    assert learning.probability(record, "b") == .8
    record["returned_model"] = "jev-latest"
    assert learning.probability(record, "a") is None


@pytest.mark.parametrize("value", [True, -1, 1.01, float("nan"), "0.9"])
def test_invalid_noul_never_becomes_a_feature(value):
    record = {"status": "ok", "returned_model": "jev-1.13.0", "response": {"answers": {"a": {"type": "noul", "noul": value}}}}
    assert learning.probability(record, "a") is None
