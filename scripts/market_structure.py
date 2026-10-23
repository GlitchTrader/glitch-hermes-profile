"""Causal, instrument-neutral market perception for the direct Glitch cycle.

This module turns already-admitted native minute frames into a compact temporal
and spatial map plus one standardized chart. It never chooses an instrument,
direction, setup, probability, bracket, action, or quantity. Hermes remains
the sole trading decision-maker and the native packet remains authoritative.

Only facts observable at or before the admitted packet are used. Completed
bars come exclusively from NinjaTrader's ``last_completed_bar`` observation;
the live one-minute bar is stored and rendered separately as partial evidence.
Failures are expected to be handled fail-open by the caller.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "glitch.hermes.market_perception.v2"
STATE_SCHEMA_VERSION = "glitch.hermes.market_perception_state.v3"
MAX_BARS = 420
MAX_SAMPLES = 420
MAX_BACKFILL_FRAMES = 180
MAX_LEVELS = 8
MAX_AUCTION_REFERENCES_PER_SIDE = 3
MAX_IMAGE_FILES = 48
MAX_SERIALIZED_CHARS = 11_250
ROOT_ORDER = ("MES", "MNQ", "M2K")


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "last_source_frame_id": None,
        "instruments": {},
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: Any, digits: int = 8) -> float | None:
    number = _finite(value)
    return round(number, digits) if number is not None else None


def _root(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return text.split()[0].split("-")[0]


def _timeframe(instrument: dict[str, Any], minutes: int) -> dict[str, Any] | None:
    for row in instrument.get("timeframe_bars", []):
        if isinstance(row, dict) and row.get("minutes") == minutes:
            return row
    return None


def _nested(row: Any, *keys: str) -> Any:
    value = row
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _native_completed_bar(row: dict[str, Any]) -> dict[str, Any] | None:
    candidates = (
        _nested(row, "descriptive_state", "native_observations", "last_completed_bar"),
        _nested(row, "native_observations", "last_completed_bar"),
    )
    return next((value for value in candidates if isinstance(value, dict)), None)


def _descriptive_state(row: dict[str, Any]) -> dict[str, Any]:
    wrapped = row.get("descriptive_state")
    if not isinstance(wrapped, dict):
        return {}
    nested = wrapped.get("descriptive_state")
    return nested if isinstance(nested, dict) else wrapped


def load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _empty_state()
    if not isinstance(value, dict) or value.get("schema_version") != STATE_SCHEMA_VERSION:
        return _empty_state()
    if not isinstance(value.get("instruments"), dict):
        return _empty_state()
    return value


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, separators=(",", ":"), sort_keys=True)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _valid_ohlcv(source: dict[str, Any]) -> dict[str, float] | None:
    values = {key: _finite(source.get(name)) for key, name in (
        ("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume")
    )}
    if any(values[key] is None for key in ("o", "h", "l", "c")):
        return None
    if values["h"] < max(values["o"], values["c"]) or values["l"] > min(values["o"], values["c"]):
        return None
    if values["h"] < values["l"]:
        return None
    values["v"] = max(0.0, values["v"] or 0.0)
    return values  # type: ignore[return-value]


def _sample_from_instrument(
    frame: dict[str, Any], instrument: dict[str, Any], row_1m: dict[str, Any]
) -> dict[str, Any] | None:
    frame_id = str(frame.get("minute_id") or "")
    partial = _valid_ohlcv(row_1m)
    if not frame_id or partial is None:
        return None
    indicators = row_1m.get("indicators") if isinstance(row_1m.get("indicators"), dict) else {}
    analytics = row_1m.get("derived_analytics") if isinstance(row_1m.get("derived_analytics"), dict) else {}
    descriptive = _descriptive_state(row_1m)
    flow = descriptive.get("flow") if isinstance(descriptive.get("flow"), dict) else {}
    quality = descriptive.get("quality") if isinstance(descriptive.get("quality"), dict) else {}
    return {
        "frame_id": frame_id,
        "observed_utc": frame.get("captured_utc"),
        "current_price": _round(instrument.get("current_price") or partial["c"]),
        "partial": {key: _round(value) for key, value in partial.items()},
        "atr": _round(indicators.get("atr")),
        "adx": _round(indicators.get("adx")),
        "rsi": _round(indicators.get("rsi")),
        "vwap": _round(indicators.get("order_flow_vwap")),
        "vwap_deviation": _round(indicators.get("order_flow_vwap_deviation")),
        "cumulative_delta": _round(indicators.get("order_flow_cumulative_delta")),
        "delta_change": _round(indicators.get("order_flow_delta_change")),
        "aggression_balance": _round(indicators.get("order_flow_aggression_balance")),
        "directional_score": _round(analytics.get("directional_score")),
        "tradeability_score": _round(analytics.get("tradeability_score")),
        "order_flow_reliability": _round(analytics.get("order_flow_reliability")),
        "classification_coverage": _round(flow.get("classification_coverage")),
        "order_flow_status": quality.get("order_flow_status"),
    }


def _bar_from_instrument(frame: dict[str, Any], row_1m: dict[str, Any]) -> dict[str, Any] | None:
    native = _native_completed_bar(row_1m)
    if native is None or str(native.get("completeness") or "complete").lower() != "complete":
        return None
    values = _valid_ohlcv(native)
    frame_id = str(frame.get("minute_id") or "")
    native_time = str(native.get("utc_time") or "")
    if not frame_id or values is None:
        return None
    identity = native_time or (
        frame_id + ":" + ":".join(str(_round(values[key])) for key in ("o", "h", "l", "c"))
    )
    return {
        "id": identity,
        "native_utc": native_time or None,
        "native_closed_utc": native.get("closed_utc"),
        "first_observed_frame_id": frame_id,
        "first_observed_utc": frame.get("captured_utc"),
        **{key: _round(value) for key, value in values.items()},
    }


def _instrument_slot(state: dict[str, Any], instrument: dict[str, Any], root: str) -> dict[str, Any]:
    slots = state.setdefault("instruments", {})
    contract = str(instrument.get("instrument_full_name") or instrument.get("instrument") or root).upper()
    if root in slots and slots[root].get("instrument_full_name") != contract:
        # Derived chart history is contract-specific. Raw frames and all learning
        # remain untouched; never interpret a rollover basis gap as a market move.
        slots[root] = {"bars": [], "samples": []}
    slot = slots.setdefault(root, {"bars": [], "samples": []})
    slot["instrument_full_name"] = contract
    economics = instrument.get("instrument_economics")
    if isinstance(economics, dict):
        slot["economics"] = {
            "point_value_usd": _round(economics.get("point_value_usd")),
            "tick_size": _round(economics.get("tick_size")),
            "source": economics.get("source"),
        }
    session = instrument.get("session")
    if isinstance(session, dict):
        slot["session"] = {
            key: (_round(value) if key != "name" else value)
            for key, value in session.items()
            if key in {"name", "high", "low", "previous_high", "previous_low"}
        }
    return slot


def ingest_frame(state: dict[str, Any], frame: dict[str, Any], contracts: dict[str, str] | None = None) -> None:
    frame_id = str(frame.get("minute_id") or "")
    market = frame.get("market_snapshot")
    if not frame_id or not isinstance(market, dict):
        return
    for instrument in market.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        root = _root(instrument.get("instrument") or instrument.get("instrument_root"))
        row_1m = _timeframe(instrument, 1)
        if not root or row_1m is None:
            continue
        contract = str(instrument.get("instrument_full_name") or instrument.get("instrument") or root).upper()
        if contracts and contracts.get(root, contract) != contract:
            continue
        native_contract = (_nested(row_1m, "descriptive_state", "native_observations", "instrument_full_name")
                           or _nested(row_1m, "native_observations", "instrument_full_name"))
        if native_contract and str(native_contract).upper() != contract:
            continue
        slot = _instrument_slot(state, instrument, root)
        bar = _bar_from_instrument(frame, row_1m)
        if bar is not None:
            by_id = {str(item.get("id")): item for item in slot.get("bars", []) if isinstance(item, dict)}
            existing = by_id.get(str(bar["id"]))
            if existing is None:
                slot.setdefault("bars", []).append(bar)
            elif any(existing.get(key) != bar.get(key) for key in ("o", "h", "l", "c", "v")):
                bar["first_observed_frame_id"] = existing.get("first_observed_frame_id") or frame_id
                bar["first_observed_utc"] = existing.get("first_observed_utc") or frame.get("captured_utc")
                slot["bars"] = [bar if item is existing else item for item in slot.get("bars", [])]
        sample = _sample_from_instrument(frame, instrument, row_1m)
        if sample is not None:
            slot["samples"] = [
                item for item in slot.get("samples", [])
                if isinstance(item, dict) and item.get("frame_id") != frame_id
            ]
            slot["samples"].append(sample)
        slot["latest_partial"] = sample.get("partial") if sample else None
        slot["latest_frame_id"] = frame_id
        profile = instrument.get("volume_profile")
        if isinstance(profile, dict):
            # Latest native session/bar volume-at-price only; never invent rows.
            slot["volume_profile"] = profile
        slot["bars"] = sorted(
            (item for item in slot.get("bars", []) if isinstance(item, dict)),
            key=lambda item: (str(item.get("native_utc") or ""), str(item.get("id") or "")),
        )[-MAX_BARS:]
        slot["samples"] = sorted(
            (item for item in slot.get("samples", []) if isinstance(item, dict)),
            key=lambda item: str(item.get("frame_id") or ""),
        )[-MAX_SAMPLES:]
    prior = str(state.get("last_source_frame_id") or "")
    state["last_source_frame_id"] = max(prior, frame_id) or None


def _packet_ceiling(packet: dict[str, Any]) -> str:
    frames = packet.get("frames")
    ids = [
        str(frame.get("minute_id")) for frame in frames or []
        if isinstance(frame, dict) and frame.get("minute_id")
    ]
    return max(ids) if ids else str(packet.get("packet_id") or "")


def update_state_from_exchange(
    state: dict[str, Any], packet: dict[str, Any], exchange: Path
) -> dict[str, Any]:
    """Catch up from retained frames without ever reading beyond this packet."""
    ceiling = _packet_ceiling(packet)
    contracts: dict[str, str] = {}
    packet_frames = [frame for frame in packet.get("frames", []) if isinstance(frame, dict)]
    for frame in sorted(packet_frames, key=lambda value: str(value.get("minute_id") or "")):
        for instrument in (frame.get("market_snapshot") or {}).get("instruments", []):
            root = _root(instrument.get("instrument") or instrument.get("instrument_root"))
            if root:
                contracts[root] = str(instrument.get("instrument_full_name") or instrument.get("instrument") or root).upper()
    if str(state.get("last_source_frame_id") or "") > ceiling:
        state = _empty_state()
    directory = exchange / "glitch" / "minute-frames"
    previous = str(state.get("last_source_frame_id") or "")
    if any(root in state.get("instruments", {})
           and state["instruments"][root].get("instrument_full_name") != contract
           for root, contract in contracts.items()):
        previous = ""  # bounded, causal backfill for the newly selected contract
    try:
        paths = [
            path for path in sorted(directory.glob("*.json"))
            if (not previous or path.stem > previous) and (not ceiling or path.stem <= ceiling)
        ][-MAX_BACKFILL_FRAMES:]
    except OSError:
        paths = []
    for path in paths:
        try:
            frame = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(frame, dict):
            ingest_frame(state, frame, contracts)
    for frame in packet.get("frames", []):
        if isinstance(frame, dict) and (not ceiling or str(frame.get("minute_id") or "") <= ceiling):
            ingest_frame(state, frame, contracts)
    return state


def _median(values: Iterable[Any]) -> float | None:
    clean = [number for value in values if (number := _finite(value)) is not None]
    return statistics.median(clean) if clean else None


def _minute_stamp(row: dict[str, Any], time_key: str) -> datetime | None:
    try:
        value = str(row[time_key])
        parsed = (datetime.strptime(value, "%Y%m%dT%H%MZ") if time_key == "frame_id"
                  else datetime.fromisoformat(value.replace("Z", "+00:00")))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (KeyError, TypeError, ValueError):
        return None


def _continuous_minutes(rows: list[dict[str, Any]], time_key: str) -> list[dict[str, Any]]:
    """Use uninterrupted observations for gap-sensitive local calculations."""
    stamp = lambda row: _minute_stamp(row, time_key)

    if not rows or stamp(rows[-1]) is None:
        return []
    for index in range(len(rows) - 1, 0, -1):
        previous, current = stamp(rows[index - 1]), stamp(rows[index])
        if previous is None or current is None or current - previous != timedelta(minutes=1):
            return rows[index:]
    return rows


def _context_minutes(slot: dict[str, Any], key: str, time_key: str) -> list[dict[str, Any]]:
    """Keep observed context inside the existing 420-minute horizon, without filling gaps."""
    rows = [row for row in slot.get(key, []) if isinstance(row, dict)]
    as_of = _minute_stamp({"frame_id": slot.get("latest_frame_id")}, "frame_id")
    if as_of is None:
        as_of = _minute_stamp(rows[-1], time_key) if rows else None
    if as_of is None:
        return []
    cutoff = as_of - timedelta(minutes=MAX_BARS)
    return [row for row in rows
            if (stamp := _minute_stamp(row, time_key)) is not None and cutoff <= stamp <= as_of]


def _context_swings(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain already-confirmed references; never confirm a pivot across missing bars."""
    result: list[dict[str, Any]] = []
    start = 0
    for end in range(1, len(bars) + 1):
        if end < len(bars) and (
            _minute_stamp(bars[end], "native_utc") - _minute_stamp(bars[end - 1], "native_utc")
        ) == timedelta(minutes=1):
            continue
        for pivot in confirmed_swings(bars[start:end]):
            result.append({**pivot, "index": pivot["index"] + start})
        start = end
    return result


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    previous_close: float | None = None
    for bar in bars:
        high, low, close = (_finite(bar.get(key)) for key in ("h", "l", "c"))
        if high is None or low is None or close is None:
            continue
        value = high - low
        if previous_close is not None:
            value = max(value, abs(high - previous_close), abs(low - previous_close))
        values.append(value)
        previous_close = close
    return values


