"""Deterministic session-structure observations for the direct Glitch cycle.

The model is stateless per cycle; Hermes session continuity cannot be trusted
(compaction can 429 or time out). This module is the artificial session memory:
it accumulates the one-minute bar ledger across cycles in a small state file,
derives labeled market-structure measurements from it, and returns a compact
observation block that is injected into CURRENT_CYCLE as evidence.

Everything here is a measurement, never a verdict. No function returns an
action, a size, a stop, or a target. Labels are provisional by design and the
block says so. If anything fails, the cycle proceeds without observations.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "glitch.market_structure.v1"
MAX_BARS = 420          # rolling ledger window (7 hours of 1m bars)
RANGE_BARS = 60         # rolling 60-minute range box
EDGE_BAND = 0.15        # fraction of box width treated as "at edge"
ACCEPT_CLOSES = 3       # consecutive 1m closes beyond box = accepted break
FAILED_LOOKBACK = 15    # bars to flag a failed break after excursion
REGIME_FLIP_CONFIRM = 3 # consecutive agreeing computations before label flips
FVG_LOOKBACK = 90       # bars scanned for unfilled gaps
LEVEL_TOUCH_TICKS = 12  # 3 points on MNQ (tick 0.25)
TICK = 0.25
MAX_SERIALIZED_CHARS = 2200


def _utc_minutes_ago(iso_utc: str, now: datetime) -> int:
    try:
        stamp = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return max(0, int((now - stamp).total_seconds() // 60))
    except ValueError:
        return 0


def load_state(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        if isinstance(state, dict) and state.get("schema_version") == SCHEMA_VERSION:
            return state
    except (OSError, ValueError):
        pass
    return {"schema_version": SCHEMA_VERSION, "bars": [], "regime": {}, "last_minute_id": None}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _mnq_instrument(packet: dict[str, Any]) -> dict[str, Any] | None:
    frames = packet.get("frames")
    if not isinstance(frames, list) or not frames:
        return None
    market = frames[-1].get("market_snapshot") if isinstance(frames[-1], dict) else None
    if not isinstance(market, dict):
        return None
    for instrument in market.get("instruments", []):
        if isinstance(instrument, dict) and str(
            instrument.get("instrument") or instrument.get("instrument_root")
        ) == "MNQ":
            return instrument
    return None


def _timeframe_bar(instrument: dict[str, Any], minutes: int) -> dict[str, Any] | None:
    for bar in instrument.get("timeframe_bars", []):
        if isinstance(bar, dict) and bar.get("minutes") == minutes:
            return bar
    return None


def update_bars(state: dict[str, Any], packet: dict[str, Any]) -> None:
    """Append every new completed-ish 1m bar from the packet's five frames."""
    frames = packet.get("frames")
    if not isinstance(frames, list):
        return
    known = {bar["id"] for bar in state["bars"]}
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        minute_id = frame.get("minute_id")
        market = frame.get("market_snapshot")
        if not minute_id or minute_id in known or not isinstance(market, dict):
            continue
        instrument = None
        for candidate in market.get("instruments", []):
            if isinstance(candidate, dict) and str(
                candidate.get("instrument") or candidate.get("instrument_root")
            ) == "MNQ":
                instrument = candidate
                break
        bar_1m = _timeframe_bar(instrument, 1) if instrument else None
        if not isinstance(bar_1m, dict):
            continue
        try:
            record = {
                "id": minute_id,
                "o": float(bar_1m["open"]),
                "h": float(bar_1m["high"]),
                "l": float(bar_1m["low"]),
                "c": float(bar_1m["close"]),
                "atr": float((bar_1m.get("indicators") or {}).get("atr") or 0.0),
            }
        except (KeyError, TypeError, ValueError):
            continue
        state["bars"].append(record)
        known.add(minute_id)
    state["bars"].sort(key=lambda bar: bar["id"])
    if len(state["bars"]) > MAX_BARS:
        state["bars"] = state["bars"][-MAX_BARS:]
    if state["bars"]:
        state["last_minute_id"] = state["bars"][-1]["id"]


