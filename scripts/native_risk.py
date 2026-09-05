"""Pure arithmetic on original native protection receipts, shared by both loops."""

import math


def _number(fields, key, fallback=None):
    try:
        value = float(fields.get(key))
        return value if math.isfinite(value) else fallback
    except (TypeError, ValueError):
        return fallback


def initial_native_risk(entry_price, quantity, fields, point_value):
    if (
        isinstance(point_value, bool) or not isinstance(point_value, (int, float))
        or not math.isfinite(point_value) or point_value <= 0
    ):
        return [], None, "native_point_value_missing"
    if (
        isinstance(entry_price, bool) or not isinstance(entry_price, (int, float))
        or not math.isfinite(entry_price) or entry_price <= 0
        or isinstance(quantity, bool) or not isinstance(quantity, (int, float))
        or not math.isfinite(quantity) or quantity <= 0 or int(quantity) != quantity
    ):
        return [], None, "native_initial_fill_invalid"
    legs = []
    remaining = int(quantity)
    for index in range(1, 4):
        stop = _number(fields, f"sl{index}")
        raw_quantity = _number(fields, f"leg{index}_qty", 0)
        if raw_quantity < 0 or int(raw_quantity) != raw_quantity:
            return legs, None, "native_initial_protection_incomplete"
        leg_quantity = int(raw_quantity)
        if index == 1 and leg_quantity <= 0 and stop is not None:
            leg_quantity = remaining
        if stop is None or stop <= 0 or leg_quantity <= 0:
            continue
        leg_quantity = min(leg_quantity, remaining)
        risk_points = abs(float(entry_price) - stop)
        legs.append({
            "leg": index,
            "quantity": leg_quantity,
            "initial_stop_price": stop,
            "risk_points_per_contract": risk_points,
            "initial_native_risk_usd": risk_points * leg_quantity * point_value,
        })
        remaining -= leg_quantity
    if not legs or remaining != 0:
        return legs, None, "native_initial_protection_incomplete"
    return legs, sum(leg["initial_native_risk_usd"] for leg in legs), "complete"