def _tolerance(bars: list[dict[str, Any]], tick: float | None) -> dict[str, Any]:
    median_true_range = _median(_true_ranges(bars[-30:]))
    if median_true_range is None and tick is None:
        return {
            "status": "unavailable",
            "points": None,
            "ticks": None,
            "recent_median_true_range_points": None,
        }
    median_true_range = median_true_range if median_true_range is not None else tick
    assert median_true_range is not None
    points = max(2 * tick, 0.2 * median_true_range) if tick is not None else 0.2 * median_true_range
    if tick is not None:
        points = math.ceil(points / tick) * tick
    return {
        "status": "available",
        "points": round(points, 8),
        "ticks": round(points / tick, 4) if tick is not None else None,
        "recent_median_true_range_points": round(median_true_range, 8),
    }


def _window_metrics(
    bars: list[dict[str, Any]], count: int, atr: float | None, point_value: float | None
) -> dict[str, Any] | None:
    window = bars[-count:]
    if len(window) < min(count, 3):
        return None
    closes = [float(bar["c"]) for bar in window]
    net = closes[-1] - closes[0]
    total_path = sum(abs(right - left) for left, right in zip(closes, closes[1:]))
    high = max(float(bar["h"]) for bar in window)
    low = min(float(bar["l"]) for bar in window)
    overlaps: list[float] = []
    for left, right in zip(window, window[1:]):
        intersection = max(0.0, min(float(left["h"]), float(right["h"])) - max(float(left["l"]), float(right["l"])))
        denominator = max(min(float(left["h"]) - float(left["l"]), float(right["h"]) - float(right["l"])), 1e-12)
        overlaps.append(min(1.0, intersection / denominator))
    changes = [right - left for left, right in zip(closes, closes[1:]) if right != left]
    reversals = sum(1 for left, right in zip(changes, changes[1:]) if left * right < 0)
    run = 0
    for change in reversed(changes):
        sign = 1 if change > 0 else -1
        if run == 0 or (run > 0) == (sign > 0):
            run += sign
        else:
            break
    return {
        "bars": len(window),
        "net_points": round(net, 8),
        "net_one_contract_usd": round(net * point_value, 8) if point_value is not None else None,
        "net_atr": round(net / atr, 6) if atr and atr > 0 else None,
        "high_low_range_points": round(high - low, 8),
        "close_path_points": round(total_path, 8),
        "signed_path_efficiency": round(net / total_path, 6) if total_path > 0 else 0.0,
        "median_adjacent_overlap_fraction": round(_median(overlaps) or 0.0, 6),
        "close_direction_reversal_fraction": round(reversals / max(1, len(changes) - 1), 6),
        "current_same_direction_close_run": run,
    }


def confirmed_swings(bars: list[dict[str, Any]], width: int = 2) -> list[dict[str, Any]]:
    """Return pivots only after the bars required to confirm them exist."""
    if len(bars) < width * 2 + 1:
        return []
    raw: list[dict[str, Any]] = []
    for index in range(width, len(bars) - width):
        bar = bars[index]
        left = bars[index - width:index]
        right = bars[index + 1:index + width + 1]
        high = float(bar["h"])
        low = float(bar["l"])
        if all(high > float(item["h"]) for item in left) and all(high >= float(item["h"]) for item in right):
            raw.append({"kind": "high", "price": high, "bar_id": bar["id"], "index": index,
                        "confirmed_after_bar_id": bars[index + width]["id"]})
        if all(low < float(item["l"]) for item in left) and all(low <= float(item["l"]) for item in right):
            raw.append({"kind": "low", "price": low, "bar_id": bar["id"], "index": index,
                        "confirmed_after_bar_id": bars[index + width]["id"]})
    raw.sort(key=lambda item: (item["index"], 0 if item["kind"] == "low" else 1))
    alternating: list[dict[str, Any]] = []
    for pivot in raw:
        if alternating and alternating[-1]["kind"] == pivot["kind"]:
            better = pivot["price"] > alternating[-1]["price"] if pivot["kind"] == "high" else pivot["price"] < alternating[-1]["price"]
            if better:
                alternating[-1] = pivot
        else:
            alternating.append(pivot)
    prior = {"high": None, "low": None}
    for pivot in alternating:
        previous = prior[pivot["kind"]]
        if previous is None:
            relation = "first_observed"
        elif pivot["price"] > previous:
            relation = "higher"
        elif pivot["price"] < previous:
            relation = "lower"
        else:
            relation = "equal"
        pivot["relation_to_prior_same_kind"] = relation
        prior[pivot["kind"]] = pivot["price"]
    return alternating


