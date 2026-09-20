"""Offline outcome measurements. No provider, Hermes, native actions or runtime writes.

Inputs are explicit same-contract observations and completed minute bars. Incomplete
paths retain observed excursion bounds; they never manufacture first-touch ordering.
These labels are research evidence, not GL-AI-10 native trade outcomes.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections import defaultdict

HORIZONS = (5, 15, 30, 60)
CLASSES = ("UP", "DOWN", "FLAT")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_anchor(anchor):
    if not isinstance(anchor.get("contract"), str) or not anchor["contract"]:
        raise ValueError("contract_required")
    for key in ("source_time", "available_time", "price", "atr15", "tick", "point_value"):
        if not finite(anchor.get(key)):
            raise ValueError("invalid_anchor_" + key)
    if anchor["available_time"] < anchor["source_time"]:
        raise ValueError("anchor_not_yet_available")
    if min(anchor[k] for k in ("price", "atr15", "tick", "point_value")) <= 0:
        raise ValueError("invalid_economics")


class Timeline:
    """Retain first-published values; flag conflicting observations instead of choosing."""

    def __init__(self, marks=(), bars=()):
        self.marks, self.bars, self.conflicts = {}, {}, {}
        for kind, rows, fields in (("mark", marks, ("price",)),
                                   ("bar", bars, ("start", "open", "high", "low", "close"))):
            records = {}
            for row in rows:
                if not isinstance(row.get("contract"), str):
                    continue
                if not all(finite(row.get(k)) for k in ("time", "available_time", *fields)):
                    continue
                if row["available_time"] < row["time"] or not row.get("valid", False):
                    continue
                if kind == "bar" and (row["time"] - row["start"] != 60
                                      or row["low"] > min(row["open"], row["close"])
                                      or row["high"] < max(row["open"], row["close"])):
                    continue
                key = (row["contract"], row["time"])
                old = records.get(key)
                if old and any(old[k] != row[k] for k in fields):
                    conflict = (kind, *key)
                    known = max(old["available_time"], row["available_time"])
                    self.conflicts[conflict] = min(self.conflicts.get(conflict, math.inf), known)
                if old is None or row["available_time"] < old["available_time"]:
                    records[key] = row
            dest = self.marks if kind == "mark" else self.bars
            for (contract, ts), row in records.items():
                dest.setdefault(contract, []).append(row)
            for rows in dest.values():
                rows.sort(key=lambda r: r["time"])

    def window(self, kind, contract, start, end, as_of):
        rows = (self.marks if kind == "mark" else self.bars).get(contract, [])
        begin = bisect_left(rows, start, key=lambda r: r["time"])
        stop = bisect_left(rows, end + 1e-6, key=lambda r: r["time"])
        return [r for r in rows[begin:stop] if r["available_time"] <= as_of
                and self.conflicts.get((kind, contract, r["time"]), math.inf) > as_of]


def label_path(anchor, timeline, horizon, as_of, endpoint_tolerance=15):
    validate_anchor(anchor)
    if horizon not in HORIZONS or not finite(as_of) or not 0 <= endpoint_tolerance <= 60:
        raise ValueError("invalid_label_parameters")
    start, price = anchor["source_time"], anchor["price"]
    end = start + horizon * 60
    base = {"horizon_minutes": horizon, "contract": anchor["contract"],
            "target_time": end, "as_of": as_of}
    if as_of < end:
        return dict(base, status="PENDING")
    future = timeline.window("mark", anchor["contract"], start + 1e-6,
                             end + endpoint_tolerance, as_of)
    endpoint = next((r for r in future if end <= r["time"] <= end + endpoint_tolerance), None)
    bars = [r for r in timeline.window("bar", anchor["contract"], start + 1e-6, end, as_of)
            if r["start"] >= start]
    complete = (len(bars) == horizon and bars[0]["start"] == start and bars[-1]["time"] == end
                and all(a["time"] == b["start"] for a, b in zip(bars, bars[1:])))
    # Exact completed-bar close outranks a later sampled mark, with its source explicit.
    if complete:
        endpoint = dict(bars[-1], price=bars[-1]["close"])
    if endpoint is None:
        return dict(base, status="PENDING" if as_of < end + endpoint_tolerance else "MISSING_ENDPOINT")
    band = max(4 * anchor["tick"], .25 * anchor["atr15"] * math.sqrt(horizon / 15))
    barrier = max(4 * anchor["tick"], anchor["atr15"])
    delta = endpoint["price"] - price
    marks_in_path = [r for r in future if r["time"] <= end]
    high = max([price] + [r["price"] for r in marks_in_path] + [r["high"] for r in bars])
    low = min([price] + [r["price"] for r in marks_in_path] + [r["low"] for r in bars])
    first, first_time = "UNRESOLVED", None
    if complete:
        first = "NEITHER"
        for bar in bars:
            up, down = bar["high"] >= price + barrier, bar["low"] <= price - barrier
            if up or down:
                first = "UNRESOLVED" if up and down else "UPPER_FIRST" if up else "LOWER_FIRST"
                first_time = bar["time"]
                break
    path_prices = [price] + ([b["close"] for b in bars] if complete else [r["price"] for r in marks_in_path])
    travel = sum(abs(b - a) for a, b in zip(path_prices, path_prices[1:]))
    return dict(base, status="OK", label="UP" if delta > band else "DOWN" if delta < -band else "FLAT",
                net_points=delta, neutral_band_points=band, endpoint_time=endpoint["time"],
                endpoint_delay_seconds=endpoint["time"] - end,
                endpoint_source="completed_minute_close" if complete else "first_available_mark_at_or_after_target",
                observed_up_excursion_points=high - price, observed_down_excursion_points=price - low,
                excursion_quality="complete_minute_ohlc" if complete else "sampled_lower_bounds",
                first_excursion=first, first_excursion_bar_close=first_time,
                first_excursion_time_precision="minute_interval" if first_time is not None else None,
                minute_path_efficiency=abs(bars[-1]["close"] - price) / travel if complete and travel else (0 if complete else None),
                sampled_mark_count=len(marks_in_path), completed_minute_count=len(bars))


def economic_probe(anchor, timeline, label, inference_ready, side, commission=.55,
                   spread_ticks=1, slippage_ticks=1):
    """One isolated hypothetical round trip, entered only after inference exists."""
    validate_anchor(anchor)
    if type(side) is not int or side not in (-1, 1) or not finite(inference_ready):
        raise ValueError("invalid_probe")
    if any(not finite(x) or x < 0 for x in (commission, spread_ticks, slippage_ticks)):
        raise ValueError("invalid_cost")
    if label.get("status") != "OK":
        return {"status": "UNRESOLVED"}
    if label.get("contract") != anchor["contract"]:
        raise ValueError("probe_contract_mismatch")
    earliest = max(inference_ready, anchor["available_time"])
    marks = timeline.window("mark", anchor["contract"], earliest, label["endpoint_time"], label["as_of"])
    if not marks or marks[0]["time"] >= label["endpoint_time"]:
        return {"status": "NO_POST_INFERENCE_ENTRY_MARK"}
    entry = marks[0]
    gross = side * (anchor["price"] + label["net_points"] - entry["price"]) * anchor["point_value"]
    cost = 2 * commission + (spread_ticks + 2 * slippage_ticks) * anchor["tick"] * anchor["point_value"]
    return {"status": "HYPOTHETICAL", "side": side, "entry_source_time": entry["time"],
            "entry_price": entry["price"], "gross_usd": gross, "cost_usd": cost,
            "net_usd": gross - cost, "cost_assumptions": {"commission_per_side": commission,
            "spread_ticks_round_trip": spread_ticks, "slippage_ticks_per_side": slippage_ticks},
            "quantity": 1, "scope": "isolated_probe_not_native_fill_or_portfolio"}


def probability_metrics(rows):
    """Rows contain an observed label and an explicitly keyed Choice distribution."""
    bins, result = defaultdict(list), {"n": 0, "brier": 0., "log_loss": 0., "correct": 0}
    recalls, high = defaultdict(list), []
    for row in rows:
        p = row["probabilities"]
        if set(p) != set(CLASSES) or any(not finite(v) or not 0 <= v <= 1 for v in p.values()):
            raise ValueError("invalid_probabilities")
        if abs(sum(p.values()) - 1) > 1e-6 or row["label"] not in CLASSES:
            raise ValueError("unresolved_distribution_or_label")
        win = max(CLASSES, key=lambda k: p[k]);conf = p[win];correct = win == row["label"]
        result["n"] += 1
        result["brier"] += sum((p[k] - (k == row["label"])) ** 2 for k in CLASSES)
        result["log_loss"] -= math.log(max(p[row["label"]], 1e-6))
        result["correct"] += correct
        bins[min(9, int(conf * 10))].append((conf, correct))
        recalls[row["label"]].append(correct)
        if conf >= .7:
            high.append(correct)
    if not result["n"]:
        return {"n": 0}
    n = result["n"]
    curve = [{"lower": k / 10, "n": len(v), "confidence": sum(x[0] for x in v) / len(v),
              "accuracy": sum(x[1] for x in v) / len(v)} for k, v in sorted(bins.items())]
    return {"n": n, "brier": result["brier"] / n, "log_loss": result["log_loss"] / n,
            "accuracy": result["correct"] / n,
            "balanced_accuracy": sum(sum(v) / len(v) for v in recalls.values()) / len(recalls),
            "ece": sum(b["n"] / n * abs(b["confidence"] - b["accuracy"]) for b in curve),
            "high_confidence_coverage": len(high) / n,
            "high_confidence_accuracy": sum(high) / len(high) if high else None,
            "calibration_curve": curve}
