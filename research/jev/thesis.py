"""Causal authored-thesis study inputs and conditional minute-mark comparisons.

No action or runtime connection. Native terminal outcomes are arguments to the
evaluator only and cannot enter the explicitly allowlisted inference state.
"""
from __future__ import annotations

import math
import re
from learning import timestamp


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def ratio(a, b):
    return round(a/b, 5) if finite(a) and finite(b) and b > 0 else None


def mark_from_snapshot(snapshot, contract):
    available = timestamp(snapshot["created_utc"])
    inst = next((i for i in snapshot["instruments"] if i.get("instrument_full_name") == contract), None)
    if inst is None:
        raise ValueError("contract_unavailable")
    source = timestamp(inst["timestamp_utc"])
    price = inst.get("current_price")
    if not inst.get("is_fresh") or not 0 <= available-source <= 90 or not finite(price) or price <= 0:
        raise ValueError("stale_or_invalid_mark")
    frames = {int(f["minutes"]): f for f in inst.get("timeframe_bars", [])}
    envelope = inst.get("descriptive_state") or {}
    ds = envelope.get("descriptive_state") or {}
    quality = ds.get("quality", {})
    ds_source = timestamp(quality["as_of_utc"]) if quality.get("as_of_utc") else None
    embedded = (envelope.get("native_observations") or {}).get("instrument_full_name")
    if embedded not in (None, contract):
        raise ValueError("embedded_contract_mismatch")
    ds_fresh = ds_source is not None and 0 <= available-ds_source <= 90
    frame_state = {}
    for h, f in frames.items():
        if h not in (1, 5, 15, 60):
            continue
        ind = f.get("indicators", {});atr = ind.get("atr")
        age = available-timestamp(f["utc_time"]) if f.get("utc_time") else None
        fresh = age is not None and 0 <= age <= h*60+90
        frame_envelope = f.get("descriptive_state") or {}
        frame_ds = frame_envelope.get("descriptive_state") or {}
        if (frame_envelope.get("native_observations") or {}).get("instrument_full_name") not in (None, contract):
            fresh = False
        details = {"age_seconds": age, "completeness": (frame_ds.get("quality") or {}).get("bar_completeness", "unknown")}
        for k in ("atr", "adx", "rsi", "di_plus", "di_minus", "macd_histogram"):
            details[k] = ind.get(k) if fresh and finite(ind.get(k)) else None
        average = ind.get("average_price")
        details["price_to_mean_atr"] = ratio(price-average, atr) if fresh and finite(average) else None
        frame_state[str(h)] = details
    flow_available = ds_fresh and quality.get("order_flow_status") == "available"
    flow = {k: ds.get("flow", {}).get(k) if flow_available and finite(ds.get("flow", {}).get(k)) else None
            for k in ("cumulative_delta", "delta_change", "delta_velocity", "delta_acceleration", "aggression_balance", "classification_coverage", "price_velocity_points", "price_flow_divergence")}
    ind1 = frames.get(1, {}).get("indicators", {})
    vwap = ind1.get("order_flow_vwap") if flow_available else None
    if not finite(vwap) or vwap <= 0:
        vwap = None
    flow["vwap"] = vwap
    flow["price_minus_vwap_points"] = price-vwap if vwap is not None else None
    path = ds.get("path", {}) if ds_fresh else {}
    movement = {str(h): path.get("signed_movement", {}).get(str(h), {}).get("points") for h in (5, 15, 60)}
    movement = {k: v if finite(v) else None for k, v in movement.items()}
    efficiency = {str(h): path.get("trend_efficiency", {}).get(str(h)) for h in (5, 15, 60)}
    efficiency = {k: v if finite(v) and 0 <= v <= 1 else None for k, v in efficiency.items()}
    return {"contract": contract, "source": source, "available": available, "price": price,
            "snapshot_id": snapshot["snapshot_id"], "frames": frame_state, "flow": flow,
            "movement_points": movement, "efficiency": efficiency,
            "quality": {"price_age_seconds": available-source, "descriptive_age_seconds": available-ds_source if ds_source else None,
                        "descriptive_fresh": ds_fresh, "flow_available": flow_available, "depth": "not_used",
                        "sampling": "minute_publications_not_subminute_tape"}}


