"""Read-only analytics-cache decoding. No trading decisions or execution imports."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone

STATE_VERSION = "glitch.jev.observation.v1"
INPUT_EPOCH = "live-partial-cache-v1"
MAX_BYTES = 512 * 1024
MAX_AGE_SECONDS = 15
PUBLISHERS = {"glitch_analytics_bridge", "glitch_ai_market_ingest"}
NUMERIC_FIELDS = (
    "Open High Low Volume CurrentPrice InstrumentPointValueUsd InstrumentTickSize "
    "AveragePrice Atr Adx Rsi StochK ZScore DiPlus DiMinus Cci MacdHistogram "
    "EmaAlignment OscillatorCompositeScore MaCompositeScore RawScore DirectionalScore "
    "TradeabilityScore OrderFlowCumulativeDelta OrderFlowDeltaChange OrderFlowVwap "
    "OrderFlowVwapDeviation OrderFlowAggressionBalance OrderFlowDepthImbalance "
    "SessionHigh SessionLow PreviousSessionHigh PreviousSessionLow"
).split()
INGEST_FIELDS = set((
    "Open High Low Volume CurrentPrice InstrumentPointValueUsd InstrumentTickSize "
    "AveragePrice Atr Adx Rsi EmaAlignment RawScore DirectionalScore TradeabilityScore "
    "SessionHigh SessionLow PreviousSessionHigh PreviousSessionLow"
).split())
DESCRIPTIVE_PATHS = (
    "location.session_open location.session_high location.session_low "
    "location.previous_session_high location.previous_session_low path.clv "
    "flow.cumulative_delta flow.delta_change flow.delta_velocity flow.delta_acceleration "
    "flow.price_velocity_points flow.price_impact_points_per_volume flow.price_flow_divergence "
    "flow.aggression_balance flow.depth_imbalance flow.quote_classified_volume "
    "flow.tick_rule_volume flow.ambiguous_volume flow.classification_coverage "
    "liquidity.best_bid liquidity.best_ask liquidity.spread_points liquidity.spread_ticks "
    "liquidity.last_quote_age_seconds liquidity.last_depth_age_seconds"
).split() + [f"path.{kind}.{m}" for kind in ("trend_efficiency", "realized_volatility_log_return_stddev")
           for m in (5, 15, 60)] + [f"path.signed_movement.{m}.{unit}"
                                   for m in (5, 15, 60) for unit in ("points", "ticks", "atr")]


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        match = re.fullmatch(r"/Date\((-?\d+)(?:[+-]\d{4})?\)/", value)
        if match:
            return int(match[1]) / 1000
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def number(value):
    return value if type(value) in (float, int) and math.isfinite(value) else None


def strict_json(raw, limit=MAX_BYTES):
    if len(raw) > limit:
        raise ValueError("size_limit")
    # Bound nesting before the JSON decoder allocates nested structures.
    depth, quoted, escaped = 0, False, False
    for ch in raw.decode("utf-8-sig"):
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "[{":
            depth += 1
            if depth > 24:
                raise ValueError("depth_limit")
        elif ch in "]}":
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def reject(_):
        raise ValueError("nonfinite_json")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def at(value, path):
    for key in path.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def age(value, now):
    parsed = timestamp(value)
    return None if parsed is None else round(now - parsed, 6)


def fresh(seconds, maximum=MAX_AGE_SECONDS):
    return seconds is not None and -1 <= seconds <= maximum


def decode_cache(raw, now):
    document = strict_json(raw)
    if not isinstance(document, dict) or not isinstance(document.get("Instruments"), list):
        raise ValueError("cache_shape")
    if not 1 <= len(document["Instruments"]) <= 16:
        raise ValueError("instrument_count")
    instruments = {}
    for feed in document["Instruments"]:
        if not isinstance(feed, dict):
            raise ValueError("feed_shape")
        contract, root = feed.get("InstrumentFullName"), feed.get("InstrumentRoot")
        if (not isinstance(contract, str) or not re.fullmatch(r"[A-Z0-9]{1,8} \d{2}-\d{2}", contract)
                or contract.split()[0] != root or contract in instruments):
            raise ValueError("contract_identity")
        readings = feed.get("Readings")
        if not isinstance(readings, list) or len(readings) > 8:
            raise ValueError("reading_count")
        frames, issues = {}, []
        for reading in readings:
            if not isinstance(reading, dict):
                raise ValueError("reading_shape")
            minutes = reading.get("Minutes")
            if type(minutes) is not int or minutes not in (1, 5, 15, 60) or str(minutes) in frames:
                raise ValueError("timeframe_identity")
            if reading.get("InstrumentFullName") != contract or reading.get("InstrumentRoot") != root:
                issues.append("mixed_contract")
            desc_raw = reading.get("DescriptiveStateJson")
            desc = strict_json(desc_raw.encode(), 24000) if isinstance(desc_raw, str) and desc_raw else {}
            if not isinstance(desc, dict):
                raise ValueError("descriptive_shape")
            if desc and (desc.get("schema_version") != "glitch.market.descriptive.v1"
                         or at(desc, "native_observations.instrument_full_name") != contract
                         or at(desc, "native_observations.instrument_root") != root):
                issues.append("descriptive_identity")
            source = at(desc, "heuristic_projections.source")
            source = source if source in ("glitch_analytics_bridge_legacy", "glitch_ai_market_ingest") else None
            publisher = reading.get("Publisher")
            publisher = publisher if publisher in PUBLISHERS else None
            # Legacy source is audit evidence, not a substitute for a publisher identity.
            quality = at(desc, "descriptive_state.quality") or {}
            asof = quality.get("as_of_utc") if isinstance(quality, dict) else None
            bar_time = at(desc, "native_observations.bar.utc_time")
            reading_time = reading.get("UtcTime")
            vals = {key: number(reading.get(key)) for key in NUMERIC_FIELDS}
            if publisher != "glitch_analytics_bridge" and source != "glitch_analytics_bridge_legacy":
                vals = {key: val if key in INGEST_FIELDS else None for key, val in vals.items()}
            completed = at(desc, "native_observations.last_completed_bar") or {}
            if not isinstance(completed, dict):
                raise ValueError("completed_bar_shape")
            completed = {key: completed.get(key) for key in ("utc_time", "closed_utc", "open", "high", "low", "close", "volume")}
            completed = {key: (val if timestamp(val) is not None else None) if key.endswith("utc") or key == "utc_time"
                         else number(val) for key, val in completed.items()}
            # Ingest's current bar UTC is the publication time; only its completed-bar boundary is native time.
            native_time = completed["closed_utc"] if publisher == "glitch_ai_market_ingest" or source == "glitch_ai_market_ingest" else bar_time
            descriptive = {key: at(desc.get("descriptive_state"), key) for key in DESCRIPTIVE_PATHS}
            descriptive = {key: val if type(val) is bool else number(val) for key, val in descriptive.items()}
            frame = {
                "publisher": publisher, "descriptive_source": source,
                "reading_utc": reading_time if timestamp(reading_time) is not None else None,
                "reading_age_seconds": age(reading_time, now),
                "descriptive_as_of_utc": asof if timestamp(asof) is not None else None,
                "descriptive_age_seconds": age(asof, now),
                "bar_utc": bar_time if timestamp(bar_time) is not None else None,
                "bar_age_seconds": age(bar_time, now),
                "native_boundary_age_seconds": age(native_time, now),
                "last_completed_bar": completed,
                "quality_status": {key: quality.get(key) if quality.get(key) in
                                   ("available", "unavailable", "warming", "stale_or_unavailable") else "unreported"
                                   for key in ("order_flow_status", "depth_status")} if isinstance(quality, dict) else {},
                "completeness": quality.get("bar_completeness") if isinstance(quality, dict)
                and quality.get("bar_completeness") in ("complete", "in_progress") else "unknown",
                "values": vals, "descriptive": descriptive,
                "available_fields": [key for key, value in vals.items() if value is not None],
            }
            frames[str(minutes)] = frame
            if not fresh(frame["reading_age_seconds"], max(15, minutes * 60 + 5)):
                issues.append(f"stale_frame_{minutes}")
            if publisher is None:
                issues.append(f"publisher_unreported_{minutes}")
            expected = {"glitch_analytics_bridge": "glitch_analytics_bridge_legacy",
                        "glitch_ai_market_ingest": "glitch_ai_market_ingest"}.get(publisher)
            if source and publisher and source != expected:
                issues.append("producer_mismatch")
            if desc:
                for raw_key, desc_key in (("InstrumentTickSize", "tick_size"), ("InstrumentPointValueUsd", "point_value_usd")):
                    if vals[raw_key] != number(at(desc, "native_observations.instrument_economics." + desc_key)):
                        issues.append("economics_mismatch")
        if set(frames) != {"1", "5", "15", "60"}:
            issues.append("missing_timeframes")
        primary = frames.get("1", {})
        if not fresh(primary.get("reading_age_seconds")):
            issues.append("stale_primary")
        if not fresh(primary.get("descriptive_age_seconds")):
            issues.append("stale_descriptive")
        # A publication heartbeat does not refresh the last native market bar.
        # NinjaTrader minute bars may carry the end-of-interval timestamp.
        if primary.get("native_boundary_age_seconds") is None or not -60 <= primary["native_boundary_age_seconds"] <= 75:
            issues.append("stale_native_bar")
        for key in ("CurrentPrice", "InstrumentTickSize", "InstrumentPointValueUsd"):
            if (primary.get("values", {}).get(key) or 0) <= 0:
                issues.append("missing_native_economics_or_price")
        if (frames.get("15", {}).get("values", {}).get("Atr") or 0) <= 0:
            issues.append("missing_atr15")
        instruments[contract] = {"contract": contract, "root": root, "frames": frames,
                                 "issues": sorted(set(issues)), "eligible": not issues}
    return instruments


def build_state(instruments, contract, observation_id, raw_hash, history=()):
    primary = instruments.get(contract)
    if not primary or not primary["eligible"]:
        raise ValueError("ineligible_primary")
    frame = primary["frames"]["1"]
    price, tick = frame["values"]["CurrentPrice"], frame["values"]["InstrumentTickSize"]
    atr15 = primary["frames"]["15"]["values"]["Atr"]
    reference = {
        "instrument": contract, "price": price, "tick_size": tick, "atr15": atr15,
        "neutral_bands_atr15": {str(h): max(4 * tick, .25 * atr15 * math.sqrt(h / 15)) / atr15
                                for h in (5, 15, 30, 60)},
        "barrier_distance_atr15": max(4 * tick, atr15) / atr15,
    }
    frames = {}
    for minutes, item in primary["frames"].items():
        vals, atr = item["values"], item["values"]["Atr"]
        frames[minutes] = dict(item, relations={
            f"price_minus_{key}_atr15": (price - vals[key]) / atr15 if vals[key] is not None else None
            for key in ("AveragePrice", "OrderFlowVwap", "SessionHigh", "SessionLow")
        })
        frames[minutes]["relations"]["range_atr"] = (
            (vals["High"] - vals["Low"]) / atr if atr and vals["High"] is not None
            and vals["Low"] is not None else None)
    return {
        "schema_version": STATE_VERSION, "input_epoch": INPUT_EPOCH,
        "observation_id": observation_id, "observation_hash": raw_hash,
        "reference": reference, "timeframes": frames,
        "quality": {"purpose": "shadow research only; no action",
                    "partial_bars": "live cache, not the completed historical training distribution",
                    "missing": "null means unavailable, never zero",
                    "heuristic_scores": "descriptive projections; no strategy or probability semantics"},
        "history": [row for row in history if row["contract"] == contract
                    and timestamp(row["source_utc"]) <= timestamp(frame["reading_utc"])][-12:],
        "cross_market": [{"contract": key, "eligible": item["eligible"], "issues": item["issues"],
                          "minute": {k: item.get("frames", {}).get("1", {}).get(k)
                                     for k in ("publisher", "reading_utc", "reading_age_seconds")},
                          "price": item.get("frames", {}).get("1", {}).get("values", {}).get("CurrentPrice")}
                         for key, item in sorted(instruments.items()) if key != contract],
    }