def swing_pivots(bars: list[dict[str, Any]], atr_1m: float) -> list[dict[str, Any]]:
    """ATR-scaled zigzag over the ledger; returns labeled pivots, oldest first."""
    threshold = max(1.0 * atr_1m, 2.0)
    pivots: list[dict[str, Any]] = []
    if len(bars) < 3:
        return pivots
    direction = 0  # 1 seeking high, -1 seeking low
    extreme = bars[0]
    for bar in bars[1:]:
        if direction >= 0 and bar["h"] >= extreme["h"]:
            extreme = bar
            direction = 1
        elif direction <= 0 and bar["l"] <= extreme["l"]:
            extreme = bar
            direction = -1
        elif direction >= 0 and extreme["h"] - bar["l"] >= threshold:
            pivots.append({"kind": "high", "price": extreme["h"], "id": extreme["id"]})
            extreme = bar
            direction = -1
        elif direction <= 0 and bar["h"] - extreme["l"] >= threshold:
            pivots.append({"kind": "low", "price": extreme["l"], "id": extreme["id"]})
            extreme = bar
            direction = 1
    labeled: list[dict[str, Any]] = []
    last_high: float | None = None
    last_low: float | None = None
    for pivot in pivots:
        if pivot["kind"] == "high":
            label = "HH" if last_high is not None and pivot["price"] > last_high else "LH"
            last_high = pivot["price"]
        else:
            label = "HL" if last_low is not None and pivot["price"] > last_low else "LL"
            last_low = pivot["price"]
        labeled.append({"label": label, "price": pivot["price"], "id": pivot["id"]})
    return labeled


def structure_bias(labels: list[str]) -> str:
    recent = labels[-4:]
    if len(recent) < 2:
        return "mixed"
    ups = sum(1 for label in recent if label in ("HH", "HL"))
    downs = sum(1 for label in recent if label in ("LL", "LH"))
    if ups >= 3 and downs <= 1:
        return "up"
    if downs >= 3 and ups <= 1:
        return "down"
    return "mixed"


