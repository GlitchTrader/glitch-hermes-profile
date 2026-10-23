"""Delivery-survivable entry range + calibration priors (no model/native calls)."""
from __future__ import annotations

import pytest

from test_direct_cycle_contracts import DIRECT


def _mnq_scenario(price: float = 29180.0) -> dict:
    return {
        "market": {
            "candidates": [{
                "instrument": "MNQ",
                "current_price": price,
                "instrument_economics": {
                    "point_value_usd": 2.0,
                    "tick_size": 0.25,
                    "source": "test",
                },
            }],
        },
    }


def test_narrow_quote_band_expands_inside_stop_target():
    low, high, audit = DIRECT.delivery_survivable_entry_range(
        action="ENTER_LONG",
        low=29180.0,
        high=29180.5,  # 2 ticks — historically doomed
        stop=29170.0,
        target=29200.0,
        reference=29180.25,
        tick=0.25,
    )
    assert audit["status"] == "expanded"
    assert audit["authored_high"] - audit["authored_low"] == pytest.approx(0.5)
    assert (high - low) >= DIRECT.ENTRY_RANGE_MIN_TICKS * 0.25 - 1e-9
    assert low <= 29180.25 <= high
    assert 29170.0 + 0.25 <= low < high <= 29200.0 - 0.25


def test_already_wide_range_unchanged():
    low, high, audit = DIRECT.delivery_survivable_entry_range(
        action="ENTER_SHORT",
        low=100.0,
        high=106.0,
        stop=110.0,
        target=90.0,
        reference=103.0,
        tick=0.25,
    )
    assert audit["status"] == "unchanged"
    assert (low, high) == (100.0, 106.0)


def test_apply_mutates_batch_and_keeps_wire_clean():
    batch = {
        "decisions": [{
            "action": "ENTER_LONG",
            "instrument": "MNQ",
            "entry_range_low": 29180.0,
            "entry_range_high": 29180.5,
            "stop_loss": 29170.0,
            "take_profit_1": 29200.0,
        }],
    }
    DIRECT.apply_delivery_survivable_entry_ranges(batch, _mnq_scenario(29180.25))
    intent = batch["decisions"][0]
    assert intent["entry_range_delivery_adjustment"]["status"] == "expanded"
    assert intent["entry_range_high"] - intent["entry_range_low"] >= 2.0 - 1e-9
    assert "entry_range_delivery_adjustment" in DIRECT.ALLOWED_DECISION_FIELDS


def test_calibration_priors_wired_into_revision_and_instructions():
    import inspect

    assert DIRECT.DIRECT_PROMPT_REVISION == "direct-v31-rr-baseline"
    assert "risk_points" in DIRECT.CALIBRATION_PRIORS_V1["baseline"]
    source = inspect.getsource(DIRECT.build_prompt)
    assert "Probability baseline" in source
    assert "CALIBRATION_PRIORS_V1" in source


def test_nothing_requires_numeric_selection_geometry():
    with pytest.raises(ValueError, match="selection_ev_nothing_geometry_required"):
        DIRECT.validate_selection_ev(
            "direction=LONG;entry=100 current;stop=not authored;target=not authored;"
            "risk_points=UNKNOWN;reward_points=UNKNOWN;friction_points=0.25;"
            "breakeven_target_first=UNKNOWN;estimated_target_first_range=0.40-0.50;"
            "now_ev=UNCERTAIN;wait_price=99;wait_ev=IMPROVED;decisive_reason=no bracket",
            "NOTHING",
            0,
            "candidate_comparison",
        )
