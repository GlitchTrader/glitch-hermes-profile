"""Causality and boundary tests for market-perception v2."""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import market_structure as ms  # noqa: E402


ECONOMICS = {
    "MES": {"point_value_usd": 5.0, "tick_size": 0.25},
    "MNQ": {"point_value_usd": 2.0, "tick_size": 0.25},
    "M2K": {"point_value_usd": 5.0, "tick_size": 0.1},
}
BASE = {"MES": 7600.0, "MNQ": 29000.0, "M2K": 2900.0}
SCALE = {"MES": 0.7, "MNQ": 4.0, "M2K": 0.5}


def minute_id(index: int) -> str:
    stamp = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return stamp.strftime("%Y%m%dT%H%MZ")


def iso_minute(index: int) -> str:
    stamp = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return stamp.strftime("%Y-%m-%dT%H:%M:00Z")


def completed_values(root: str, index: int) -> tuple[float, float, float, float]:
    scale = SCALE[root]
    center = BASE[root] + scale * (0.12 * index + 2.4 * math.sin(index / 7))
    open_price = center - scale * math.sin(index / 3)
    close = center + scale * math.sin((index + 1) / 3)
    high = max(open_price, close) + scale * (0.8 + 0.2 * math.cos(index))
    low = min(open_price, close) - scale * (0.8 + 0.2 * math.sin(index))
    return open_price, high, low, close


def instrument(root: str, index: int, *, partial_offset: float = 0.0) -> dict:
    open_price, high, low, close = completed_values(root, index)
    tick = ECONOMICS[root]["tick_size"]
    partial_open = close + partial_offset
    partial_close = partial_open + tick
    vwap = BASE[root] + SCALE[root] * index * 0.08 if root != "M2K" else None
    delta = (index % 11 - 5) * 13 if root != "M2K" else None
    deviation = (partial_close - vwap) / max(SCALE[root] * 8, tick) if vwap is not None else None
    native = {
        "utc_time": iso_minute(index),
        "closed_utc": iso_minute(index + 1),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100 + index,
        "completeness": "complete",
        "source": "ninjatrader_bars_ago_1",
    }
    return {
        "instrument": root,
        "instrument_full_name": f"{root} 09-26",
        "current_price": partial_close,
        "instrument_economics": {**ECONOMICS[root], "source": "ninjatrader_master_instrument"},
        "session": {
            "name": "Asia",
            "high": BASE[root] + SCALE[root] * 16,
            "low": BASE[root] - SCALE[root] * 12,
            "previous_high": BASE[root] + SCALE[root] * 20,
            "previous_low": BASE[root] - SCALE[root] * 18,
        },
        "timeframe_bars": [{
            "minutes": 1,
            "utc_time": iso_minute(index + 1),
            "open": partial_open,
            "high": max(partial_open, partial_close) + tick,
            "low": min(partial_open, partial_close) - tick,
            "close": partial_close,
            "volume": 17 + index,
            "indicators": {
                "atr": SCALE[root] * 3,
                "adx": 22 + index % 8,
                "rsi": 45 + index % 20,
                "order_flow_cumulative_delta": delta * index if delta is not None else None,
                "order_flow_delta_change": delta,
                "order_flow_vwap": vwap,
                "order_flow_vwap_deviation": deviation,
                "order_flow_aggression_balance": 0.15 if delta is not None else None,
            },
            "derived_analytics": {
                "directional_score": math.sin(index / 8),
                "tradeability_score": 0.5,
                "order_flow_reliability": 0.7 if delta is not None else None,
            },
            "descriptive_state": {
                "native_observations": {"last_completed_bar": native},
                "descriptive_state": {
                    "flow": {"classification_coverage": 1.0 if delta is not None else None},
                    "quality": {
                        "partial_1m": True,
                        "order_flow_status": "available" if delta is not None else "unavailable",
                    },
                },
            },
        }],
    }


def frame(index: int, *, partial_offset: float = 0.0) -> dict:
    return {
        "schema_version": "glitch.hermes.minute_frame.v1",
        "minute_id": minute_id(index + 1),
        "captured_utc": iso_minute(index + 1),
        "market_snapshot": {
            "instruments": [instrument(root, index, partial_offset=partial_offset) for root in ("MNQ", "MES", "M2K")],
        },
    }


def packet(end_index: int, *, partial_offset: float = 0.0) -> dict:
    frames = [frame(index, partial_offset=partial_offset) for index in range(end_index - 4, end_index + 1)]
    return {"packet_id": frames[-1]["minute_id"], "frames": frames}


def seed_exchange(exchange: Path, count: int = 90) -> None:
    directory = exchange / "glitch" / "minute-frames"
    directory.mkdir(parents=True)
    for index in range(count):
        value = frame(index)
        (directory / f"{value['minute_id']}.json").write_text(
            json.dumps(value, separators=(",", ":")), encoding="utf-8"
        )