def _legs(
    bars: list[dict[str, Any]], swings: list[dict[str, Any]],
    atr: float | None, tick: float | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for start, end in zip(swings, swings[1:]):
        if end["index"] <= start["index"]:
            continue
        segment = bars[start["index"]:end["index"] + 1]
        points = float(end["price"]) - float(start["price"])
        # Match the displacement endpoints. The starting bar closes after its
        # pivot; the ending bar's close is after this leg and must be excluded.
        path = [float(start["price"]), *(float(bar["c"]) for bar in segment[:-1]), float(end["price"])]
        total_path = sum(abs(right - left) for left, right in zip(path, path[1:]))
        results.append({
            "state": "completed", "from_kind": start["kind"], "to_kind": end["kind"],
            "from_price": _round(start["price"]), "to_price": _round(end["price"]),
            "points": round(points, 8),
            "ticks": round(points / tick, 4) if tick is not None else None,
            "atr": round(points / atr, 6) if atr and atr > 0 else None,
            "path_efficiency": round(abs(points) / total_path, 6) if total_path > 0 else None,
            "bars": end["index"] - start["index"],
        })
    if swings and bars:
        start = swings[-1]
        current = float(bars[-1]["c"])
        points = current - float(start["price"])
        results.append({
            "state": "in_progress", "from_kind": start["kind"],
            "from_price": _round(start["price"]), "current_price": round(current, 8),
            "points": round(points, 8),
            "ticks": round(points / tick, 4) if tick is not None else None,
            "atr": round(points / atr, 6) if atr and atr > 0 else None,
            "bars": max(0, len(bars) - 1 - int(start["index"])),
        })
    return results[-5:]


def _touch_measurements(bars: list[dict[str, Any]], price: float, tolerance: float) -> dict[str, int | None]:
    touches = 0
    in_touch = False
    last_index: int | None = None
    response_above = 0
    response_below = 0
    for index, bar in enumerate(bars):
        hit = float(bar["l"]) - tolerance <= price <= float(bar["h"]) + tolerance
        if hit and not in_touch:
            touches += 1
            last_index = index
            future = bars[index + 1:index + 4]
            if future:
                if max(float(item["c"]) for item in future) >= price + tolerance:
                    response_above += 1
                if min(float(item["c"]) for item in future) <= price - tolerance:
                    response_below += 1
        in_touch = hit
    return {
        "touch_episodes": touches,
        "responses_above": response_above,
        "responses_below": response_below,
        "last_touch_age_bars": (len(bars) - 1 - last_index) if last_index is not None else None,
    }


def _range_reference(bars: list[dict[str, Any]], count: int = 60) -> dict[str, Any] | None:
    window = bars[-count:]
    if len(window) < 10:
        return None
    high = max(float(bar["h"]) for bar in window)
    low = min(float(bar["l"]) for bar in window)
    return {"bars": len(window), "high": round(high, 8), "low": round(low, 8),
            "mid": round((high + low) / 2, 8), "width_points": round(high - low, 8)}


def _auction_reference_ladder(
    session: dict[str, Any], range_reference: dict[str, Any] | None,
    vwap_path: dict[str, Any], current: float, tolerance: float,
) -> dict[str, list[list[Any]]]:
    """Keep a compact causal level path on both sides of current price."""
    candidates: list[tuple[float, str]] = []
    for key, label in (
        ("high", "session_high"), ("low", "session_low"),
        ("previous_high", "prior_session_high"),
        ("previous_low", "prior_session_low"),
    ):
        if (price := _finite(session.get(key))) is not None:
            candidates.append((price, label))
    if range_reference:
        for key in ("high", "low", "mid"):
            if (price := _finite(range_reference.get(key))) is not None:
                candidates.append((price, f"range{range_reference['bars']}_{key}"))
    bands = vwap_path.get("current_bands")
    if isinstance(bands, dict):
        labels = {
            "minus_2": "vwap_-2", "minus_1": "vwap_-1", "median": "vwap",
            "plus_1": "vwap_+1", "plus_2": "vwap_+2",
        }
        for key, label in labels.items():
            if (price := _finite(bands.get(key))) is not None:
                candidates.append((price, label))

    clusters: list[dict[str, Any]] = []
    for price, source in sorted(candidates):
        if clusters and abs(price - float(clusters[-1]["price"])) <= tolerance:
            cluster = clusters[-1]
            count = int(cluster["source_count"])
            cluster["price"] = (float(cluster["price"]) * count + price) / (count + 1)
            cluster["source_count"] = count + 1
            cluster["sources"].append(source)
        else:
            clusters.append({"price": price, "source_count": 1, "sources": [source]})

    ladder: dict[str, list[list[Any]]] = {"above": [], "below": []}
    for cluster in clusters:
        price = float(cluster["price"])
        signed = price - current
        relation = "above" if signed > tolerance else "below" if signed < -tolerance else None
        if relation is None:
            continue
        ladder[relation].append([
            round(price, 8), round(signed, 8), sorted(set(cluster["sources"])),
        ])
    for relation in ladder:
        ladder[relation].sort(key=lambda row: abs(float(row[1])))
        rows = ladder[relation]
        if len(rows) > MAX_AUCTION_REFERENCES_PER_SIDE:
            last = len(rows) - 1
            step = last / (MAX_AUCTION_REFERENCES_PER_SIDE - 1)
            rows = [rows[math.floor(index * step + 0.5)] for index in range(MAX_AUCTION_REFERENCES_PER_SIDE)]
        ladder[relation] = rows
    return ladder


def _levels(
    bars: list[dict[str, Any]], swings: list[dict[str, Any]], session: dict[str, Any],
    current: float, tolerance: float, tick: float | None,
    atr: float | None, point_value: float | None,
) -> list[dict[str, Any]]:
    candidates: list[tuple[float, str]] = []
    for pivot in swings[-24:]:
        candidates.append((float(pivot["price"]), f"confirmed_swing_{pivot['kind']}"))
    for key, label in (
        ("high", "session_high"), ("low", "session_low"),
        ("previous_high", "previous_session_high"), ("previous_low", "previous_session_low"),
    ):
        if (price := _finite(session.get(key))) is not None:
            candidates.append((price, label))
    reference = _range_reference(bars)
    if reference:
        for key in ("high", "low", "mid"):
            candidates.append((float(reference[key]), f"trailing_{reference['bars']}_bar_{key}"))
    clusters: list[dict[str, Any]] = []
    for price, source in sorted(candidates):
        if clusters and abs(price - float(clusters[-1]["price"])) <= tolerance:
            cluster = clusters[-1]
            count = int(cluster["source_count"])
            cluster["price"] = (float(cluster["price"]) * count + price) / (count + 1)
            cluster["source_count"] = count + 1
            cluster["sources"].append(source)
        else:
            clusters.append({"price": price, "source_count": 1, "sources": [source]})
    measured: list[dict[str, Any]] = []
    for cluster in clusters:
        price = float(cluster["price"])
        signed = price - current
        measured.append({
            "price": round(price, 8),
            "relative_to_current": "above" if signed > tolerance else "below" if signed < -tolerance else "at",
            "signed_distance_points": round(signed, 8),
            "absolute_distance_ticks": round(abs(signed) / tick, 4) if tick is not None else None,
            "absolute_distance_atr": round(abs(signed) / atr, 6) if atr and atr > 0 else None,
            "absolute_distance_one_contract_usd": (
                round(abs(signed) * point_value, 8) if point_value is not None else None
            ),
            "sources": sorted(set(cluster["sources"])),
            **_touch_measurements(bars[-180:], price, tolerance),
        })
    measured.sort(key=lambda item: (abs(float(item["signed_distance_points"])), float(item["price"])))
    return _balanced_levels(measured, MAX_LEVELS)


def _balanced_levels(levels: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Keep nearest evidence on both sides before filling by absolute distance."""
    if limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    for relation in ("at", "above", "below"):
        match = next((item for item in levels if item.get("relative_to_current") == relation), None)
        if match is not None and match not in selected:
            selected.append(match)
    for item in levels:
        if len(selected) >= limit:
            break
        if item not in selected:
            selected.append(item)
    selected.sort(key=lambda item: (abs(float(item["signed_distance_points"])), float(item["price"])))
    return selected[:limit]


def _structure_events(bars: list[dict[str, Any]], levels: list[dict[str, Any]], tolerance: float) -> list[dict[str, Any]]:
    if len(bars) < 2:
        return []
    prior, current = bars[-2], bars[-1]
    events: list[dict[str, Any]] = []
    for level in levels[:6]:
        price = float(level["price"])
        prior_close, current_close = float(prior["c"]), float(current["c"])
        event: str | None = None
        if prior_close <= price + tolerance and current_close > price + tolerance:
            event = "close_crossed_above_tolerance"
        elif prior_close >= price - tolerance and current_close < price - tolerance:
            event = "close_crossed_below_tolerance"
        elif float(current["l"]) <= price + tolerance <= float(current["h"]) and current_close > price + tolerance:
            event = "touched_then_closed_above_tolerance"
        elif float(current["l"]) <= price - tolerance <= float(current["h"]) and current_close < price - tolerance:
            event = "touched_then_closed_below_tolerance"
        if event:
            events.append({"event": event, "level_price": price, "level_sources": level["sources"],
                           "completed_bar_id": current["id"]})
    return events[:6]


def fvg_zones(
    bars: list[dict[str, Any]], current_price: float, tick: float | None,
    atr: float | None, point_value: float | None, lookback: int = 120,
) -> list[dict[str, Any]]:
    window = bars[-lookback:]
    zones: list[dict[str, Any]] = []
    for index in range(2, len(window)):
        first, third = window[index - 2], window[index]
        if float(third["l"]) > float(first["h"]):
            bottom, top, kind = float(first["h"]), float(third["l"]), "up_imbalance"
        elif float(third["h"]) < float(first["l"]):
            bottom, top, kind = float(third["h"]), float(first["l"]), "down_imbalance"
        else:
            continue
        later = window[index + 1:]
        full = any(float(bar["l"]) <= bottom for bar in later) if kind == "up_imbalance" else any(float(bar["h"]) >= top for bar in later)
        if full:
            continue
        partial = any(float(bar["l"]) < top for bar in later) if kind == "up_imbalance" else any(float(bar["h"]) > bottom for bar in later)
        distance = 0.0 if bottom <= current_price <= top else min(abs(current_price - bottom), abs(current_price - top))
        zones.append({
            "kind": kind, "bottom": round(bottom, 8), "top": round(top, 8),
            "width_points": round(top - bottom, 8),
            "fill_status": "partially_filled" if partial else "unfilled",
            "formed_bar_id": third.get("id"),
            "age_bars": len(window) - 1 - index,
            "distance_ticks": round(distance / tick, 4) if tick is not None else None,
            "distance_atr": round(distance / atr, 6) if atr and atr > 0 else None,
            "distance_one_contract_usd": (
                round(distance * point_value, 8) if point_value is not None else None
            ),
        })
    zones.sort(key=lambda item: (item["distance_ticks"], item["age_bars"]))
    return zones[:3]


def _vwap_path(samples: list[dict[str, Any]], tick: float | None) -> dict[str, Any]:
    valid = [sample for sample in samples[-60:] if _finite(sample.get("vwap")) is not None and _finite(sample.get("current_price")) is not None]
    if not valid:
        return {"status": "unavailable", "reason": "native_vwap_missing", "coverage": "0/60"}
    crossings = 0
    prior_side: int | None = None
    sigmas: list[float] = []
    for sample in valid:
        price, vwap = float(sample["current_price"]), float(sample["vwap"])
        side = 1 if price > vwap else -1 if price < vwap else 0
        if prior_side not in (None, 0) and side not in (0, prior_side):
            crossings += 1
        if side:
            prior_side = side
        deviation = _finite(sample.get("vwap_deviation"))
        if deviation is not None and abs(deviation) >= 0.05:
            sigma = abs((price - vwap) / deviation)
            if math.isfinite(sigma) and sigma >= (tick or 1e-12):
                sigmas.append(sigma)
    latest = valid[-1]
    sigma = _median(sigmas[-30:])
    vwap = float(latest["vwap"])
    return {
        "status": "available", "coverage": f"{len(valid)}/60",
        "current_vwap": round(vwap, 8),
        "current_price_minus_vwap_points": round(float(latest["current_price"]) - vwap, 8),
        "current_deviation_units": _round(latest.get("vwap_deviation"), 6),
        "vwap_change_last_15_samples_points": round(vwap - float(valid[-min(15, len(valid))]["vwap"]), 8),
        "price_vwap_crossings": crossings,
        "derived_sigma_points": round(sigma, 8) if sigma is not None else None,
        "current_bands": ({
            "minus_2": round(vwap - 2 * sigma, 8), "minus_1": round(vwap - sigma, 8),
            "median": round(vwap, 8), "plus_1": round(vwap + sigma, 8),
            "plus_2": round(vwap + 2 * sigma, 8),
        } if sigma is not None else None),
    }


def _order_flow_response(samples: list[dict[str, Any]], atr: float | None) -> dict[str, Any]:
    window = samples[-15:]
    # Cumulative delta alone is enough evidence that the OF runtime is live
    # (some minutes publish cum delta with a zero/null delta_change).
    valid = [
        sample for sample in window
        if _finite(sample.get("delta_change")) is not None
        or _finite(sample.get("cumulative_delta")) is not None
    ]
    if not valid:
        return {"status": "unavailable", "reason": "native_order_flow_missing", "coverage": f"0/{len(window)}"}
    deltas: list[float] = []
    for index, sample in enumerate(valid):
        explicit = _finite(sample.get("delta_change"))
        if explicit is not None:
            deltas.append(float(explicit))
            continue
        previous = _finite(valid[index - 1].get("cumulative_delta")) if index else None
        current = _finite(sample.get("cumulative_delta"))
        if previous is not None and current is not None:
            deltas.append(float(current - previous))
        else:
            deltas.append(0.0)
    prices = [float(sample["current_price"]) for sample in valid if _finite(sample.get("current_price")) is not None]
    price_change = prices[-1] - prices[0] if len(prices) >= 2 else 0.0
    signed_effort = sum(deltas)
    absolute_effort = sum(abs(value) for value in deltas)
    return {
        "status": "available", "coverage": f"{len(valid)}/{len(window)}",
        "signed_delta_change_sum": round(signed_effort, 8),
        "absolute_delta_change_sum": round(absolute_effort, 8),
        "price_change_points": round(price_change, 8),
        "price_change_atr": round(price_change / atr, 6) if atr and atr > 0 else None,
        "price_delta_sign_agreement": None if signed_effort == 0 or price_change == 0 else (signed_effort > 0) == (price_change > 0),
        "price_points_per_1000_absolute_delta": round(price_change * 1000 / absolute_effort, 8) if absolute_effort > 0 else None,
        "latest_aggression_balance": _round(valid[-1].get("aggression_balance"), 6),
        "latest_reliability": _round(valid[-1].get("order_flow_reliability"), 6),
        "latest_classification_coverage": _round(valid[-1].get("classification_coverage"), 6),
    }


def _evidence_quality(
    *,
    session: dict[str, Any],
    context_bars: list[Any],
    bars: list[Any],
    samples: list[Any],
    tick: float | None,
    point_value: float | None,
    atr: float | None,
    vwap_path: dict[str, Any],
    flow_response: dict[str, Any],
    latest_frame_id: Any,
) -> dict[str, Any]:
    """Ready only when contiguous history and session extremes are actually usable."""
    contiguous = len(bars)
    context = len(context_bars)
    previous_incomplete = (
        session.get("previous_high") is None
        or session.get("previous_low") is None
        or str(session.get("extremes_status") or "") == "partial_no_previous"
    )
    contiguous_incomplete = contiguous < 60 <= context
    missing = [
        name for name, absent in (
            ("native_economics", tick is None or point_value is None),
            ("atr", atr is None),
            ("vwap", vwap_path.get("status") == "unavailable"),
            ("order_flow", flow_response.get("status") == "unavailable"),
            ("previous_session_extremes", previous_incomplete),
            ("contiguous_bar_history", contiguous_incomplete),
        ) if absent
    ]
    # Soft fields (vwap/flow/atr) stay in missing[]; status hard-gates on history
    # integrity so a truncated reload cannot advertise ready session room.
    if contiguous >= 60 and not previous_incomplete and not contiguous_incomplete:
        status = "ready"
    elif context >= 60 or contiguous >= 20:
        status = "partial"
    else:
        status = "warming"
    return {
        "status": status,
        "completed_bar_count": context,
        "sample_count": len(samples),
        "contiguous_completed_bar_count": contiguous,
        "latest_source_frame_id": latest_frame_id,
        "missing": missing,
    }


def instrument_perception(root: str, slot: dict[str, Any]) -> dict[str, Any]:
    context_bars = _context_minutes(slot, "bars", "native_utc")
    bars = _continuous_minutes(context_bars, "native_utc")
    samples = _continuous_minutes(_context_minutes(slot, "samples", "frame_id"), "frame_id")
    economics = slot.get("economics") if isinstance(slot.get("economics"), dict) else {}
    tick_value = _finite(economics.get("tick_size"))
    point_value_value = _finite(economics.get("point_value_usd"))
    tick = tick_value if tick_value is not None and tick_value > 0 else None
    point_value = (
        point_value_value if point_value_value is not None and point_value_value > 0 else None
    )
    latest_sample = samples[-1] if samples else {}
    current = _finite(latest_sample.get("current_price"))
    if current is None and bars:
        current = float(bars[-1]["c"])
    atr = _finite(latest_sample.get("atr"))
    tolerance = _tolerance(bars, tick) if bars else {
        "status": "unavailable", "points": None, "ticks": None,
        "recent_median_true_range_points": None,
    }
    swings = confirmed_swings(bars)
    context_swings = _context_swings(context_bars)
    session = slot.get("session") if isinstance(slot.get("session"), dict) else {}
    tolerance_points = _finite(tolerance.get("points"))
    levels = (
        _levels(
            bars, context_swings, session, current or 0.0,
            tolerance_points, tick, atr, point_value,
        )
        if bars and current is not None and tolerance_points is not None else []
    )
    windows = {
        str(count): value for count in (5, 15, 60, 180)
        if (value := _window_metrics(bars, count, atr, point_value)) is not None
    }
    recent_tr = _median(_true_ranges(bars[-5:]))
    prior_tr = _median(_true_ranges(bars[-25:-5])) if len(bars) > 5 else None
    expansion_ratio = recent_tr / prior_tr if recent_tr is not None and prior_tr and prior_tr > 0 else None
    visible_swings = [{
        "kind": pivot["kind"], "price": _round(pivot["price"]),
        "relation_to_prior_same_kind": pivot["relation_to_prior_same_kind"],
        "age_bars": len(context_bars) - 1 - int(pivot["index"]),
    } for pivot in context_swings[-8:]]
    range_reference = _range_reference(bars)
    vwap_path = _vwap_path(samples, tick)
    flow_response = _order_flow_response(samples, atr)
    return {
        "instrument": root, "instrument_full_name": slot.get("instrument_full_name"),
        "current_price": _round(current), "economics": economics,
        "evidence_quality": _evidence_quality(
            session=session if isinstance(session, dict) else {},
            context_bars=context_bars,
            bars=bars,
            samples=samples,
            tick=tick,
            point_value=point_value,
            atr=atr,
            vwap_path=vwap_path,
            flow_response=flow_response,
            latest_frame_id=slot.get("latest_frame_id"),
        ),
        "measurement_tolerance": tolerance,
        "price_sequence": {
            "windows": windows, "confirmed_swings": visible_swings,
            "legs": _legs(bars, swings, atr, tick),
            "current_partial_bar": slot.get("latest_partial"),
            "swing_confirmation_delay_bars": 2,
        },
        "auction_evidence": {
            "recent_vs_prior_median_true_range_ratio": round(expansion_ratio, 6) if expansion_ratio is not None else None,
            "recent_median_true_range_points": _round(recent_tr),
            "prior_median_true_range_points": _round(prior_tr),
            "balance_and_direction_are_separate_measurements": True,
            "structure_events": (
                _structure_events(bars, levels, tolerance_points)
                if tolerance_points is not None else []
            ),
        },
        "range_reference": range_reference,
        # Sorted by absolute distance; relative_to_current keeps both sides
        # explicit without duplicating the same level in another structure.
        "nearest_measured_levels": levels,
        "auction_reference_ladder": (
            _auction_reference_ladder(
                session, range_reference, vwap_path, current, tolerance_points,
            )
            if current is not None and tolerance_points is not None else {"above": [], "below": []}
        ),
        "vwap_path": vwap_path,
        "order_flow_response": flow_response,
        "unfilled_three_bar_imbalances": (
            fvg_zones(bars, current or 0.0, tick, atr, point_value)
            if bars and current is not None else []
        ),
    }


@lru_cache(maxsize=8)
def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _line(draw: Any, points: list[tuple[float, float]], fill: str, width: int = 1) -> None:
    if len(points) >= 2:
        draw.line(points, fill=fill, width=width)


def _opening_range(bars: list[dict[str, Any]], minutes: int = 30) -> dict[str, Any] | None:
    """First N minutes of the contiguous segment that ends at the latest bar."""
    if len(bars) < 5 or minutes < 5:
        return None
    start = 0
    for index in range(len(bars) - 1, 0, -1):
        previous = _minute_stamp(bars[index - 1], "native_utc")
        current = _minute_stamp(bars[index], "native_utc")
        if previous is None or current is None or current - previous != timedelta(minutes=1):
            start = index
            break
    window = bars[start:start + minutes]
    if len(window) < 5:
        return None
    high = max(float(bar["h"]) for bar in window)
    low = min(float(bar["l"]) for bar in window)
    return {
        "bars": len(window),
        "high": round(high, 8),
        "low": round(low, 8),
        "mid": round((high + low) / 2, 8),
        "source": f"or{len(window)}_contiguous_open",
    }


def _value_area_from_totals(
    totals: dict[float, float], value_fraction: float = 0.7,
) -> tuple[float, float, float] | None:
    positive = {price: volume for price, volume in totals.items() if volume > 0}
    if not positive:
        return None
    session_total = sum(positive.values())
    if session_total <= 0:
        return None
    poc = max(positive.items(), key=lambda item: (item[1], -abs(item[0]), -item[0]))[0]
    ordered = sorted(positive)
    lo = hi = ordered.index(poc)
    included = positive[poc]
    target = session_total * value_fraction
    while included < target and (lo > 0 or hi < len(ordered) - 1):
        below = positive[ordered[lo - 1]] if lo > 0 else -1.0
        above = positive[ordered[hi + 1]] if hi < len(ordered) - 1 else -1.0
        if above > below:
            hi += 1
            included += positive[ordered[hi]]
        elif below > above:
            lo -= 1
            included += positive[ordered[lo]]
        elif hi < len(ordered) - 1:
            hi += 1
            included += positive[ordered[hi]]
        else:
            lo -= 1
            included += positive[ordered[lo]]
    return poc, ordered[lo], ordered[hi]


def _volume_profile_overlay(slot: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Native volume-at-price when ready; otherwise a bar-distributed session profile."""
    tick = _finite(_nested(slot, "economics", "tick_size"))
    profile = slot.get("volume_profile") if isinstance(slot.get("volume_profile"), dict) else {}
    if profile.get("status") == "ready":
        # Reject profiles whose newest 1m footprint is older than the chart window
        # (seen on MES when a stale prior-session blob remains on the instrument).
        bar_start = _minute_stamp(bars[0], "native_utc") if bars else None
        newest_fp = None
        for item in profile.get("bars_1m") or []:
            if not isinstance(item, dict):
                continue
            stamp = _minute_stamp({"native_utc": item.get("utc_time") or item.get("utc")}, "native_utc")
            if stamp is not None and (newest_fp is None or stamp > newest_fp):
                newest_fp = stamp
        if bar_start is not None and newest_fp is not None and newest_fp < bar_start - timedelta(minutes=30):
            profile = {}
    if profile.get("status") == "ready":
        full_map = profile.get("full_map") if isinstance(profile.get("full_map"), dict) else {}
        rows = profile.get("session_rows") if isinstance(profile.get("session_rows"), list) else []
        histogram: dict[float, dict[str, float]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = _finite(row.get("p") if "p" in row else row.get("price"))
            if price is None:
                continue
            bid, ask = _row_bid_ask(row)
            total = bid + ask
            if total <= 0 and (volume := _finite(row.get("v") or row.get("volume"))) is not None:
                total = max(0.0, volume)
                bid = ask = total * 0.5
            if total <= 0:
                continue
            bucket = histogram.setdefault(price, {"bid": 0.0, "ask": 0.0, "total": 0.0})
            bucket["bid"] += bid
            bucket["ask"] += ask
            bucket["total"] += total
        poc = _finite(full_map.get("poc"))
        vah = _finite(full_map.get("vah"))
        val = _finite(full_map.get("val"))
        if poc is None or vah is None or val is None:
            derived = _value_area_from_totals({price: row["total"] for price, row in histogram.items()})
            if derived is not None:
                poc, val, vah = derived
        footprint = [bar for bar in (profile.get("bars_1m") or []) if isinstance(bar, dict)]
        return {
            "status": "native" if histogram or poc is not None else "unavailable",
            "source": "volume_at_price",
            "poc": poc, "vah": vah, "val": val,
            "histogram": histogram,
            "footprint_bars": footprint[-24:],
            "classification": profile.get("classification"),
        }
    if len(bars) < 10 or tick is None or tick <= 0:
        return {"status": "unavailable", "reason": "native_profile_and_bars_insufficient"}
    totals: dict[float, float] = {}
    for bar in bars:
        low, high = float(bar["l"]), float(bar["h"])
        volume = max(0.0, float(bar.get("v") or 0.0))
        if volume <= 0 or high < low:
            continue
        start = math.floor(low / tick) * tick
        levels = []
        price = start
        while price <= high + tick * 0.5:
            levels.append(round(price, 8))
            price = round(price + tick, 10)
        if not levels:
            continue
        share = volume / len(levels)
        for price in levels:
            totals[price] = totals.get(price, 0.0) + share
    derived = _value_area_from_totals(totals)
    if derived is None:
        return {"status": "unavailable", "reason": "empty_distributed_profile"}
    poc, val, vah = derived
    return {
        "status": "approximated_from_1m_ohlcv",
        "source": "completed_1m_volume_distribution",
        "poc": poc, "vah": vah, "val": val,
        "histogram": {
            price: {"bid": volume * 0.5, "ask": volume * 0.5, "total": volume}
            for price, volume in totals.items()
        },
        "footprint_bars": [],
    }


def _sample_flow_by_minute(samples: list[dict[str, Any]]) -> dict[datetime, dict[str, float]]:
    by_minute: dict[datetime, dict[str, float]] = {}
    for sample in samples:
        stamp = _minute_stamp(sample, "frame_id")
        if stamp is None:
            continue
        row = by_minute.setdefault(stamp, {})
        for key in ("delta_change", "aggression_balance", "cumulative_delta", "vwap", "vwap_deviation", "current_price"):
            if (value := _finite(sample.get(key))) is not None:
                row[key] = value
    return by_minute


def _flow_for_bar(
    bar: dict[str, Any], flow_by_minute: dict[datetime, dict[str, float]],
) -> dict[str, float]:
    """Completed bars are sealed on the next frame; try native, +1m, and first_observed."""
    stamp = _minute_stamp(bar, "native_utc")
    if stamp is not None:
        if stamp in flow_by_minute:
            return flow_by_minute[stamp]
        nxt = stamp + timedelta(minutes=1)
        if nxt in flow_by_minute:
            return flow_by_minute[nxt]
    frame_id = bar.get("first_observed_frame_id")
    if frame_id:
        observed = _minute_stamp({"frame_id": frame_id}, "frame_id")
        if observed is not None and observed in flow_by_minute:
            return flow_by_minute[observed]
    return {}


def _row_bid_ask(row: dict[str, Any]) -> tuple[float, float]:
    """Native volume-at-price rows use b/a; keep bid/ask aliases for tests/fixtures."""
    bid = _finite(row.get("b") if "b" in row else row.get("bid")) or 0.0
    ask = _finite(row.get("a") if "a" in row else row.get("ask")) or 0.0
    return max(0.0, bid), max(0.0, ask)


def _footprint_by_bar_utc(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Index native 1m footprint rows by completed-bar utc_time."""
    indexed: dict[str, list[dict[str, Any]]] = {}
    for bar in profile.get("footprint_bars") or []:
        if not isinstance(bar, dict):
            continue
        stamp = str(bar.get("utc_time") or bar.get("utc") or "")
        rows = bar.get("rows") if isinstance(bar.get("rows"), list) else []
        clean = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price = _finite(row.get("p") if "p" in row else row.get("price"))
            if price is None:
                continue
            bid, ask = _row_bid_ask(row)
            if bid <= 0 and ask <= 0:
                continue
            clean.append({"p": price, "bid": bid, "ask": ask})
        if stamp and clean:
            indexed[stamp] = clean
    return indexed


def _overlay_values(active_trade_state: dict[str, Any] | None, root: str) -> list[tuple[str, float, str]]:
    overlays: list[tuple[str, float, str]] = []
    trades = active_trade_state.get("trades", []) if isinstance(active_trade_state, dict) else []
    for trade in trades:
        if not isinstance(trade, dict) or _root(trade.get("instrument")) != root:
            continue
        if (entry := _finite(trade.get("average_price"))) is not None:
            overlays.append(("entry/breakeven", entry, "#f6c85f"))
        math_row = trade.get("deterministic_management_math")
        if isinstance(math_row, dict):
            if (current := _finite(math_row.get("current_price"))) is not None:
                overlays.append(("current(native)", current, "#ffffff"))
            for leg in math_row.get("stop_legs", []):
                if isinstance(leg, dict) and (price := _finite(leg.get("price"))) is not None:
                    overlays.append(("working stop", price, "#ff6b6b"))
            for leg in math_row.get("target_legs", []):
                if isinstance(leg, dict) and (price := _finite(leg.get("price"))) is not None:
                    overlays.append(("working target", price, "#4dd4ac"))
        entry = _finite(trade.get("average_price"))
        peak = _finite(trade.get("peak_unrealized_pnl_usd"))
        quantity = _finite(trade.get("quantity"))
        point_value = _finite(math_row.get("point_value_usd")) if isinstance(math_row, dict) else None
        side = str(trade.get("side") or "")
        if entry is not None and peak is not None and quantity and point_value and quantity > 0 and point_value > 0:
            mfe = entry + peak / (quantity * point_value) * (1 if side == "long" else -1)
            overlays.append(("sampled MFE", mfe, "#9b8cff"))
    unique: dict[tuple[str, float], tuple[str, float, str]] = {}
    for item in overlays:
        unique[(item[0], round(item[1], 8))] = item
    return list(unique.values())


def _draw_panel(
    image: Any, bounds: tuple[int, int, int, int], root: str, slot: dict[str, Any],
    perception: dict[str, Any], active_trade_state: dict[str, Any] | None,
) -> None:
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = bounds
    # Full retained horizon (up to MAX_BARS), not a shorter visual crop.
    bars = _context_minutes(slot, "bars", "native_utc")
    samples = _context_minutes(slot, "samples", "frame_id")
    overlays = _overlay_values(active_trade_state, root)
    opening = _opening_range(bars, 30)
    profile = _volume_profile_overlay(slot, bars)
    flow_by_minute = _sample_flow_by_minute(samples)
    draw.rectangle(bounds, fill="#11161d", outline="#36404a")
    hours = max(1, int(round(len(bars) / 60))) if bars else 0
    draw.text(
        (left + 10, top + 7),
        f"{root}  {len(bars)}x1m (~{hours}h) + live partial",
        fill="#e8eef5", font=_font(15),
    )
    if not bars:
        draw.text((left + 10, top + 36), "warming: no native completed bars", fill="#8d99a6", font=_font(13))
        return
    profile_width = 88
    chart_left, chart_right = left + 52, right - (68 + profile_width)
    # RSI strip removed: reclaim vertical space for price action / footprint.
    chart_top, chart_bottom = top + 30, bottom - 58
    volume_top, volume_bottom = chart_bottom + 6, bottom - 8
    footprint_by_utc = _footprint_by_bar_utc(profile)
    max_footprint_bars = 18
    price_values = [float(value) for bar in bars for value in (bar["h"], bar["l"])]
    price_values.extend(value for _, value, _ in overlays)
    for key in ("poc", "vah", "val"):
        if (price := _finite(profile.get(key))) is not None:
            price_values.append(price)
    if opening:
        price_values.extend([float(opening["high"]), float(opening["low"])])
    session = slot.get("session") if isinstance(slot.get("session"), dict) else {}
    for key in ("high", "low", "previous_high", "previous_low"):
        if (price := _finite(session.get(key))) is not None:
            price_values.append(price)
    for sample in samples:
        if (vwap := _finite(sample.get("vwap"))) is not None:
            price_values.append(vwap)
            price = _finite(sample.get("current_price"))
            deviation = _finite(sample.get("vwap_deviation"))
            if price is not None and deviation is not None and abs(deviation) >= 0.05:
                sigma = abs((price - vwap) / deviation)
                if math.isfinite(sigma):
                    price_values.extend([vwap + offset * sigma for offset in (-2, -1, 1, 2)])
    partial = slot.get("latest_partial") if isinstance(slot.get("latest_partial"), dict) else None
    if partial:
        price_values.extend(float(partial[key]) for key in ("h", "l") if _finite(partial.get(key)) is not None)
    low, high = min(price_values), max(price_values)
    padding = max((high - low) * 0.05, _finite(_nested(slot, "economics", "tick_size")) or 0.25)
    low, high = low - padding, high + padding
    span = max(high - low, 1e-9)
    first_time = _minute_stamp(bars[0], "native_utc")
    minute_offsets = [
        ((_minute_stamp(bar, "native_utc") - first_time).total_seconds() / 60) if first_time else float(index)
        for index, bar in enumerate(bars)
    ]
    x_count = minute_offsets[-1] + 1 + (1 if partial else 0)
    x_step = max(1.0, (chart_right - chart_left) / max(1, x_count))
    price_y = lambda value: chart_bottom - (float(value) - low) / span * (chart_bottom - chart_top)

    def sample_x(sample: dict[str, Any]) -> float | None:
        stamp = _minute_stamp(sample, "frame_id")
        if stamp is None or first_time is None:
            return None
        offset = (stamp - first_time).total_seconds() / 60
        if offset < -0.5 or offset > minute_offsets[-1] + 2:
            return None
        return chart_left + (offset + 0.5) * x_step

    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = chart_top + fraction * (chart_bottom - chart_top)
        draw.line((chart_left, y, chart_right, y), fill="#27313b", width=1)
        draw.text((chart_right + 5, y - 7), f"{high - fraction * span:.2f}", fill="#8d99a6", font=_font(11))
    if opening and low <= float(opening["high"]) and high >= float(opening["low"]):
        draw.rectangle(
            (chart_left, price_y(min(float(opening["high"]), high)),
             chart_right, price_y(max(float(opening["low"]), low))),
            fill="#1a2430",
        )
        for label, price in (("OR high", opening["high"]), ("OR low", opening["low"])):
            y = price_y(float(price))
            draw.line((chart_left, y, chart_right, y), fill="#4a6d8c", width=1)
            draw.text((chart_left + 4, y - 12), f"{label} {float(price):.2f}", fill="#7ea0bd", font=_font(10))
    for zone in perception.get("unfilled_three_bar_imbalances", []):
        if not isinstance(zone, dict):
            continue
        zone_low, zone_high = _finite(zone.get("bottom")), _finite(zone.get("top"))
        if zone_low is None or zone_high is None or zone_high < low or zone_low > high:
            continue
        color = "#17332e" if zone.get("kind") == "up_imbalance" else "#3a241d"
        age = max(0, int(_finite(zone.get("age_bars")) or 0))
        formed_index = max(0, len(bars) - 1 - age)
        formed_x = chart_left + (minute_offsets[formed_index] + 0.5) * x_step
        draw.rectangle(
            (formed_x, price_y(min(zone_high, high)), chart_right, price_y(max(zone_low, low))),
            fill=color,
        )
    max_volume = max(float(bar.get("v") or 0) for bar in bars) or 1.0
    footprint_start = max(0, len(bars) - max_footprint_bars)
    for index, bar in enumerate(bars):
        x = chart_left + (minute_offsets[index] + 0.5) * x_step
        if index and minute_offsets[index] - minute_offsets[index - 1] > 1:
            gap_x = x - 0.5 * x_step
            draw.line((gap_x, chart_top, gap_x, chart_bottom), fill="#77838e", width=1)
        open_y, close_y = price_y(bar["o"]), price_y(bar["c"])
        high_y, low_y = price_y(bar["h"]), price_y(bar["l"])
        color = "#38c5ad" if float(bar["c"]) > float(bar["o"]) else "#e9783f" if float(bar["c"]) < float(bar["o"]) else "#8d99a6"
        half = max(1, min(8, int(x_step * 0.45)))
        stamp = _minute_stamp(bar, "native_utc")
        flow = _flow_for_bar(bar, flow_by_minute)
        delta = _finite(flow.get("delta_change"))
        if delta is None:
            # Recover signed effort from cumulative path when delta_change is 0/null.
            cum = _finite(flow.get("cumulative_delta"))
            prev_flow = _flow_for_bar(bars[index - 1], flow_by_minute) if index else {}
            prev_cum = _finite(prev_flow.get("cumulative_delta"))
            if cum is not None and prev_cum is not None:
                delta = cum - prev_cum
        utc_key = str(bar.get("native_utc") or "")
        rows = footprint_by_utc.get(utc_key) if index >= footprint_start else None
        footprint_imbalance = None
        if rows:
            fp_half = max(half, 7)
            draw.line((x, high_y, x, low_y), fill="#5a6670", width=1)
            body_top, body_bottom = min(open_y, close_y), max(open_y, close_y)
            draw.rectangle(
                (x - fp_half, body_top, x + fp_half, max(body_bottom, body_top + 1)),
                outline=color, width=1,
            )
            bid_total = sum(float(row["bid"]) for row in rows)
            ask_total = sum(float(row["ask"]) for row in rows)
            footprint_imbalance = ask_total - bid_total
            # Traditional footprint: bid left of wick, ask right, exact counts.
            for row in rows:
                price = float(row["p"])
                if not low <= price <= high:
                    continue
                y = int(price_y(price))
                bid = int(round(float(row["bid"])))
                ask = int(round(float(row["ask"])))
                bid_fill = "#6fa8dc" if bid >= ask else "#aeb6bf"
                ask_fill = "#e9783f" if ask > bid else "#aeb6bf"
                bid_text, ask_text = str(bid), str(ask)
                bx = x - fp_half - 1 - 5 * len(bid_text)
                ax = x + fp_half + 2
                draw.rectangle((bx - 1, y - 6, bx + 5 * len(bid_text) + 1, y + 5), fill="#0b0f14")
                draw.rectangle((ax - 1, y - 6, ax + 5 * len(ask_text) + 1, y + 5), fill="#0b0f14")
                draw.text((bx, y - 5), bid_text, fill=bid_fill, font=_font(9))
                draw.text((ax, y - 5), ask_text, fill=ask_fill, font=_font(9))
        else:
            draw.line((x, high_y, x, low_y), fill=color, width=1)
            draw.rectangle((x - max(1, min(3, half)), min(open_y, close_y), x + max(1, min(3, half)), max(open_y, close_y) + 1), fill=color)
        signed = delta if delta not in (None, 0.0) else footprint_imbalance
        volume_color = (
            "#2f8f75" if signed is not None and signed > 0
            else "#b35a3a" if signed is not None and signed < 0
            else "#3a5965"
        )
        volume_height = float(bar.get("v") or 0) / max_volume * (volume_bottom - volume_top)
        draw.rectangle(
            (x - max(1, min(3, half)), volume_bottom - volume_height, x + max(1, min(3, half)), volume_bottom),
            fill=volume_color,
        )
        aggression = _finite(flow.get("aggression_balance"))
        if aggression is not None and abs(aggression) >= 0.2:
            marker = "#7dffa8" if aggression > 0 else "#ff9b7d"
            draw.ellipse((x - 2, high_y - 7, x + 2, high_y - 3), fill=marker)
    if partial:
        x = chart_left + (minute_offsets[-1] + 1.5) * x_step
        open_y, close_y = price_y(partial["o"]), price_y(partial["c"])
        draw.line((x, price_y(partial["h"]), x, price_y(partial["l"])), fill="#f2f5f7", width=1)
        half = max(1, min(4, int(x_step * 0.4)))
        draw.rectangle((x - half, min(open_y, close_y), x + half, max(open_y, close_y) + 1), outline="#f2f5f7", width=2)
    vwap_bands: dict[int, list[tuple[float, float]]] = {offset: [] for offset in (-2, -1, 0, 1, 2)}
    for sample in samples:
        x = sample_x(sample)
        if x is None:
            continue
        vwap = _finite(sample.get("vwap"))
        sample_price = _finite(sample.get("current_price"))
        deviation = _finite(sample.get("vwap_deviation"))
        if vwap is not None:
            vwap_bands[0].append((x, price_y(vwap)))
            if sample_price is not None and deviation is not None and abs(deviation) >= 0.05:
                sigma = abs((sample_price - vwap) / deviation)
                if math.isfinite(sigma):
                    for offset in (-2, -1, 1, 2):
                        vwap_bands[offset].append((x, price_y(vwap + offset * sigma)))

    def observed_line(points: list[tuple[float, float]], color: str, width: int = 1) -> None:
        # Do not draw invented continuity through unobserved indicator minutes.
        for left_point, right_point in zip(points, points[1:]):
            if right_point[0] - left_point[0] <= x_step * 1.51:
                _line(draw, [left_point, right_point], color, width)

    for offset in (-2, -1, 1, 2):
        observed_line(vwap_bands[offset], "#675f38")
    observed_line(vwap_bands[0], "#f2c94c", 2)
    if vwap_bands[0]:
        last_x, last_y = vwap_bands[0][-1]
        draw.text((min(last_x + 4, chart_right - 70), last_y - 12), "VWAP", fill="#f2c94c", font=_font(11))
    histogram = profile.get("histogram") if isinstance(profile.get("histogram"), dict) else {}
    if histogram:
        max_node = max((row.get("total") or 0) for row in histogram.values()) or 1.0
        profile_left = chart_right + 8
        profile_right = right - 10
        for price, row in histogram.items():
            if not low <= float(price) <= high:
                continue
            total = float(row.get("total") or 0)
            if total <= 0:
                continue
            width = total / max_node * (profile_right - profile_left)
            y = price_y(float(price))
            bid = float(row.get("bid") or 0)
            ask = float(row.get("ask") or 0)
            split = bid / (bid + ask) if (bid + ask) > 0 else 0.5
            draw.rectangle((profile_left, y - 1, profile_left + width * split, y + 1), fill="#3d6d8c")
            draw.rectangle(
                (profile_left + width * split, y - 1, profile_left + width, y + 1), fill="#8c5a3d",
            )
        draw.text((profile_left, chart_top), "VP", fill="#8d99a6", font=_font(10))
    for key, color, label in (
        ("val", "#6fa8dc", "VAL"), ("poc", "#f2c94c", "POC"), ("vah", "#6fa8dc", "VAH"),
    ):
        price = _finite(profile.get(key))
        if price is not None and low <= price <= high:
            y = price_y(price)
            draw.line((chart_left, y, chart_right, y), fill=color, width=1)
            draw.text((chart_right - 78, y - 11), f"{label} {price:.2f}", fill=color, font=_font(10))
    for pivot in perception.get("price_sequence", {}).get("confirmed_swings", [])[-6:]:
        if not isinstance(pivot, dict):
            continue
        price = _finite(pivot.get("price"))
        if price is None or not low <= price <= high:
            continue
        age = max(0, int(_finite(pivot.get("age_bars")) or 0))
        index = max(0, len(bars) - 1 - age)
        x = chart_left + (minute_offsets[index] + 0.5) * x_step
        y = price_y(price)
        kind = str(pivot.get("kind") or "swing")
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline="#c3d0dc", width=1)
        draw.text((x + 4, y - 10), kind[:3], fill="#c3d0dc", font=_font(9))
    for level in perception.get("nearest_measured_levels", [])[:8]:
        price = _finite(level.get("price")) if isinstance(level, dict) else None
        if price is not None and low <= price <= high:
            y = price_y(price)
            sources = level.get("sources", [])
            canonical = any("session" in str(source) for source in sources)
            color = "#5a7891" if canonical else "#46606e"
            draw.line((chart_left, y, chart_right, y), fill=color, width=1)
            if canonical:
                draw.text((chart_left + 4, y + 1), str(sources[0])[:22], fill=color, font=_font(10))
    for label, price, color in overlays:
        if low <= price <= high:
            y = price_y(price)
            draw.line((chart_left, y, chart_right, y), fill=color, width=2)
            draw.text((chart_left + 4, y - 13), f"{label} {price:.2f}", fill=color, font=_font(11))
    draw.text((left + 10, volume_top), "vol (delta / footprint imbalance)", fill="#77838e", font=_font(10))
    if footprint_by_utc:
        draw.text((left + 250, volume_top), "footprint: bid left | ask right", fill="#77838e", font=_font(10))
    draw.text((chart_left, bottom - 18), str(bars[0].get("native_utc") or "")[:16], fill="#77838e", font=_font(10))
    if len(bars) < minute_offsets[-1] + 1:
        draw.text((chart_left + 210, bottom - 18), "missing minutes shown as gaps", fill="#77838e", font=_font(10))
    draw.text((chart_right - 125, bottom - 18), str(bars[-1].get("native_utc") or "")[:16], fill="#77838e", font=_font(10))
    vwap_status = perception.get("vwap_path", {}).get("status")
    flow_status = perception.get("order_flow_response", {}).get("status")
    vp_status = str(profile.get("status") or "unavailable")
    draw.text(
        (right - 420, top + 8),
        f"VWAP {vwap_status} | OF {flow_status} | VP {vp_status}",
        fill="#8d99a6", font=_font(11),
    )


def render_market_context(
    state: dict[str, Any], market_map: dict[str, Any], output_path: Path,
    active_trade_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from PIL import Image
    roots = [root for root in market_map.get("instrument_order", []) if root in state.get("instruments", {})]
    if not roots:
        return {"status": "unavailable", "reason": "no_instruments_to_render"}
    positioned = market_map.get("view") == "position_management"
    width = 1400
    panel_height = 760 if positioned else 380
    height = panel_height * len(roots)
    image = Image.new("RGB", (width, height), "#0b0f14")
    by_root = {item["instrument"]: item for item in market_map.get("instruments", []) if isinstance(item, dict)}
    for index, root in enumerate(roots):
        _draw_panel(
            image, (0, index * panel_height, width - 1, (index + 1) * panel_height - 1),
            root, state["instruments"][root], by_root[root], active_trade_state,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(output_path.parent), prefix=output_path.stem, suffix=".tmp")
    os.close(fd)
    try:
        image.save(temporary, format="PNG", optimize=False, compress_level=6)
        os.replace(temporary, output_path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    paths = sorted(output_path.parent.glob("*.png"), key=lambda path: path.name)
    for path in paths[:-MAX_IMAGE_FILES]:
        try:
            path.unlink()
        except OSError:
            pass
    return {
        "status": "attached", "format": "png", "width": width, "height": height,
        "panels": roots, "semantics": "spatial_context_only_numeric_packet_authoritative",
    }


def _ordered_roots(packet: dict[str, Any], positioned_roots: Iterable[str] | None) -> list[str]:
    available: set[str] = set()
    frames = packet.get("frames")
    latest = frames[-1] if isinstance(frames, list) and frames and isinstance(frames[-1], dict) else {}
    market = latest.get("market_snapshot") if isinstance(latest, dict) else {}
    for instrument in market.get("instruments", []) if isinstance(market, dict) else []:
        if isinstance(instrument, dict) and (root := _root(instrument.get("instrument") or instrument.get("instrument_root"))):
            available.add(root)
    requested = {_root(value) for value in positioned_roots or [] if _root(value)}
    if requested:
        available &= requested
    return [root for root in ROOT_ORDER if root in available] + sorted(available - set(ROOT_ORDER))


def _trim_to_budget(value: dict[str, Any]) -> None:
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        instrument["nearest_measured_levels"] = _balanced_levels(
            instrument.get("nearest_measured_levels", []), 5
        )
        sequence = instrument.get("price_sequence")
        if isinstance(sequence, dict):
            sequence["confirmed_swings"] = sequence.get("confirmed_swings", [])[-6:]
            sequence["legs"] = sequence.get("legs", [])[-4:]
        instrument["unfilled_three_bar_imbalances"] = instrument.get("unfilled_three_bar_imbalances", [])[:2]
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        instrument["nearest_measured_levels"] = _balanced_levels(
            instrument.get("nearest_measured_levels", []), 3
        )
        sequence = instrument.get("price_sequence")
        if isinstance(sequence, dict):
            sequence["confirmed_swings"] = sequence.get("confirmed_swings", [])[-5:]
            sequence["legs"] = sequence.get("legs", [])[-3:]
        auction = instrument.get("auction_evidence")
        if isinstance(auction, dict):
            auction["structure_events"] = auction.get("structure_events", [])[:2]
        instrument["unfilled_three_bar_imbalances"] = instrument.get("unfilled_three_bar_imbalances", [])[:1]
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        levels = instrument.get("nearest_measured_levels", [])
        if isinstance(levels, list):
            instrument["nearest_measured_levels"] = _balanced_levels(levels, 3)
        sequence = instrument.get("price_sequence")
        if isinstance(sequence, dict):
            windows = sequence.get("windows")
            if isinstance(windows, dict):
                close_run = None
                for requested, window in windows.items():
                    if not isinstance(window, dict):
                        continue
                    close_run = window.get("current_same_direction_close_run", close_run)
                    # Coverage is not redundant: a requested 60-minute window
                    # may contain only a few consecutive bars after a data gap.
                    if str(window.get("bars")) == str(requested):
                        window.pop("bars", None)
                    for repeated in ("net_one_contract_usd", "close_path_points", "current_same_direction_close_run"):
                        window.pop(repeated, None)
                sequence["current_same_direction_close_run"] = close_run
        auction = instrument.get("auction_evidence")
        if isinstance(auction, dict):
            compact_events = []
            for event in auction.get("structure_events", [])[:1]:
                if isinstance(event, dict):
                    compact_events.append({
                        key: event.get(key) for key in (
                            "event", "level_price", "completed_bar_id"
                        ) if key in event
                    })
            auction["structure_events"] = compact_events
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    # In a three-instrument flat scan the rendered six-hour chart retains the
    # long visual path. If text still exceeds its hard budget, omit only the
    # redundant 180-row aggregate; 5/15/60 measurements remain numeric.
    for instrument in value.get("instruments", []):
        sequence = instrument.get("price_sequence") if isinstance(instrument, dict) else None
        windows = sequence.get("windows") if isinstance(sequence, dict) else None
        if isinstance(windows, dict):
            windows.pop("180", None)
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        instrument.pop("instrument_full_name", None)
        sequence = instrument.get("price_sequence")
        if isinstance(sequence, dict):
            # The authoritative latest numeric packet already contains this
            # same partial OHLCV row; remove only the map duplicate.
            sequence.pop("current_partial_bar", None)
            sequence["confirmed_swings"] = sequence.get("confirmed_swings", [])[-4:]
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    # The latest packet already retains native economics and the rendered
    # chart retains the wider path. Keep the causal comparison primitives but
    # remove only their duplicated long-form representations.
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        range_reference = instrument.pop("range_reference", None)
        if isinstance(range_reference, dict):
            range_reference.pop("bars", None)
            instrument["range_60"] = range_reference
        sequence = instrument.get("price_sequence")
        if isinstance(sequence, dict):
            sequence["confirmed_swings"] = sequence.get("confirmed_swings", [])[-3:]
            sequence["legs"] = sequence.get("legs", [])[-2:]
        levels = instrument.get("nearest_measured_levels")
        if isinstance(levels, list):
            for level in levels:
                if isinstance(level, dict):
                    level["sources"] = level.get("sources", [])[:2]
        vwap = instrument.get("vwap_path")
        if isinstance(vwap, dict):
            vwap.pop("current_bands", None)
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    value.pop("authority", None)
    value.pop("decision_authority", None)
    value.pop("effect", None)
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        instrument.pop("economics", None)
        auction = instrument.get("auction_evidence")
        if isinstance(auction, dict):
            auction.pop("balance_and_direction_are_separate_measurements", None)
        for level in instrument.get("nearest_measured_levels", []):
            if isinstance(level, dict):
                level["sources"] = level.get("sources", [])[:1]
        for zone in instrument.get("unfilled_three_bar_imbalances", []):
            if isinstance(zone, dict):
                zone.pop("formed_bar_id", None)
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    # Preserve the wider auction ladder and detailed near-level economics before
    # duplicated range/noise representations. The ladder carries the 60-bar
    # high, midpoint, and low, while the 60 window retains its width; overlap
    # already supplies a bounded chop measurement when reversal count is elided.
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        instrument.pop("range_60", None)
        tolerance = instrument.get("measurement_tolerance")
        if isinstance(tolerance, dict):
            tolerance.pop("ticks", None)
            tolerance.pop("recent_median_true_range_points", None)
        sequence = instrument.get("price_sequence")
        if isinstance(sequence, dict):
            for leg in sequence.get("legs", []):
                if isinstance(leg, dict):
                    leg.pop("ticks", None)
            for window in sequence.get("windows", {}).values():
                if isinstance(window, dict):
                    window.pop("close_direction_reversal_fraction", None)
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    for instrument in value.get("instruments", []):
        sequence = instrument.get("price_sequence") if isinstance(instrument, dict) else None
        if isinstance(sequence, dict):
            sequence.pop("current_same_direction_close_run", None)
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    # Compact OF/VWAP payloads once all three roots carry native flow.
    for instrument in value.get("instruments", []):
        if not isinstance(instrument, dict):
            continue
        flow = instrument.get("order_flow_response")
        if isinstance(flow, dict):
            instrument["order_flow_response"] = {
                key: flow[key] for key in (
                    "status", "coverage", "signed_delta_change_sum",
                    "price_change_points", "latest_aggression_balance", "reason",
                ) if key in flow
            }
        vwap = instrument.get("vwap_path")
        if isinstance(vwap, dict):
            instrument["vwap_path"] = {
                key: vwap[key] for key in (
                    "status", "coverage", "current_vwap",
                    "current_price_minus_vwap_points", "reason",
                ) if key in vwap
            }
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) <= MAX_SERIALIZED_CHARS:
        return
    # All semantics below are also stated in the prompt and concrete fields.
    # If unusually long native identifiers still exceed the hard text budget,
    # fail open to the authoritative packet instead of sending an oversized map.
    value.pop("measurement_contract", None)
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) > MAX_SERIALIZED_CHARS:
        raise ValueError("market_perception_text_budget_exceeded")


def build_market_perception(
    packet: dict[str, Any], exchange: Path, *,
    active_trade_state: dict[str, Any] | None = None,
    positioned_roots: Iterable[str] | None = None,
) -> tuple[dict[str, Any], Path | None]:
    """Build the bounded factual map and chart for one already-admitted cycle."""
    supervisor = exchange / "hermes" / "supervisor"
    state_path = supervisor / "market-perception-state.json"
    state = update_state_from_exchange(load_state(state_path), packet, exchange)
    save_state(state_path, state)
    roots = _ordered_roots(packet, positioned_roots)
    market_map: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_packet_id": packet.get("packet_id") or _packet_ceiling(packet),
        "nature": "deterministic_causal_measurements_evidence_not_permission",
        "authority": "numeric_native_packet_over_visual_context",
        "decision_authority": "hermes",
        "effect": "observation_only_no_execution_or_admission_effect",
        "measurement_contract": {
            "completed_bars": "native_last_completed_bar_only",
            "continuity": "observed_context_and_confirmed_references_retained_420_minutes;gaps_not_filled;local_windows_flow_and_imbalances_use_latest_consecutive_minutes;coverage_not_entry_permission",
            "live_bar": "partial_separate_not_relabelled_completed",
            "level_tolerance": "max(2_native_ticks,20pct_recent_median_true_range)_rounded_to_tick",
            "vwap_bands": "sigma_inferred_from_native_price_vwap_and_native_deviation_when_available",
            "missing": "unknown_and_neutral",
        },
        "auction_reference_ladder_contract": {
            "row_format": ["price", "signed_distance_points", "sources"],
        },
        "view": "position_management" if positioned_roots else "portfolio_scan",
        "instrument_order": roots,
        "instruments": [instrument_perception(root, state["instruments"][root]) for root in roots if root in state["instruments"]],
        "visual_context": {"status": "pending"},
    }
    _trim_to_budget(market_map)
    image_path: Path | None = None
    if roots:
        image_path = supervisor / "market-context-images" / f"{market_map['source_packet_id']}-{market_map['view']}.png"
        try:
            market_map["visual_context"] = render_market_context(state, market_map, image_path, active_trade_state)
        except Exception as error:
            image_path = None
            market_map["visual_context"] = {
                "status": "unavailable", "reason": f"render_failed:{type(error).__name__}",
                "semantics": "text_packet_remains_authoritative_and_decision_continues",
            }
    else:
        market_map["visual_context"] = {"status": "unavailable", "reason": "no_current_instruments"}
    _trim_to_budget(market_map)
    return market_map, image_path