def range_box(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    window = bars[-RANGE_BARS:]
    if len(window) < 10:
        return None
    high = max(bar["h"] for bar in window)
    low = min(bar["l"] for bar in window)
    return {"high": high, "low": low, "mid": round((high + low) / 2, 2), "width": round(high - low, 2)}


def breakout_state(bars: list[dict[str, Any]], box: dict[str, Any]) -> str:
    if not bars or not box:
        return "unknown"
    # The box is computed over trailing bars, so the newest closes are compared
    # against the box formed by the bars before them.
    prior = bars[:-ACCEPT_CLOSES] if len(bars) > ACCEPT_CLOSES else bars
    window = prior[-RANGE_BARS:]
    if len(window) < 10:
        return "unknown"
    high = max(bar["h"] for bar in window)
    low = min(bar["l"] for bar in window)
    tail = bars[-ACCEPT_CLOSES:]
    closes = [bar["c"] for bar in tail]
    if all(close > high for close in closes):
        return "accepted_above"
    if all(close < low for close in closes):
        return "accepted_below"
    recent = bars[-FAILED_LOOKBACK:]
    poked_above = any(bar["h"] > high for bar in recent)
    poked_below = any(bar["l"] < low for bar in recent)
    last_close = closes[-1]
    band = max((high - low) * EDGE_BAND, 2.0)
    if poked_above and last_close < high:
        return "failed_break_high"
    if poked_below and last_close > low:
        return "failed_break_low"
    if last_close >= high - band:
        return "testing_high"
    if last_close <= low + band:
        return "testing_low"
    return "inside"


def regime_hypothesis(state: dict[str, Any], adx_60m: float, box: dict[str, Any] | None,
                      atr_60m: float, bias: str) -> dict[str, Any]:
    """Hysteresis-stabilized regime label; flips only after repeated agreement."""
    if box is None:
        raw = "unknown"
    elif adx_60m >= 25 and bias in ("up", "down"):
        raw = "directional_up" if bias == "up" else "directional_down"
    elif adx_60m < 20 and atr_60m > 0 and box["width"] <= 2.5 * atr_60m:
        raw = "range"
    else:
        raw = "transition"
    regime = state.setdefault("regime", {})
    current = regime.get("label", "unknown")
    if raw == current:
        regime["pending"] = None
        regime["pending_count"] = 0
        regime["stable_cycles"] = int(regime.get("stable_cycles", 0)) + 1
    elif raw == regime.get("pending"):
        regime["pending_count"] = int(regime.get("pending_count", 0)) + 1
        if regime["pending_count"] >= REGIME_FLIP_CONFIRM:
            regime.update({"label": raw, "pending": None, "pending_count": 0, "stable_cycles": 0})
    else:
        regime["pending"] = raw
        regime["pending_count"] = 1
    return {"label": regime.get("label", "unknown"), "raw": raw,
            "stable_cycles": int(regime.get("stable_cycles", 0))}


def fvg_zones(bars: list[dict[str, Any]], current_price: float) -> list[dict[str, Any]]:
    """Nearest unfilled three-bar imbalance zones from the 1m ledger."""
    window = bars[-FVG_LOOKBACK:]
    zones: list[dict[str, Any]] = []
    for index in range(2, len(window)):
        first, third = window[index - 2], window[index]
        if third["l"] > first["h"]:
            zones.append({"side": "bullish", "top": third["l"], "bottom": first["h"], "at": index})
        elif third["h"] < first["l"]:
            zones.append({"side": "bearish", "top": first["l"], "bottom": third["h"], "at": index})
    unfilled: list[dict[str, Any]] = []
    for zone in zones:
        filled = False
        for bar in window[zone["at"] + 1:]:
            if zone["side"] == "bullish" and bar["l"] <= zone["bottom"]:
                filled = True
                break
            if zone["side"] == "bearish" and bar["h"] >= zone["top"]:
                filled = True
                break
        if not filled:
            unfilled.append({
                "side": zone["side"],
                "top": round(zone["top"], 2),
                "bottom": round(zone["bottom"], 2),
                "distance": round(min(abs(current_price - zone["top"]),
                                      abs(current_price - zone["bottom"])), 2),
            })
    unfilled.sort(key=lambda zone: zone["distance"])
    return unfilled[:3]


def level_touches(bars: list[dict[str, Any]], price: float) -> int:
    tolerance = LEVEL_TOUCH_TICKS * TICK
    touches = 0
    inside = False
    for bar in bars:
        hit = bar["l"] - tolerance <= price <= bar["h"] + tolerance
        if hit and not inside:
            touches += 1
        inside = hit
    return touches


def recent_attempts(decisions_path: Path, outcomes_path: Path, current_price: float,
                    now: datetime) -> dict[str, Any]:
    """The agent's own recent completed trades and loss clusters near price.

    Reads glitch.hermes.trade_outcome.v1 records. A losing trade's
    planned_stop is where the idea died, so it anchors the near-price check.
    """
    outcomes: list[dict[str, Any]] = []
    try:
        with open(outcomes_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()[-40:]
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                outcomes.append(record)
    except OSError:
        pass
    trades: list[dict[str, Any]] = []
    losses_near = 0
    for record in outcomes[-12:]:
        action = str(record.get("action") or "")
        if action not in ("ENTER_LONG", "ENTER_SHORT"):
            continue
        side = "long" if action == "ENTER_LONG" else "short"
        realized = record.get("master_realized_pnl_usd")
        stop = record.get("planned_stop")
        target = record.get("planned_target")
        closed = str(record.get("exit_utc") or record.get("recorded_utc") or "")
        minutes = _utc_minutes_ago(closed, now) if closed else None
        trade = {
            "side": side,
            "stop": round(float(stop), 2) if isinstance(stop, (int, float)) else None,
            "target": round(float(target), 2) if isinstance(target, (int, float)) else None,
            "result_usd": round(float(realized), 2) if isinstance(realized, (int, float)) else None,
            "minutes_ago": minutes,
        }
        trades.append(trade)
        if (trade["result_usd"] is not None and trade["result_usd"] < 0
                and minutes is not None and minutes <= 45
                and isinstance(stop, (int, float))
                and abs(float(stop) - current_price) <= 25.0):
            losses_near += 1
    return {"last_trades": trades[-3:], "recent_losses_near_price": losses_near}


def build_observations(packet: dict[str, Any], state: dict[str, Any],
                       glitch_data: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    instrument = _mnq_instrument(packet)
    if instrument is None:
        return {"available": False, "reason": "mnq_instrument_missing"}
    update_bars(state, packet)
    bars = state["bars"]
    if len(bars) < 10:
        return {"available": False, "reason": "ledger_warming_up", "bars": len(bars)}

    current_price = float(instrument.get("current_price") or bars[-1]["c"])
    bar_1m = _timeframe_bar(instrument, 1) or {}
    bar_60m = _timeframe_bar(instrument, 60) or {}
    atr_1m = float((bar_1m.get("indicators") or {}).get("atr") or 0.0)
    atr_60m = float((bar_60m.get("indicators") or {}).get("atr") or 0.0)
    adx_60m = float((bar_60m.get("indicators") or {}).get("adx") or 0.0)

    pivots = swing_pivots(bars, atr_1m)
    labels = [pivot["label"] for pivot in pivots]
    bias = structure_bias(labels)
    box = range_box(bars)
    state_break = breakout_state(bars, box) if box else "unknown"
    regime = regime_hypothesis(state, adx_60m, box, atr_60m, bias)

    session = instrument.get("session") or {}
    key_levels = []
    for kind, price in (
        ("session_high", session.get("high")),
        ("session_low", session.get("low")),
        ("prev_session_high", session.get("previous_high")),
        ("prev_session_low", session.get("previous_low")),
        ("range_high", box["high"] if box else None),
        ("range_low", box["low"] if box else None),
        ("range_mid", box["mid"] if box else None),
    ):
        if isinstance(price, (int, float)) and price > 0:
            key_levels.append({
                "kind": kind,
                "price": round(float(price), 2),
                "distance": round(abs(current_price - float(price)), 2),
                "touches": level_touches(bars, float(price)),
            })
    if box and box["width"] > 0:
        for name, ratio in (("fib_382", 0.382), ("fib_500", 0.5), ("fib_618", 0.618)):
            key_levels.append({
                "kind": name,
                "price": round(box["low"] + box["width"] * ratio, 2),
                "distance": round(abs(current_price - (box["low"] + box["width"] * ratio)), 2),
            })
    key_levels.sort(key=lambda level: level["distance"])

    swings_out = [
        {"label": pivot["label"], "price": round(pivot["price"], 2),
         "minutes_ago": _utc_minutes_ago(_minute_id_to_iso(pivot["id"]), now)}
        for pivot in pivots[-6:]
    ]

    position_in_range = None
    at_edge = None
    if box and box["width"] > 0:
        position_in_range = round((current_price - box["low"]) / box["width"], 2)
        at_edge = position_in_range <= EDGE_BAND or position_in_range >= 1 - EDGE_BAND

    attempts = recent_attempts(
        glitch_data / "intents" / "decisions.jsonl",
        glitch_data / "intents" / "hermes-trade-outcomes.jsonl",
        current_price,
        now,
    )

    observations: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "available": True,
        "nature": "deterministic_measurements_provisional_labels_evidence_not_permission",
        "ledger_minutes": len(bars),
        "regime_60m": {
            "label": regime["label"],
            "raw": regime["raw"],
            "stable_cycles": regime["stable_cycles"],
            "adx_60m": round(adx_60m, 1),
            "range": box,
            "range_atr_ratio": round(box["width"] / atr_60m, 2) if box and atr_60m > 0 else None,
        },
        "location": {
            "position_in_range": position_in_range,
            "at_range_edge": at_edge,
            "breakout_state": state_break,
            "atr_1m": round(atr_1m, 2),
        },
        "swings_1m": swings_out,
        "structure_bias": bias,
        "fvg_zones": fvg_zones(bars, current_price),
        "key_levels": key_levels[:7],
        "own_recent_attempts": attempts,
    }
    serialized = json.dumps(observations, separators=(",", ":"))
    if len(serialized) > MAX_SERIALIZED_CHARS:
        observations["fvg_zones"] = observations["fvg_zones"][:1]
        observations["key_levels"] = observations["key_levels"][:4]
        observations["swings_1m"] = observations["swings_1m"][-4:]
    return observations


def _minute_id_to_iso(minute_id: str) -> str:
    # 20260731T0432Z -> 2026-07-31T04:32:00+00:00
    try:
        stamp = datetime.strptime(minute_id, "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)
        return stamp.isoformat()
    except ValueError:
        return ""


def build_market_structure_observations(packet: dict[str, Any], exchange: Path,
                                        glitch_data: Path) -> dict[str, Any]:
    """Entry point for the direct cycle. Never raises into the trading path."""
    state_path = exchange / "hermes" / "supervisor" / "market-structure-state.json"
    state = load_state(state_path)
    observations = build_observations(packet, state, glitch_data)
    save_state(state_path, state)
    return observations