def clean_thesis(text, limit=1800):
    # Authored text is the only free-text input; remove operational identifiers.
    text = re.sub(r"\bSIM\d+\b|\bGL1-[A-Z0-9-]+\b|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "[ID_REMOVED]", str(text or ""), flags=re.I)
    return text[:limit]


def build_state(trade, current, history, with_thesis=True):
    if current["contract"] != trade["symbol"]:
        raise ValueError("position_contract_mismatch")
    entry_time = timestamp(trade["entry"])
    if not entry_time < current["source"] <= current["available"]:
        raise ValueError("observation_before_entry")
    sign = 1 if trade["side"] == "Long" else -1 if trade["side"] == "Short" else None
    if sign is None or not finite(trade["entry_price"]):
        raise ValueError("invalid_position")
    earlier = sorted((m for m in history if m["contract"] == current["contract"]
                      and entry_time < m["source"] <= current["source"] and m["available"] <= current["available"]), key=lambda m: m["available"])
    e, p = trade["entry_price"], current["price"]
    stop, target = trade.get("planned_stop"), trade.get("planned_target")
    risk = abs(e-stop) if finite(stop) else None
    atr1 = current["frames"].get("1", {}).get("atr")
    favorable = sign*(p-e)
    peak = max([0, favorable]+[sign*(m["price"]-e) for m in earlier])
    state = {"schema": "glitch.jev.thesis_replay.v1", "instrument": trade["symbol"],
             "position": {"side": trade["side"], "entry_price": e, "elapsed_seconds": current["available"]-entry_time,
                          "original_stop": stop if finite(stop) else None, "original_target": target if finite(target) else None,
                          "geometry_source": "original_authored_geometry_not_current_working_orders",
                          "risk_points": risk, "current_favorable_points": favorable,
                          "sampled_peak_favorable_points_lower_bound": peak,
                          "sampled_giveback_points": peak-favorable,
                          "distance_to_original_invalidation_points": sign*(p-stop) if finite(stop) else None,
                          "remaining_original_objective_points": sign*(target-p) if finite(target) else None,
                          "movement_in_atr1": ratio(favorable, atr1), "original_risk_in_atr1": ratio(risk, atr1)},
             "market": {k: current[k] for k in ("price", "frames", "flow", "movement_points", "efficiency", "quality")},
             "recent_marks": [{"seconds_before_current_publication": current["available"]-m["available"],
                               "source_age_at_publication": m["available"]-m["source"], "price": m["price"],
                               "delta_change": m["flow"].get("delta_change"), "vwap": m["flow"].get("vwap")} for m in earlier[-10:]],
             "authored_thesis": {"entry_reason": clean_thesis(trade.get("authored_entry_reason")),
                                  "disconfirming_evidence": clean_thesis(trade.get("authored_disconfirming_evidence"))} if with_thesis else None}
    return state


def choice(record, question, names):
    if record.get("status") != "ok" or record.get("returned_model") != "jev-1.13.0":
        return None
    answer = record.get("response", {}).get("answers", {}).get(question, {})
    if answer.get("type") != "choice":
        return None
    ps = answer.get("probabilities", {})
    if set(ps) != set(names) or any(not finite(v) or not 0 <= v <= 1 for v in ps.values()):
        return None
    total = sum(ps.values())
    if total <= 0 or abs(total-1) > len(ps)*.005+1e-9:
        return None
    if abs(total-1) > 1e-9 and any(abs(v*100-round(v*100)) > 1e-8 for v in ps.values()):
        return None
    if answer.get("choice") not in ps or ps[answer["choice"]] < max(ps.values()):
        return None
    return {k: v/total for k, v in ps.items()}


def first_signal(rows, mode="persistent"):
    if mode not in ("persistent", "failed"):
        raise ValueError("unknown_probe_mode")
    previous = None
    for row in sorted(rows, key=lambda r: r["mark"]["available"]):
        ps = choice(row.get("response", {}), "thesis_state", ("HELD", "DETERIORATING", "FAILED", "UNKNOWN"))
        mark = row["mark"]
        hot = ps is not None and (ps["FAILED"] if mode == "failed" else ps["FAILED"]+ps["DETERIORATING"]) >= .7
        if not hot:
            previous = None
            continue
        if mode == "failed" or (previous and 0 < mark["available"]-previous["mark"]["available"] <= 120
                                and math.floor(mark["available"]/60)-math.floor(previous["mark"]["available"]/60) == 1
                                and mark["source"] > previous["mark"]["source"]):
            return row
        previous = row
    return None


def exit_probe(trade, signal, marks, slippage_spread_ticks=1.5, commission=.55):
    if any(not finite(x) or x < 0 for x in (slippage_spread_ticks, commission)):
        raise ValueError("invalid_probe_cost")
    if signal is None:
        return {"status": "no_signal"}
    delay = signal["response"].get("latency_ms")
    if not finite(delay) or delay < 0:
        return {"status": "invalid_latency"}
    ready = signal["mark"]["available"]+delay/1000
    end = timestamp(trade["exit"])
    future = [m for m in marks if m["contract"] == trade["symbol"] and ready <= m["source"] <= m["available"] < end]
    fill = min(future, key=lambda m: m["available"]) if future else None
    result = {"status": "conditional_mark_probe" if fill else "no_post_response_mark_before_native_exit",
              "signal_available": ready, "seconds_to_native_terminal": end-ready}
    if fill:
        root = trade["symbol"].split()[0];point = {"MES":5,"MNQ":2,"M2K":5}[root];tick={"MES":.25,"MNQ":.25,"M2K":.1}[root]
        sign = 1 if trade["side"] == "Long" else -1;qty=trade["quantity"]
        gross = sign*(fill["price"]-trade["entry_price"])*qty*point
        cost = qty*(commission+slippage_spread_ticks*tick*point)
        result.update(fill_source=fill["source"],fill_available=fill["available"],fill_price=fill["price"],
                      hypothetical_gross=gross,original_terminal_gross=trade["gross"],
                      gross_advantage=gross-trade["gross"],extra_exit_cost=cost,
                      cost_penalized_advantage=gross-trade["gross"]-cost)
    return result
