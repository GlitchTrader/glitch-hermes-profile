"""Read recorder evidence and write a NEW external research report; never mutate input."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from jev_observation import decode_cache, digest, strict_json, timestamp
from score_observations import HORIZONS, Timeline, economic_probe, label_path, probability_metrics


def collect(root, as_of):
    if json.loads((root / "observer.json").read_text())["owner"] != "glitch.jev.shadow.v1":
        raise ValueError("not_observer_evidence")
    observations, requests, predictions, marks, bars = {}, {}, [], [], []
    source_high_water, prediction_ids = {}, set()
    counts, issues, inputs = Counter(), Counter(), []
    for path in sorted(root.glob("evidence-*.jsonl")):
        hasher = hashlib.sha256();read_bytes = 0
        with path.open("rb") as stream:
            while line := stream.readline(2 * 1024 * 1024 + 1):
                if len(line) > 2 * 1024 * 1024:
                    raise ValueError("record_size")
                if not line.endswith(b"\n"):
                    issues["unfinished_tail"] += 1
                    break
                hasher.update(line);read_bytes += len(line)
                row = strict_json(line, 2 * 1024 * 1024)
                published = timestamp(row.get("recorded_utc"))
                if published is None or published > as_of:
                    continue
                if row.get("influenced") is not False and not (
                    row.get("influenced") is None and row.get("authority") == "hermes_evidence_sim"
                    and row.get("kind") in ("request", "prediction")
                ):
                    raise ValueError("unexpected_influenced_record")
                kind = row.get("kind");counts[kind] += 1
                if kind == "observation":
                    raw = base64.b64decode(row["raw_cache_base64"], validate=True)
                    if digest(raw) != row["raw_hash"]:
                        raise ValueError("observation_hash")
                    available = timestamp(row["read_end_utc"])
                    # Reconstruct from raw native bytes using publication-time freshness.
                    try:
                        instruments = decode_cache(raw, available)
                    except (ValueError, TypeError):
                        issues["invalid_cache"] += 1
                        continue
                    observations[row["observation_id"]] = {"raw_hash": row["raw_hash"], "available": available,
                                                         "instruments": instruments}
                    for contract, inst in instruments.items():
                        source = timestamp(inst.get("frames", {}).get("1", {}).get("reading_utc"))
                        if source is not None:
                            if source < source_high_water.get(contract, source):
                                inst["issues"].append("source_time_regression")
                                inst["eligible"] = False
                            source_high_water[contract] = max(source, source_high_water.get(contract, source))
                        issues.update(inst["issues"])
                        if not inst["eligible"]:
                            continue
                        frame = inst["frames"]["1"];source = timestamp(frame["reading_utc"])
                        marks.append({"contract": contract, "time": source, "available_time": available,
                                      "price": frame["values"]["CurrentPrice"], "valid": True})
                        # Minute bars are stamped at their END. Both producers set
                        # utc_time=Times[bip][1], but closed_utc=Times[bip][0] (next bar).
                        # Do not shift the prior bar's OHLC into the following interval.
                        b = frame["last_completed_bar"];bar_end = timestamp(b.get("utc_time"))
                        if bar_end is not None:
                            bars.append({"contract": contract, "start": bar_end - 60, "time": bar_end,
                                         "available_time": available, "valid": True,
                                         **{k: b.get(k) for k in ("open", "high", "low", "close")}})
                elif kind == "request":
                    if digest(row["state"]) != row["state_hash"]:
                        raise ValueError("request_state_hash")
                    if row["request_id"] in requests:
                        raise ValueError("duplicate_request_identity")
                    requests[row["request_id"]] = row
                elif kind == "prediction":
                    if row["request_id"] in prediction_ids:
                        raise ValueError("duplicate_prediction_identity")
                    prediction_ids.add(row["request_id"])
                    predictions.append(row)
        inputs.append({"file": path.name, "consumed_complete_bytes": read_bytes, "sha256": hasher.hexdigest()})
    return observations, requests, predictions, Timeline(marks, bars), counts, issues, inputs


def evaluate(root, as_of):
    observations, requests, predictions, timeline, counts, issues, inputs = collect(root, as_of)
    outcomes, metric_rows, excluded = [], defaultdict(list), Counter()
    for pred in predictions:
        req = requests.get(pred.get("request_id"))
        if (not req or not pred.get("eligible_for_research_scoring") or pred.get("status") != "ok"
                or pred.get("expired") is not False or pred.get("superseded") is not False
                or pred.get("input_stale_or_invalid") is not False):
            excluded["missing_request_or_ineligible_prediction"] += 1
            continue
        obs = observations.get(req["observation_id"])
        if (not obs or req["observation_hash"] != obs["raw_hash"]
                or pred["observation_hash"] != obs["raw_hash"]
                or pred.get("requested_model") != "jev-1.13.0"
                or pred.get("returned_model") != "jev-1.13.0"
                or pred.get("provider") != req.get("provider")
                or pred.get("provider") != "typesafe-direct"
                or pred.get("state_hash") != req.get("state_hash")
                or pred.get("observation_id") != req.get("observation_id")
                or pred.get("question_hash") != req.get("question_hash")):
            excluded["identity_mismatch"] += 1
            continue
        ref = req["state"]["reference"];contract = ref["instrument"]
        inst = obs["instruments"].get(contract)
        if not inst or not inst["eligible"]:
            excluded["ineligible_anchor"] += 1
            continue
        frame = inst["frames"]["1"]
        if (ref["atr15"] != inst["frames"]["15"]["values"]["Atr"]
                or ref["price"] != frame["values"]["CurrentPrice"]
                or ref["tick_size"] != frame["values"]["InstrumentTickSize"]
                or req["state"]["observation_id"] != req["observation_id"]
                or req["state"]["observation_hash"] != obs["raw_hash"]):
            excluded["anchor_scale_mismatch"] += 1
            continue
        anchor = {"contract": contract, "source_time": timestamp(frame["reading_utc"]),
                  "available_time": obs["available"], "price": frame["values"]["CurrentPrice"],
                  "tick": frame["values"]["InstrumentTickSize"], "atr15": ref["atr15"],
                  "point_value": frame["values"]["InstrumentPointValueUsd"]}
        for horizon in HORIZONS:
            if f"endpoint_{horizon}m" not in pred.get("probabilities_for_scoring", {}):
                continue  # Different frozen bundles need not ask every legacy horizon.
            label = label_path(anchor, timeline, horizon, as_of)
            result = {"observation_id": req["observation_id"], "request_id": req["request_id"],
                      "provider": pred["provider"], "requested_model": pred["requested_model"],
                      "returned_model": pred["returned_model"], "question_hash": pred["question_hash"],
                      "state_hash": req["state_hash"], "input_epoch": req["state"]["input_epoch"],
                      "label": label, "influenced": pred.get("influenced"),
                      "authority": pred.get("authority", "shadow_only")}
            if label["status"] == "OK":
                p = pred["probabilities_for_scoring"][f"endpoint_{horizon}m"]
                row = {"label": label["label"], "probabilities": p}
                epoch = "|".join([pred["provider"], pred["returned_model"], pred["question_hash"],
                                  req["state"]["input_epoch"], str(horizon)])
                metric_rows[epoch].append(row)
                if label["endpoint_delay_seconds"] == 0:
                    metric_rows[epoch + "|exact_endpoint"].append(row)
                result["economic_probes"] = {str(side): economic_probe(anchor, timeline, label,
                                              timestamp(pred["end_utc"]), side) for side in (-1, 1)}
            outcomes.append(result)
    report = {"schema": "glitch.jev.offline_scoring.v1", "as_of": as_of, "input_files": inputs,
              "records": dict(counts), "input_issues": dict(issues), "excluded_predictions": dict(excluded),
              "conflicting_timeline_records": len(timeline.conflicts),
              "outcome_status": dict(Counter(x["label"]["status"] for x in outcomes)),
              "metrics_by_frozen_epoch": {k: probability_metrics(v) for k, v in metric_rows.items()},
              "prediction_authorities": dict(Counter(x.get("authority", "shadow_only") for x in outcomes)),
              "limitations": ["15s endpoint tolerance is reported; exact endpoints scored separately.",
                              "This report has no runtime effect. SIM advisory predictions may have been consumed; join Hermes contexts/attempts by request ID. Prompt inclusion does not establish final-choice causality.",
                              "Incomplete minute paths cannot prove first touch, exact excursions or missed barriers.",
                              "No wake or management policy exists here; avoided losses and opportunity cost remain unmeasured.",
                              "Observed time is native publication, not a quote-by-quote execution tape.",
                              "Probabilities remain evidence; hypothetical two-sided probes are not portfolio PnL."],
              "influenced": False}
    return report, outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--as-of", type=float, default=None)
    args = parser.parse_args();source = args.evidence.resolve();target = args.report.resolve()
    if source == target or source in target.parents or any(p.lower() == "glitchdata" for p in target.parts):
        raise ValueError("report_must_be_outside_runtime_evidence")
    if target.exists() or target.with_suffix(".outcomes.jsonl").exists():
        raise ValueError("report_already_exists")
    report, outcomes = evaluate(source, args.as_of if args.as_of is not None else time.time())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False);stream.write("\n")
    with target.with_suffix(".outcomes.jsonl").open("x", encoding="utf-8") as stream:
        for row in outcomes:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    print(json.dumps({"report": str(target), "records": report["records"], "outcomes": len(outcomes)}))


if __name__ == "__main__":
    main()
