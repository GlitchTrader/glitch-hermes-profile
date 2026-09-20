"""Causal label edge cases: no manufactured path ordering or future-time entry."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("jev_offline", Path(__file__).resolve().parents[1] / "research/jev/score_observations.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def anchor(**changes):
    return dict({"contract": "MES 12-26", "source_time": 0, "available_time": 0,
                 "price": 100, "atr15": 2, "tick": .25, "point_value": 5}, **changes)


def bar(i, low=99.5, high=100.5, close=100, **changes):
    return dict({"contract": "MES 12-26", "start": (i - 1) * 60, "time": i * 60,
                 "available_time": i * 60, "open": 100, "low": low, "high": high,
                 "close": close, "valid": True}, **changes)


def mark(time, price=100, **changes):
    return dict({"contract": "MES 12-26", "time": time, "available_time": time,
                 "price": price, "valid": True}, **changes)


def test_green_endpoint_can_have_adverse_barrier_first():
    bars = [bar(1, low=97), bar(2), bar(3), bar(4), bar(5, high=103, close=103)]
    result = mod.label_path(anchor(), mod.Timeline(bars=bars), 5, 300)
    assert result["label"] == "UP"
    assert result["first_excursion"] == "LOWER_FIRST"
    assert result["first_excursion_bar_close"] == 60
    assert result["observed_down_excursion_points"] == 3


def test_same_bar_crossing_is_unresolved():
    bars = [bar(1, low=97, high=103)] + [bar(i) for i in range(2, 6)]
    assert mod.label_path(anchor(), mod.Timeline(bars=bars), 5, 300)["first_excursion"] == "UNRESOLVED"


def test_sparse_marks_cannot_prove_neither_or_exact_excursion():
    result = mod.label_path(anchor(), mod.Timeline([mark(60, 101), mark(300, 100)]), 5, 300)
    assert result["first_excursion"] == "UNRESOLVED"
    assert result["excursion_quality"] == "sampled_lower_bounds"
    assert result["minute_path_efficiency"] is None


def test_missing_minute_censors_order_even_if_later_bar_hits():
    bars = [bar(1), bar(3, low=97), bar(4), bar(5)]
    result = mod.label_path(anchor(), mod.Timeline([mark(300)], bars), 5, 300)
    assert result["first_excursion"] == "UNRESOLVED"


def test_straddling_anchor_bar_cannot_supply_pre_anchor_high():
    bars = [bar(1, high=200)] + [bar(i) for i in range(2, 7)]
    result = mod.label_path(anchor(source_time=30, available_time=30), mod.Timeline([mark(330)], bars), 5, 330)
    assert result["excursion_quality"] == "sampled_lower_bounds"
    assert result["observed_up_excursion_points"] == .5


def test_contract_identity_never_joins_by_root():
    result = mod.label_path(anchor(), mod.Timeline([mark(300, contract="MES 09-26")]), 5, 320)
    assert result["status"] == "MISSING_ENDPOINT"


def test_future_publication_is_not_available():
    result = mod.label_path(anchor(), mod.Timeline([mark(300, available_time=400)]), 5, 320)
    assert result["status"] == "MISSING_ENDPOINT"


def test_pending_and_late_endpoint_do_not_interpolate():
    timeline = mod.Timeline([mark(316, 105)])
    assert mod.label_path(anchor(), timeline, 5, 299)["status"] == "PENDING"
    assert mod.label_path(anchor(), timeline, 5, 320)["status"] == "MISSING_ENDPOINT"


def test_allowed_endpoint_delay_is_explicit():
    result = mod.label_path(anchor(), mod.Timeline([mark(310, 101)]), 5, 320)
    assert result["endpoint_delay_seconds"] == 10
    assert result["endpoint_source"] == "first_available_mark_at_or_after_target"
    assert result["label"] == "FLAT"  # equality belongs to the neutral band


def test_conflicting_duplicate_is_excluded():
    timeline = mod.Timeline([mark(300, 101), mark(300, 102)])
    assert len(timeline.conflicts) == 1
    assert mod.label_path(anchor(), timeline, 5, 320)["status"] == "MISSING_ENDPOINT"


def test_bar_revision_prevents_complete_path():
    bars = [bar(i) for i in range(1, 6)] + [bar(2, high=102, available_time=200)]
    result = mod.label_path(anchor(), mod.Timeline([mark(300)], bars), 5, 320)
    assert result["excursion_quality"] == "sampled_lower_bounds"


def test_later_revision_cannot_change_an_earlier_asof_label():
    timeline = mod.Timeline([mark(300, 101), mark(300, 103, available_time=400)])
    assert mod.label_path(anchor(), timeline, 5, 320)["label"] == "FLAT"
    assert mod.label_path(anchor(), timeline, 5, 420)["status"] == "MISSING_ENDPOINT"


def test_probe_uses_post_inference_mark_and_charges_both_sides():
    timeline = mod.Timeline([mark(30, 99), mark(60, 100), mark(300, 103)])
    label = mod.label_path(anchor(), timeline, 5, 320)
    long = mod.economic_probe(anchor(), timeline, label, 45, 1)
    short = mod.economic_probe(anchor(), timeline, label, 45, -1)
    assert long["entry_source_time"] == 60
    assert long["cost_usd"] == pytest.approx(4.85)
    assert long["net_usd"] == pytest.approx(10.15)
    assert short["net_usd"] == pytest.approx(-19.85)
    assert mod.economic_probe(anchor(), timeline, label, 301, 1)["status"] == "NO_POST_INFERENCE_ENTRY_MARK"


def test_metrics_use_labels_not_dictionary_order():
    result = mod.probability_metrics([{"label": "UP", "probabilities": {"FLAT": .1, "DOWN": .2, "UP": .7}}])
    assert result["brier"] == pytest.approx(.14)
    assert result["accuracy"] == 1
    assert result["ece"] == pytest.approx(.3)


@pytest.mark.parametrize("change", [{"atr15": 0}, {"source_time": float("nan")}, {"available_time": -1}])
def test_invalid_anchor_rejected(change):
    with pytest.raises(ValueError):
        mod.label_path(anchor(**change), mod.Timeline(), 5, 300)