def test_completed_bar_is_native_and_live_partial_stays_separate() -> None:
    state = ms._empty_state()
    value = frame(20, partial_offset=500.0)
    ms.ingest_frame(state, value)

    mes = state["instruments"]["MES"]
    native_close = completed_values("MES", 20)[3]
    assert mes["bars"][-1]["c"] == pytest.approx(native_close)
    assert mes["latest_partial"]["c"] > native_close + 400
    assert mes["bars"][-1]["first_observed_frame_id"] == value["minute_id"]


def test_instrument_neutral_ingest_dedupes_and_uses_native_economics() -> None:
    state = ms._empty_state()
    for index in range(ms.MAX_BARS + 20):
        ms.ingest_frame(state, frame(index))
    ms.ingest_frame(state, frame(ms.MAX_BARS + 19))

    assert set(state["instruments"]) == {"MES", "MNQ", "M2K"}
    for root, economics in ECONOMICS.items():
        slot = state["instruments"][root]
        assert len(slot["bars"]) == ms.MAX_BARS
        assert len(slot["samples"]) == ms.MAX_SAMPLES
        assert slot["economics"]["tick_size"] == economics["tick_size"]
        assert slot["economics"]["point_value_usd"] == economics["point_value_usd"]


def test_exchange_backfill_never_reads_a_frame_after_packet_ceiling(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    seed_exchange(exchange, 75)
    admitted = packet(60)
    state = ms.update_state_from_exchange(ms._empty_state(), admitted, exchange)

    assert state["last_source_frame_id"] == admitted["packet_id"]
    assert all(
        slot["latest_frame_id"] <= admitted["packet_id"]
        for slot in state["instruments"].values()
    )


def test_corrupt_state_recovers_neutrally_and_round_trip_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    assert ms.load_state(path) == ms._empty_state()

    state = ms._empty_state()
    ms.ingest_frame(state, frame(1))
    ms.save_state(path, state)
    first = path.read_bytes()
    ms.save_state(path, ms.load_state(path))
    assert path.read_bytes() == first


def test_swings_are_causal_and_name_the_confirmation_bar() -> None:
    bars = []
    prices = [10, 11, 14, 12, 9, 10, 13]
    for index, price in enumerate(prices):
        bars.append({
            "id": f"b{index}", "o": price, "h": price + 1,
            "l": price - 1, "c": price, "v": 1,
        })
    swings = ms.confirmed_swings(bars, width=2)

    assert swings
    assert all("confirmed_after_bar_id" in swing for swing in swings)
    assert all(
        int(swing["confirmed_after_bar_id"][1:]) > int(swing["bar_id"][1:])
        for swing in swings
    )


def test_unfilled_imbalance_is_a_measurement_not_a_trade() -> None:
    bars = [
        {"id": "b0", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1},
        {"id": "b1", "o": 101, "h": 108, "l": 100, "c": 107, "v": 1},
        {"id": "b2", "o": 107, "h": 110, "l": 104, "c": 109, "v": 1},
    ]
    zones = ms.fvg_zones(bars, 109, tick=0.25, atr=3, point_value=5)

    assert zones[0]["kind"] == "up_imbalance"
    assert zones[0]["formed_bar_id"] == "b2"
    assert "action" not in zones[0]
    bars.append({"id": "b3", "o": 109, "h": 109, "l": 100, "c": 101, "v": 1})
    assert ms.fvg_zones(bars, 101, tick=0.25, atr=3, point_value=5) == []


def test_auction_reference_ladder_spans_near_and_far_causal_levels() -> None:
    ladder = ms._auction_reference_ladder(
        {
            "high": 110, "low": 90,
            "previous_high": 120, "previous_low": 80,
        },
        {"bars": 60, "high": 115, "low": 85, "mid": 100, "width_points": 30},
        {
            "current_bands": {
                "minus_2": 90, "minus_1": 95, "median": 100,
                "plus_1": 105, "plus_2": 110,
            },
        },
        current=100,
        tolerance=0.5,
    )

    assert [row[0] for row in ladder["above"]] == [105, 115, 120]
    assert [row[0] for row in ladder["below"]] == [95, 85, 80]
    assert all(row[1] > 0 for row in ladder["above"])
    assert all(row[1] < 0 for row in ladder["below"])
    assert "prior_session_high" in ladder["above"][-1][2]
    assert "prior_session_low" in ladder["below"][-1][2]


def test_market_map_is_bounded_neutral_and_missing_flow_stays_unknown(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    seed_exchange(exchange, 90)
    value, image_path = ms.build_market_perception(packet(89), exchange)

    assert value["instrument_order"] == ["MES", "MNQ", "M2K"]
    assert image_path is not None and image_path.is_file()
    assert len(json.dumps(value, separators=(",", ":"))) <= ms.MAX_SERIALIZED_CHARS
    by_root = {item["instrument"]: item for item in value["instruments"]}
    assert by_root["M2K"]["vwap_path"]["status"] == "unavailable"
    assert by_root["M2K"]["order_flow_response"]["status"] == "unavailable"
    assert "vwap" in by_root["M2K"]["evidence_quality"]["missing"]
    assert by_root["MES"]["evidence_quality"]["status"] == "ready"
    assert value["auction_reference_ladder_contract"]["row_format"] == [
        "price", "signed_distance_points", "sources",
    ]
    for perception in by_root.values():
        ladder = perception["auction_reference_ladder"]
        assert 1 <= len(ladder["above"]) <= ms.MAX_AUCTION_REFERENCES_PER_SIDE
        assert 1 <= len(ladder["below"]) <= ms.MAX_AUCTION_REFERENCES_PER_SIDE
        assert all(row[1] > 0 for row in ladder["above"])
        assert all(row[1] < 0 for row in ladder["below"])
        for level in perception["nearest_measured_levels"]:
            assert "absolute_distance_ticks" in level
            assert "absolute_distance_atr" in level
            assert "absolute_distance_one_contract_usd" in level
            assert "touch_episodes" in level
            assert "responses_above" in level
            assert "responses_below" in level
            assert "last_touch_age_bars" in level

    forbidden_keys = {
        "recommended_action", "trade_action", "probability", "permission",
        "veto", "candidate_bracket", "quantity", "setup_score", "rank",
    }

    def keys(node):
        if isinstance(node, dict):
            for key, child in node.items():
                yield key
                yield from keys(child)
        elif isinstance(node, list):
            for child in node:
                yield from keys(child)

    assert forbidden_keys.isdisjoint(set(keys(value)))


def test_measured_levels_keep_both_sides_and_missing_economics_stays_unknown() -> None:
    state = ms._empty_state()
    for index in range(80):
        ms.ingest_frame(state, frame(index))
    slot = state["instruments"]["MES"]
    slot.pop("economics", None)

    perception = ms.instrument_perception("MES", slot)

    relations = {level["relative_to_current"] for level in perception["nearest_measured_levels"]}
    assert "above" in relations
    assert "below" in relations
    assert "native_economics" in perception["evidence_quality"]["missing"]
    assert perception["measurement_tolerance"]["ticks"] is None
    assert all(
        level["absolute_distance_ticks"] is None
        and level["absolute_distance_one_contract_usd"] is None
        for level in perception["nearest_measured_levels"]
    )


def test_geometry_converts_each_instrument_with_its_own_contract_math(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    seed_exchange(exchange, 80)
    value, _ = ms.build_market_perception(packet(79), exchange)
    by_root = {item["instrument"]: item for item in value["instruments"]}

    for root, perception in by_root.items():
        level = perception["nearest_measured_levels"][0]
        points = abs(level["signed_distance_points"])
        assert level["absolute_distance_one_contract_usd"] == pytest.approx(
            points * ECONOMICS[root]["point_value_usd"]
        )
        assert level["absolute_distance_ticks"] == pytest.approx(
            points / ECONOMICS[root]["tick_size"], abs=1e-4
        )


def test_map_and_png_are_byte_deterministic_for_identical_input(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    seed_exchange(exchange, 75)
    admitted = packet(74)
    first_map, first_path = ms.build_market_perception(admitted, exchange)
    first_bytes = first_path.read_bytes()
    second_map, second_path = ms.build_market_perception(admitted, exchange)

    assert second_map == first_map
    assert second_path == first_path
    assert second_path.read_bytes() == first_bytes


def test_position_view_renders_only_the_active_instrument(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    seed_exchange(exchange, 75)
    trade_state = {
        "trades": [{
            "instrument": "MES", "side": "long", "quantity": 1,
            "average_price": 7610.0, "peak_unrealized_pnl_usd": 25.0,
            "deterministic_management_math": {
                "point_value_usd": 5.0, "current_price": 7612.0,
                "stop_legs": [{"price": 7605.0}], "target_legs": [{"price": 7625.0}],
            },
        }],
    }
    value, path = ms.build_market_perception(
        packet(74), exchange, active_trade_state=trade_state, positioned_roots=["MES"]
    )

    assert value["view"] == "position_management"
    assert value["instrument_order"] == ["MES"]
    assert value["visual_context"]["panels"] == ["MES"]
    assert path is not None and path.is_file()


def test_image_retention_is_bounded(tmp_path: Path) -> None:
    exchange = tmp_path / "exchange"
    seed_exchange(exchange, 75)
    image_dir = exchange / "hermes" / "supervisor" / "market-context-images"
    image_dir.mkdir(parents=True)
    for index in range(ms.MAX_IMAGE_FILES + 5):
        (image_dir / f"20000101T{index:04d}Z-portfolio_scan.png").write_bytes(b"old")

    ms.build_market_perception(packet(74), exchange)

    assert len(list(image_dir.glob("*.png"))) <= ms.MAX_IMAGE_FILES
