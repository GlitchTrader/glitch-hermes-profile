"""Reconcile completed master/follower trades into Hermes learning outcomes.

The direct exchange outbox is the decision authority. NinjaTrader execution
events prove the AI-owned master lifecycle; CopyEngine Journal events or
NinjaTrader's durable daily order log can prove follower-native protection;
intent-bound native fill receipts prove the master round trip. TradeLedger.tsv
supplies derived follower round trips and master diagnostics. A complete native
master trade is always attributable to Hermes. Missing follower evidence is
unknown, not failure, and never erases master learning.
"""

import argparse
import bisect
import hashlib
import json
import math
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


DOTNET_EPOCH_TICKS = 621355968000000000
NATIVE_LOG_QUANTITY_PATTERN = re.compile(r"(?:^|\s)Quantity=(?P<quantity>\d+(?:\.\d+)?)")
COPY_ENTRY_SIGNAL_PATTERN = re.compile(
    r"^GLT-COPY-E-[^-]+-(?P<correlation>[^-]+)-",
    re.IGNORECASE,
)
COPY_PROTECTION_SIGNAL_PATTERN = re.compile(
    r"^GLT-COPY-(?P<role>[ST])-[^-]+-(?P<correlation>[^-]+)-",
    re.IGNORECASE,
)
NATIVE_PROTECTION_STATES = {"accepted", "working", "partially filled", "filled"}
NATIVE_PROTECTION_WINDOW_SECONDS = 5
MASTER_TERMINAL_CODES = {
    "master_exit_fill_observed": "managed_exit",
    "master_stop_exit_fill_observed": "stop",
    "master_target_exit_fill_observed": "target",
}
NATIVE_OUTCOME_TIME_TOLERANCE_SECONDS = 5


def parse_utc(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def read_jsonl(path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    if text and not text.endswith(("\n", "\r")):
        raise RuntimeError(f"jsonl_incomplete_trailing_record:{path}")
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"jsonl_malformed_completed_line:{path}:{line_number}:{error.msg}") from error
        if isinstance(row, dict):
            rows.append(row)
        else:
            raise RuntimeError(f"jsonl_completed_line_not_object:{path}:{line_number}")
    return rows


def write_jsonl_atomic(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_trade_ledger(path):
    """Read Glitch's derived account round trips.

    Followers are owned by GlitchCopyEngine, not GlitchAiOrderExecutor, so the
    AI execution journal intentionally has one group-close event rather than a
    fabricated close event per follower. TradeLedger.tsv is the account-level
    execution evidence used for followers and as a diagnostic cross-check for
    masters; intent-bound native master receipts remain the learning authority.
    """
    if not path.exists():
        return []
    columns = [
        "trade_id", "entry_utc_ticks", "exit_utc_ticks", "account", "instrument",
        "side", "contracts", "entry_price", "exit_price", "pnl_points",
        "open_reason", "close_reason", "entry_session", "exit_session",
        "trade_source", "entry_type", "exit_type", "entry_signal", "exit_signal",
        "commission_total", "entry_order_identity", "exit_order_identity",
    ]
    rows = []
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 10:
            continue
        row = dict(zip(columns, parts))
        try:
            row["entry_utc"] = datetime.fromtimestamp(
                (int(row["entry_utc_ticks"]) - DOTNET_EPOCH_TICKS) / 10_000_000,
                tz=timezone.utc,
            )
            row["exit_utc"] = datetime.fromtimestamp(
                (int(row["exit_utc_ticks"]) - DOTNET_EPOCH_TICKS) / 10_000_000,
                tz=timezone.utc,
            )
            for key in ("contracts", "entry_price", "exit_price", "pnl_points", "commission_total"):
                row[key] = float(row.get(key) or 0)
        except (ValueError, OverflowError, OSError):
            continue
        rows.append(row)
    return rows


def read_journal(path):
    rows = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        parts = raw.split("\t", 3)
        if len(parts) < 4:
            continue
        try:
            recorded_utc = datetime.fromtimestamp(
                (int(parts[0]) - DOTNET_EPOCH_TICKS) / 10_000_000,
                tz=timezone.utc,
            )
        except (ValueError, OverflowError, OSError):
            continue
        rows.append({
            "recorded_utc": recorded_utc,
            "account": parts[1],
            "category": parts[2],
            "message": parts[3],
        })
    return rows


def message_fields(message):
    fields = {}
    for token in str(message or "").split("|"):
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    return fields


def _remember_intent(
    intents,
    row,
    evidence,
    cycle_id=None,
    source_kind="unknown",
    account_groups_tsv=None,
):
    if not isinstance(row, dict):
        return
    intent_id = str(row.get("intent_id") or "")
    if not intent_id:
        return
    value = dict(row)
    value["_evidence_path"] = str(evidence)
    incoming_cycle = str(cycle_id or row.get("cycle_id") or "")
    existing = intents.get(intent_id)
    if not isinstance(existing, dict):
        value["_cycle_id"] = incoming_cycle
        value["_lineage_source"] = source_kind
        if source_kind == "outbox" and isinstance(account_groups_tsv, str):
            value["_account_groups_tsv"] = account_groups_tsv
        intents[intent_id] = value
        return

    # The outbox is the authoritative batch-to-intent join.  The AddOn's
    # durable decision log contains the wire intent but not the Hermes batch
    # cycle, so a later blank log value must never erase an outbox cycle.
    existing_cycle = str(existing.get("_cycle_id") or "")
    existing_source = str(existing.get("_lineage_source") or "")
    if existing_cycle and incoming_cycle and existing_cycle != incoming_cycle:
        # Keep the conflict visible even when the authoritative outbox value
        # is about to replace a weaker source's value.
        existing["_lineage_conflict"] = {
            "existing_cycle_id": existing_cycle,
            "incoming_cycle_id": incoming_cycle,
            "existing_source": existing_source,
            "incoming_source": source_kind,
        }
    if source_kind == "outbox" and incoming_cycle:
        existing["_cycle_id"] = incoming_cycle
        existing["_lineage_source"] = source_kind
        if isinstance(account_groups_tsv, str):
            existing["_account_groups_tsv"] = account_groups_tsv
    elif not existing_cycle and incoming_cycle:
        existing["_cycle_id"] = incoming_cycle
        existing["_lineage_source"] = source_kind
    if not existing.get("_evidence_path"):
        existing["_evidence_path"] = str(evidence)


def find_intents(evidence_root=None, decision_root=None, decision_log=None):
    intents = {}
    if evidence_root and evidence_root.exists():
        for path in evidence_root.glob("portfolio-*/intent-*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            _remember_intent(
                intents,
                row,
                path.parent,
                path.parent.name.replace("portfolio-", "glitch-portfolio-"),
                "evidence",
            )
    if decision_root and decision_root.exists():
        for path in sorted(decision_root.glob("*.json")):
            try:
                batch = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(batch, dict):
                continue
            cycle_id = batch.get("cycle_id")
            account_groups_tsv = batch.get("account_groups_tsv")
            for row in batch.get("decisions", []):
                _remember_intent(
                    intents,
                    row,
                    path,
                    cycle_id,
                    "outbox",
                    account_groups_tsv,
                )
    if decision_log and decision_log.exists():
        for row in read_jsonl(decision_log):
            # Glitch's durable decision log wraps the Hermes intent inside an
            # approval/audit envelope. Attribution needs the intent contract,
            # while the envelope remains recoverable through the evidence path.
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else row
            _remember_intent(intents, intent, decision_log, row.get("cycle_id"), "decision_log")
    return intents


def parse_group_accounts_tsv(account_groups_tsv, master_account):
    groups = {}
    for raw in str(account_groups_tsv or "").splitlines():
        fields = raw.strip().split("\t")
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "G" and len(fields) >= 3:
            groups[fields[1]] = {"master": fields[2], "followers": []}
        elif fields[0] == "M" and len(fields) >= 7 and fields[1] in groups and fields[6].strip() == "1":
            groups[fields[1]]["followers"].append(fields[2])
    for group in groups.values():
        if group["master"].lower() == master_account.lower():
            return [group["master"]] + group["followers"]
    return []


def reconciliation_snapshot_intervals(trade_ledger, intents, by_intent, existing):
    """Return every known trade window without interpreting its market outcome."""
    intervals = []
    for trade in trade_ledger:
        start = trade.get("entry_utc")
        end = trade.get("exit_utc")
        if isinstance(start, datetime) and isinstance(end, datetime):
            intervals.append((min(start, end), max(start, end)))
    for outcome in existing.values():
        stamps = []
        for field in (
            "entry_utc", "exit_utc", "terminal_verified_utc",
            "replication_terminal_verified_utc",
        ):
            try:
                stamps.append(parse_utc(outcome.get(field)))
            except (TypeError, ValueError):
                continue
        if stamps:
            intervals.append((min(stamps), max(stamps)))
    for intent_id, intent in intents.items():
        if intent.get("action") not in {"ENTER_LONG", "ENTER_SHORT"}:
            continue
        stamps = []
        for event in by_intent.get(intent_id, []):
            try:
                stamps.append(parse_utc(event.get("recorded_utc")))
            except (TypeError, ValueError):
                continue
        if stamps:
            intervals.append((min(stamps), max(stamps)))

    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _snapshot_filename_utc(path):
    try:
        return datetime.strptime(path.stem, "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def portfolio_snapshots(glitch_data, intervals=None):
    """Load full trade windows plus their nearest boundary snapshots.

    Filename filtering changes only file-selection cost. Every snapshot inside
    every known trade is still parsed, along with the nearest snapshot before
    and after each window. Noncanonical filenames are always parsed.
    """
    snapshots = []
    root = glitch_data / "snapshots" / "historical" / "portfolio"
    paths = list(root.glob("*.json"))
    selected = paths
    if intervals is not None:
        timestamped = sorted(
            (stamp, path)
            for path in paths
            if (stamp := _snapshot_filename_utc(path)) is not None
        )
        stamps = [stamp for stamp, _ in timestamped]
        selected_paths = {
            path for path in paths if _snapshot_filename_utc(path) is None
        }
        for start, end in intervals:
            first = bisect.bisect_left(stamps, start)
            after = bisect.bisect_right(stamps, end)
            lower = max(0, first - 1)
            upper = min(len(timestamped), after + 1)
            selected_paths.update(path for _, path in timestamped[lower:upper])
        selected = sorted(selected_paths)
    for path in selected:
        try:
            row = json.loads(path.read_text(encoding="utf-8-sig"))
            snapshots.append((parse_utc(row["created_utc"]), row))
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return sorted(snapshots, key=lambda item: item[0])


def account_at(snapshot, account):
    for row in snapshot.get("accounts", []):
        if str(row.get("account", "")).lower() == account.lower():
            return row
    return None


def nearest_before(snapshots, when):
    candidates = [row for stamp, row in snapshots if stamp < when]
    return candidates[-1] if candidates else None


def snapshot_reference(snapshots, when):
    """Return a stable reference to the latest portfolio state before entry."""
    candidates = [(stamp, row) for stamp, row in snapshots if stamp < when]
    if not candidates:
        return None
    stamp, row = candidates[-1]
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "snapshot_id": row.get("snapshot_id"),
        "snapshot_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "created_utc": stamp.isoformat().replace("+00:00", "Z"),
        "relation": "nearest_before_entry",
    }


def market_snapshot_rows(glitch_data):
    """Parse the bounded minute-frame corpus once per reconciliation cycle."""
    root = glitch_data / "hermes" / "exchange" / "glitch" / "minute-frames"
    rows = []
    for path in root.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8-sig"))
            raw_stamp = row.get("created_utc") or row.get("minute_id")
            try:
                stamp = parse_utc(raw_stamp)
            except (TypeError, ValueError):
                stamp = datetime.strptime(str(raw_stamp), "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        rows.append((stamp, row))
    return sorted(rows, key=lambda item: item[0])


def market_snapshot_reference(glitch_data, when, instrument_root=None, market_frames=None):
    """Reference the nearest market frame without treating it as native account truth."""
    candidates = [
        (stamp, row)
        for stamp, row in (
            market_frames if market_frames is not None else market_snapshot_rows(glitch_data)
        )
        if stamp < when
    ]
    if not candidates:
        return None
    stamp, row = candidates[-1]
    market = row.get("market_snapshot") if isinstance(row, dict) else None
    if not isinstance(market, dict):
        return None
    target_root = _instrument_root(instrument_root or "MNQ")
    instruments = market.get("instruments") if isinstance(market.get("instruments"), list) else []
    instrument = next(
        (
            value for value in instruments
            if isinstance(value, dict)
            and _instrument_root(value.get("instrument") or value.get("instrument_root")) == target_root
        ),
        None,
    )
    reference = {
        "minute_id": row.get("minute_id"),
        "snapshot_hash": market.get("snapshot_hash"),
        "created_utc": stamp.isoformat().replace("+00:00", "Z"),
        "relation": "nearest_before_entry",
    }
    if isinstance(instrument, dict):
        reference["instrument_root"] = _instrument_root(instrument.get("instrument") or instrument.get("instrument_root"))
        reference["current_price"] = instrument.get("current_price")
        reference["descriptive_state"] = instrument.get("descriptive_state")
        reference["instrument_economics"] = instrument.get("instrument_economics")
        reference["native_observations"] = instrument.get("native_observations")
    return reference


def _iso_or_none(value):
    if not value:
        return None
    try:
        return parse_utc(value).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return None


def _duration_ms(start, end):
    try:
        return round((parse_utc(end) - parse_utc(start)).total_seconds() * 1000, 3)
    except (TypeError, ValueError):
        return None


def first_touch_state(close_kind):
    """Map native close evidence without claiming unavailable intrabar order."""
    return {
        "stop": "STOP_FIRST",
        "target": "PRIMARY_TARGET_FIRST",
        "managed_exit": "NEITHER",
    }.get(str(close_kind or ""), "UNRESOLVED")


def normalized_outcome(account_outcome):
    risk = account_outcome.get("initial_native_risk_usd")
    realized = account_outcome.get("realized_pnl_usd")
    risk_complete = (
        isinstance(risk, (int, float)) and risk > 0
        and isinstance(realized, (int, float))
    )
    sampled_mfe = account_outcome.get("sampled_mfe_usd")
    sampled_mae = account_outcome.get("sampled_mae_usd")
    return {
        "realized_pnl_usd": realized,
        "realized_r": (realized / risk) if risk_complete else None,
        "mfe_r": (sampled_mfe / risk) if isinstance(sampled_mfe, (int, float)) and risk_complete else None,
        "mae_r": (sampled_mae / risk) if isinstance(sampled_mae, (int, float)) and risk_complete else None,
        "first_touch": first_touch_state(account_outcome.get("close_kind")),
        "source_quality": {
            "realized": "intent_bound_native_receipt_and_native_economics" if risk_complete else "native_receipt_or_incomplete_risk",
            "mfe_mae": "minute_snapshot_sampled_not_exact",
            "first_touch": "native_exit_class_only_no_intrabar_order_claim",
        },
        "excursion_eligible": False,
    }


def entry_range_fill_quality(intent, fill_price, tick_size):
    result = {
        "schema_version": "glitch.hermes.entry_range_fill_quality.v1",
        "status": "unavailable",
        "effect": "observation_only_no_execution_effect",
        "declared_entry_range_low": intent.get("entry_range_low"),
        "declared_entry_range_high": intent.get("entry_range_high"),
        "native_fill_price": fill_price,
    }
    try:
        low = float(intent.get("entry_range_low"))
        high = float(intent.get("entry_range_high"))
        fill = float(fill_price)
        tick = float(tick_size)
    except (TypeError, ValueError):
        result["reason"] = "entry_range_or_native_fill_unavailable"
        return result
    if not all(math.isfinite(value) for value in (low, high, fill, tick)) or low >= high or tick <= 0:
        result["reason"] = "entry_range_or_tick_size_invalid"
        return result

    if low <= fill <= high:
        relation = "inside_declared_range"
        deviation_points = 0.0
    elif fill < low:
        relation = (
            "favorable_beyond_range"
            if intent.get("action") == "ENTER_LONG" else "adverse_beyond_range"
        )
        deviation_points = low - fill
    else:
        relation = (
            "adverse_beyond_range"
            if intent.get("action") == "ENTER_LONG" else "favorable_beyond_range"
        )
        deviation_points = fill - high
    result.update({
        "status": (
            "inside_declared_range"
            if relation == "inside_declared_range" else "outside_declared_range"
        ),
        "range_relation": relation,
        "deviation_points": round(deviation_points, 8),
        "deviation_ticks": round(deviation_points / tick, 4),
    })
    return result


def intent_fidelity(
    intent, account_outcome, submitted, bracket_event, market_reference, events,
    management_history=None,
):
    submit_fields = message_fields(submitted.get("message")) if isinstance(submitted, dict) else {}
    bracket_fields = message_fields(bracket_event.get("message")) if isinstance(bracket_event, dict) else {}
    decision_price = market_reference.get("current_price") if isinstance(market_reference, dict) else None
    fill_price = account_outcome.get("entry_price")
    tick_size = account_outcome.get("tick_size")
    adverse_drift_ticks = None
    try:
        if decision_price is not None and fill_price is not None and float(tick_size) > 0:
            signed_move = float(fill_price) - float(decision_price)
            if intent.get("action") == "ENTER_SHORT":
                signed_move = -signed_move
            adverse_drift_ticks = signed_move / float(tick_size)
    except (TypeError, ValueError):
        adverse_drift_ticks = None

    quantity = int(account_outcome.get("quantity") or 0)
    legs = account_outcome.get("initial_protection_legs") or []
    stop_coverage = sum(int(leg.get("quantity") or 0) for leg in legs if isinstance(leg, dict))
    target_present = any(
        _float(bracket_fields, f"tp{index}") is not None for index in range(1, 4)
    )
    target_coverage = stop_coverage if target_present else 0
    if quantity > 0 and stop_coverage == quantity and target_coverage == quantity:
        native_state = "fully_protected"
    elif stop_coverage > 0 or target_coverage > 0:
        native_state = "partially_protected"
    else:
        native_state = "unknown"

    native_management_events = []
    for event in events or []:
        code = str(event.get("code") or "")
        if any(token in code.lower() for token in ("move", "amend", "modify", "managed_exit")):
            native_management_events.append({
                "code": code,
                "recorded_utc": event.get("recorded_utc"),
                "message": event.get("message"),
            })
    counterfactuals = management_history if isinstance(management_history, dict) else {
        "summary": {"total_decisions": len(management_history or [])},
        "representative_decisions": list(management_history or []),
    }
    return {
        "identity": {
            "intent_id": intent.get("intent_id"),
            "cycle_id": intent.get("_cycle_id"),
            "instrument": intent.get("instrument"),
            "account": intent.get("account"),
        },
        "decision_price": decision_price,
        "submission_price": _float(bracket_fields, "fill"),
        "native_fill_price": fill_price,
        "signed_adverse_drift_ticks": adverse_drift_ticks,
        "entry_range_fill_quality": entry_range_fill_quality(intent, fill_price, tick_size),
        "timing": {
            "decision_to_submission_ms": _duration_ms(
                market_reference.get("created_utc") if isinstance(market_reference, dict) else None,
                bracket_event.get("recorded_utc") if isinstance(bracket_event, dict) else None,
            ),
            "submission_to_fill_ms": _duration_ms(
                submitted.get("recorded_utc") if isinstance(submitted, dict) else None,
                account_outcome.get("entry_utc"),
            ),
            "fill_to_bracket_submission_ms": _duration_ms(
                account_outcome.get("entry_utc"),
                bracket_event.get("recorded_utc") if isinstance(bracket_event, dict) else None,
            ),
            "fill_to_full_protection_ack_ms": None,
            "full_protection_acknowledgement_status": "unavailable_native_receipt",
        },
        "coverage": {
            "position_quantity": quantity,
            "stop_coverage_quantity": stop_coverage,
            "target_coverage_quantity": target_coverage,
            "unprotected_quantity": max(0, quantity - min(stop_coverage, target_coverage)),
            "native_state": native_state,
            "source": "native_bracket_and_execution_receipts",
        },
        "native_state": {
            "protection_status": account_outcome.get("protection_status"),
            "protection_evidence": account_outcome.get("protection_evidence"),
            "submission_correlation": submit_fields.get("correlation"),
        },
        "management_history": counterfactuals["representative_decisions"],
        "management_counterfactual_summary": counterfactuals["summary"],
        "native_management_events": native_management_events,
    }


def forecast_outcome(forecast, close_kind):
    observed = None
    if close_kind in {"stop", "target"}:
        observed = close_kind == "stop"
    if not isinstance(forecast, dict):
        return {
            "status": "not_provided",
            "event": "STOP_BEFORE_PRIMARY_TARGET",
            "observed": observed,
            "brier_score": None,
        }
    probability = forecast.get("probability")
    brier = None
    if observed is not None and isinstance(probability, (int, float)):
        brier = (float(probability) - (1.0 if observed else 0.0)) ** 2
    return {
        "status": "observed" if observed is not None else "unresolved",
        "event": forecast.get("event"),
        "probability": probability,
        "method": forecast.get("method"),
        "confidence": forecast.get("confidence"),
        "observed": observed,
        "brier_score": brier,
        "observation_source": "intent_bound_native_exit_receipt" if observed is not None else None,
    }


def canonical_outcome_layers(
    intent, account_outcome, submitted, bracket_event, market_reference, events,
    management_history=None,
):
    normalized = normalized_outcome(account_outcome)
    return {
        "decision_geometry": {
            "source": "hermes_intent",
            "action": intent.get("action"),
            "instrument": intent.get("instrument"),
            "quantity": intent.get("quantity"),
            "decision_price": market_reference.get("current_price") if isinstance(market_reference, dict) else None,
            "planned_entry_range_low": intent.get("entry_range_low"),
            "planned_entry_range_high": intent.get("entry_range_high"),
            "planned_stop": intent.get("stop_loss"),
            "planned_target": intent.get("take_profit_1"),
            "planned_stop_2": intent.get("stop_loss_2"),
            "planned_target_2": intent.get("take_profit_2"),
            "planned_stop_3": intent.get("stop_loss_3"),
            "planned_target_3": intent.get("take_profit_3"),
        },
        "native_geometry": {
            "source": "intent_bound_native_execution_receipts",
            "entry_price": account_outcome.get("entry_price"),
            "exit_price": account_outcome.get("exit_price"),
            "point_value_usd": account_outcome.get("point_value_usd"),
            "tick_size": account_outcome.get("tick_size"),
            "initial_protection_legs": account_outcome.get("initial_protection_legs"),
            "initial_native_risk_usd": account_outcome.get("initial_native_risk_usd"),
            "geometry_comparison": {
                "planned_stop": intent.get("stop_loss"),
                "native_initial_stops": [
                    leg.get("initial_stop_price") for leg in account_outcome.get("initial_protection_legs", [])
                    if isinstance(leg, dict)
                ],
            },
        },
        "execution_diagnostics": {
            "intent_fidelity": intent_fidelity(
                intent, account_outcome, submitted, bracket_event, market_reference, events,
                management_history,
            ),
        },
        "normalized_outcome": normalized,
        "forecast_outcome": forecast_outcome(
            intent.get("forecast"), account_outcome.get("close_kind")
        ),
        "attribution": {
            "origin": intent.get("origin") or ("ai" if intent.get("intent_id") else "manual"),
            "master_learning_eligible": True,
            "normalization_status": account_outcome.get("risk_normalization_status"),
            "excursion_source_quality": "sampled_minute_snapshots_not_exact",
        },
    }


def configured_master_accounts(path):
    masters = set()
    if not path.exists():
        return masters
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        fields = raw.strip().split("\t")
        if len(fields) >= 3 and fields[0] == "G" and fields[2].strip():
            masters.add(fields[2].strip().lower())
    return masters


def _normalized_entry_order_identity(record):
    for key in ("entry_order_identity", "entry_order_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value.lower()
    return ""


def _manual_entry_order_key(record):
    manual = record.get("manual_trade") if isinstance(record.get("manual_trade"), dict) else {}
    order_identity = _normalized_entry_order_identity(record) or _normalized_entry_order_identity(manual)
    account = str(record.get("account") or record.get("master_account") or "").strip().lower()
    instrument = str(record.get("instrument") or "").split()[0].upper()
    if not account or not instrument or not order_identity:
        return ""
    return "|".join(("entry-order-v1", account, instrument, order_identity))


def _manual_entry_fallback_key(record):
    account = str(record.get("account") or record.get("master_account") or "").strip().lower()
    instrument = str(record.get("instrument") or "").split()[0].upper()
    side = str(record.get("side") or record.get("action") or "").strip().lower()
    if side in {"long", "buy", "enter_long"}:
        side = "long"
    elif side in {"short", "sell", "sellshort", "enter_short"}:
        side = "short"
    entry_value = record.get("entry_utc")
    try:
        entry_utc = parse_utc(entry_value).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return ""
    manual = record.get("manual_trade") if isinstance(record.get("manual_trade"), dict) else {}
    source = str(record.get("trade_source") or manual.get("trade_source") or "").strip().lower()
    entry_type = str(record.get("entry_type") or manual.get("entry_type") or "").strip().lower()
    signal = str(record.get("entry_signal") or manual.get("entry_signal") or "").strip().lower()
    if not account or not instrument or not side:
        return ""
    return "|".join(("entry-fallback-v1", account, instrument, side, entry_utc, source, entry_type, signal))


def manual_episode_identity(trade):
    """Return an immutable manual-entry identity, with a legacy-ledger fallback."""
    return _manual_entry_order_key(trade) or _manual_entry_fallback_key(trade)


def replace_manual_outcome(existing, manual, trade):
    """Replace corrected and legacy-ID variants of the same manual episode."""
    current_order_key = _manual_entry_order_key(trade)
    current_fallback = _manual_entry_fallback_key(trade)
    for intent_id, prior in list(existing.items()):
        if not isinstance(prior, dict) or str(prior.get("origin") or "").lower() != "manual":
            continue
        prior_order_key = _manual_entry_order_key(prior)
        if current_order_key and prior_order_key:
            same_episode = current_order_key == prior_order_key
        elif prior_order_key:
            same_episode = False
        else:
            same_episode = bool(current_fallback and current_fallback == _manual_entry_fallback_key(prior))
        if same_episode:
            existing.pop(intent_id, None)
    existing[manual["intent_id"]] = manual


def contemporaneous_ai_comparison(intents, trade):
    """Return nearby AI thought, when present, without inventing one for manual trades."""
    candidates = []
    for intent in intents.values():
        if str(intent.get("account") or "").lower() != str(trade.get("account") or "").lower():
            continue
        if str(intent.get("instrument") or "").split()[0].upper() != str(trade.get("instrument") or "").split()[0].upper():
            continue
        try:
            created = parse_utc(intent.get("created_utc"))
        except (TypeError, ValueError):
            continue
        distance = (trade["entry_utc"] - created).total_seconds()
        if distance < 0 or distance > 90:
            continue
        candidates.append((distance, created, intent))
    if not candidates:
        return None
    _, created, intent = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return {
        "intent_id": intent.get("intent_id"),
        "cycle_id": intent.get("_cycle_id"),
        "created_utc": created.isoformat().replace("+00:00", "Z"),
        "action": intent.get("action"),
        "confidence": intent.get("confidence"),
        "snapshot_hash": intent.get("snapshot_hash"),
        "reason": intent.get("reason"),
        "decision_audit": intent.get("decision_audit"),
        "comparison_status": "nearby_ai_decision",
    }


def manual_trade_outcome(glitch_data, snapshots, intents, trade, market_frames=None):
    """Build a learning-only manual episode from completed native round-trip truth."""
    source = str(trade.get("trade_source") or "").strip().lower()
    entry_type = str(trade.get("entry_type") or "").strip().lower()
    signal = str(trade.get("entry_signal") or "").strip().upper()
    if source != "manual" and entry_type != "manual":
        return None
    if source == "replication" or signal.startswith("GLT-"):
        return None
    account = str(trade.get("account") or "")
    instrument = str(trade.get("instrument") or "MNQ").split()[0].upper()
    origin_key = manual_episode_identity(trade)
    if not account or not origin_key:
        return None
    digest = hashlib.sha256(origin_key.encode("utf-8")).hexdigest()
    intent_id = "manual-" + digest[:32]
    cycle_id = "manual-cycle-" + digest[:24]
    side = "ENTER_LONG" if str(trade.get("side") or "").lower() == "long" else "ENTER_SHORT"
    portfolio = snapshot_reference(snapshots, trade["entry_utc"])
    market = market_snapshot_reference(
        glitch_data, trade["entry_utc"], instrument, market_frames
    )
    terminal = terminal_group_snapshot(snapshots, trade["exit_utc"], [account])
    master_result = {
        "account": account,
        "quantity": int(abs(trade.get("contracts") or 1)),
        "entry_utc": trade["entry_utc"].isoformat().replace("+00:00", "Z"),
        "exit_utc": trade["exit_utc"].isoformat().replace("+00:00", "Z"),
        "entry_price": trade.get("entry_price"),
        "exit_price": trade.get("exit_price"),
        "realized_pnl_usd": None,
        "pnl_points": trade.get("pnl_points"),
        "commission_total": trade.get("commission_total"),
        "trade_id": trade.get("trade_id"),
        "close_kind": infer_close_kind(trade),
        **excursion(
            snapshots, account, trade["entry_utc"], trade["exit_utc"], instrument, 0.0
        ),
    }
    manual_intent = {
        "intent_id": intent_id,
        "_cycle_id": cycle_id,
        "instrument": instrument,
        "account": account,
        "action": side,
        "quantity": master_result["quantity"],
        "origin": "manual",
        "forecast": None,
    }
    canonical_layers = canonical_outcome_layers(
        manual_intent, master_result, None, None, market, []
    )
    return {
        "schema_version": "glitch.hermes.trade_outcome.v1",
        "recorded_utc": trade["exit_utc"].isoformat().replace("+00:00", "Z"),
        "intent_id": intent_id,
        "cycle_id": cycle_id,
        "origin": "manual",
        "route_id": "manual",
        "master_account": account,
        "instrument": instrument,
        "action": side,
        "entry_utc": trade["entry_utc"].isoformat().replace("+00:00", "Z"),
        "exit_utc": trade["exit_utc"].isoformat().replace("+00:00", "Z"),
        "terminal_verified_utc": terminal.isoformat().replace("+00:00", "Z") if terminal else None,
        "reason": trade.get("open_reason"),
        "account_outcomes": [master_result],
        "replication_diagnostics": [],
        "master_realized_pnl_usd": None,
        "group_realized_pnl_usd": None,
        "master_realized_pnl_points": trade.get("pnl_points"),
        "master_attribution_status": "complete",
        "master_learning_eligible": True,
        "attribution_status": "complete",
        "learning_eligible": True,
        "evidence": "TradeLedger.tsv",
        "snapshot_reference": {
            "portfolio": portfolio,
            "market": market,
            "status": "complete" if portfolio or market else "unavailable",
        },
        "ai_comparison": contemporaneous_ai_comparison(intents, trade),
        **canonical_layers,
        "manual_trade": {
            "entry_order_identity": str(trade.get("entry_order_identity") or trade.get("entry_order_id") or "").strip() or None,
            "trade_source": trade.get("trade_source"),
            "entry_type": trade.get("entry_type"),
            "entry_signal": trade.get("entry_signal"),
            "exit_signal": trade.get("exit_signal"),
            "open_reason": trade.get("open_reason"),
            "close_reason": trade.get("close_reason"),
        },
    }


def nearest_after(snapshots, when):
    for stamp, row in snapshots:
        if stamp > when:
            return row
    return None


def terminal_group_snapshot(snapshots, when, expected_accounts):
    """Return the first post-exit snapshot proving the whole group terminal."""
    for stamp, snapshot in snapshots:
        if stamp <= when:
            continue
        terminal = True
        for account in expected_accounts:
            row = account_at(snapshot, account)
            if not row or row.get("positions") or int(row.get("working_orders") or 0) != 0:
                terminal = False
                break
        if terminal:
            return stamp
    return None


def excursion(snapshots, account, entry_utc, exit_utc, instrument_root, realized_pnl):
    # These are deliberately named sampled bounds, not native MAE/MFE. Minute
    # snapshots plus terminal PnL cannot prove the price-path extrema.
    values = [0.0, float(realized_pnl)]
    sample_times = []
    for stamp, snapshot in snapshots:
        if stamp < entry_utc or stamp > exit_utc:
            continue
        account_row = account_at(snapshot, account)
        if not account_row:
            continue
        for position in account_row.get("positions", []):
            if str(position.get("instrument_root", "")).upper() == instrument_root:
                values.append(float(position.get("unrealized_pnl", 0)))
                sample_times.append(stamp)
    return {
        "sampled_mfe_usd": max(values) if values else None,
        "sampled_mae_usd": min(values) if values else None,
        "excursion_sample_count": len(sample_times),
        "excursion_sampling_method": "minute_unrealized_plus_terminal_bounds",
        "excursion_first_sample_utc": (
            sample_times[0].isoformat().replace("+00:00", "Z") if sample_times else None
        ),
        "excursion_last_sample_utc": (
            sample_times[-1].isoformat().replace("+00:00", "Z") if sample_times else None
        ),
        "excursion_eligible": False,
    }


def management_intent_counterfactuals(
    intents, snapshots, account, instrument_root, entry_utc, exit_utc, realized_pnl
):
    """Attach sampled opportunity cost to in-trade decisions without prescribing action."""
    rows = []
    for intent in intents.values():
        action = str(intent.get("action") or "").upper()
        if action not in {"HOLD", "MOVE_STOP", "MOVE_TP", "EXIT"}:
            continue
        if str(intent.get("account") or "").lower() != account.lower():
            continue
        if _instrument_root(intent.get("instrument")) != instrument_root:
            continue
        try:
            created_utc = parse_utc(intent.get("created_utc"))
        except (TypeError, ValueError):
            continue
        if not entry_utc < created_utc < exit_utc:
            continue

        sampled = None
        for stamp, snapshot in snapshots:
            if stamp > created_utc:
                break
            account_row = account_at(snapshot, account)
            if account_row is None:
                continue
            position = next((
                value for value in account_row.get("positions", [])
                if _instrument_root(value.get("instrument_root") or value.get("instrument")) == instrument_root
            ), None)
            if isinstance(position, dict):
                sampled = (stamp, position.get("unrealized_pnl"))
        sampled_pnl = sampled[1] if sampled is not None else None
        advantage = None
        if isinstance(sampled_pnl, (int, float)) and isinstance(realized_pnl, (int, float)):
            advantage = float(sampled_pnl) - float(realized_pnl)
        rows.append({
            "intent_id": intent.get("intent_id"),
            "cycle_id": intent.get("_cycle_id"),
            "created_utc": created_utc.isoformat().replace("+00:00", "Z"),
            "action": action,
            "protection_updates": intent.get("protection_updates"),
            "sampled_snapshot_utc": (
                sampled[0].isoformat().replace("+00:00", "Z") if sampled is not None else None
            ),
            "sampled_exit_then_pnl_usd_before_costs": sampled_pnl,
            "actual_terminal_pnl_usd_before_costs": realized_pnl,
            "sampled_exit_then_advantage_usd": advantage,
        })
    rows.sort(key=lambda row: row["created_utc"])
    action_counts = {
        action: sum(1 for row in rows if row["action"] == action)
        for action in ("HOLD", "MOVE_STOP", "MOVE_TP", "EXIT")
        if any(row["action"] == action for row in rows)
    }
    numeric = [
        row for row in rows
        if isinstance(row.get("sampled_exit_then_advantage_usd"), (int, float))
    ]
    summary = {
        "schema_version": "glitch.hermes.management_counterfactual_summary.v1",
        "effect": "informational_only_not_execution_or_strategy_gate",
        "total_decisions": len(rows),
        "action_counts": action_counts,
        "maximum_sampled_exit_advantage_usd": (
            max(row["sampled_exit_then_advantage_usd"] for row in numeric) if numeric else None
        ),
        "minimum_sampled_exit_advantage_usd": (
            min(row["sampled_exit_then_advantage_usd"] for row in numeric) if numeric else None
        ),
        "limitations": "minute_snapshot_samples_not_executable_fills_no_fees_or_slippage",
    }
    selected = []
    candidates = []
    if rows:
        candidates.extend((rows[0], rows[-1]))
    if numeric:
        candidates.extend((
            max(numeric, key=lambda row: row["sampled_exit_then_advantage_usd"]),
            min(numeric, key=lambda row: row["sampled_exit_then_advantage_usd"]),
        ))
    for action in ("HOLD", "MOVE_STOP", "MOVE_TP", "EXIT"):
        action_rows = [row for row in rows if row["action"] == action]
        if action_rows:
            candidates.extend((action_rows[0], action_rows[-1]))
    for row in candidates + rows:
        if row["intent_id"] in {value["intent_id"] for value in selected}:
            continue
        selected.append(row)
        if len(selected) == 8:
            break
    selected.sort(key=lambda row: row["created_utc"])
    return {"summary": summary, "representative_decisions": selected}


def infer_close_kind(trade):
    exit_type = str(trade.get("exit_type") or "").strip().lower()
    exit_signal = str(trade.get("exit_signal") or "").strip()
    close_reason = str(trade.get("close_reason") or "").strip().lower()
    signal_parts = exit_signal.upper().split("-")
    signal_role = signal_parts[2] if len(signal_parts) > 2 else ""
    if (
        "stop" in exit_type or exit_type == "sl" or "stop" in close_reason
        or signal_role == "S" or re.match(r"^[HP]S\d+", signal_role)
    ):
        return "stop"
    if (
        "target" in exit_type or exit_type == "tp" or "target" in close_reason
        or signal_role == "T" or re.match(r"^[HP]T\d+", signal_role)
    ):
        return "target"
    if exit_type in {"exit", "manual", "close"} or exit_signal.lower() == "close" or "manual" in close_reason:
        return "managed_exit"
    return "unknown"


def native_master_trade_from_events(
    events, intent, master_account, bracket_event, bracket_fields, derived_trade=None
):
    """Build and validate one master round trip from intent-bound native receipts."""
    entry_events = []
    terminal_events = []
    seen_executions = set()
    for event in events:
        code = str(event.get("code") or "")
        if code != "master_entry_fill_observed" and code not in MASTER_TERMINAL_CODES:
            continue
        fields = message_fields(event.get("message"))
        if str(fields.get("account") or "").lower() != master_account.lower():
            continue
        execution_id = str(fields.get("execution_id") or "").strip()
        if execution_id and execution_id in seen_executions:
            continue
        if execution_id:
            seen_executions.add(execution_id)
        try:
            recorded_utc = parse_utc(event.get("recorded_utc"))
            fill = float(fields["fill"])
            native_signed_quantity = float(fields["signed_quantity"])
            signed_quantity = float(
                event.get("_attributed_signed_quantity", native_signed_quantity)
            )
        except (KeyError, TypeError, ValueError):
            continue
        if signed_quantity == 0:
            continue
        parsed = {
            "code": code,
            "recorded_utc": recorded_utc,
            "fill": fill,
            "signed_quantity": signed_quantity,
            "native_execution_signed_quantity": native_signed_quantity,
            "unallocated_native_quantity": abs(float(
                event.get("_unallocated_signed_quantity", 0) or 0
            )),
            "entry": _float(fields, "entry"),
            "point_value_usd": _float(fields, "point_value_usd"),
            "realized_pnl_usd": _float(fields, "realized_pnl_usd"),
            "execution_id": execution_id or None,
            "native_order": fields.get("native_order") or None,
            "source_intent_id": event.get("_source_intent_id") or event.get("intent_id"),
        }
        if code == "master_entry_fill_observed":
            entry_events.append(parsed)
        else:
            parsed["close_kind"] = MASTER_TERMINAL_CODES[code]
            terminal_events.append(parsed)

    audit = {
        "schema_version": "glitch.hermes.native_outcome_reconciliation.v2",
        "status": "quarantined",
        "learning_eligible": False,
        "authority": "intent_bound_native_execution_receipts",
        "discrepancies": [],
        "native_entry_events": [
            {
                **{key: value for key, value in row.items() if key != "recorded_utc"},
                "recorded_utc": row["recorded_utc"].isoformat().replace("+00:00", "Z"),
            }
            for row in entry_events
        ],
        "native_terminal_events": [
            {
                **{key: value for key, value in row.items() if key != "recorded_utc"},
                "recorded_utc": row["recorded_utc"].isoformat().replace("+00:00", "Z"),
            }
            for row in terminal_events
        ],
    }
    if not terminal_events:
        audit["discrepancies"].append("native_terminal_event_missing")
        return None, audit

    entry_sign = 1 if intent.get("action") == "ENTER_LONG" else -1
    exit_sign = -entry_sign
    if entry_events and any(
        (1 if row["signed_quantity"] > 0 else -1) != entry_sign for row in entry_events
    ):
        audit["discrepancies"].append("native_entry_side_mismatch")
    if any((1 if row["signed_quantity"] > 0 else -1) != exit_sign for row in terminal_events):
        audit["discrepancies"].append("native_exit_side_mismatch")
    if any(row["unallocated_native_quantity"] > 1e-9 for row in terminal_events):
        audit["discrepancies"].append("native_exit_quantity_unattributed")

    exit_quantity = sum(abs(row["signed_quantity"]) for row in terminal_events)
    if entry_events:
        entry_quantity = sum(abs(row["signed_quantity"]) for row in entry_events)
        entry_price = sum(
            row["fill"] * abs(row["signed_quantity"]) for row in entry_events
        ) / entry_quantity
        entry_utc = min(row["recorded_utc"] for row in entry_events)
        entry_source = "native_master_entry_fill_receipt"
        entry_signal = next((row["native_order"] for row in entry_events if row["native_order"]), None)
    else:
        entry_quantity = sum(
            max(0.0, _float(bracket_fields, f"leg{index}_qty", 0.0) or 0.0)
            for index in range(1, 4)
        )
        if entry_quantity <= 0:
            entry_quantity = abs(float(intent.get("quantity") or 0))
        entry_price = _float(bracket_fields, "fill")
        try:
            entry_utc = parse_utc(bracket_event.get("recorded_utc"))
        except (AttributeError, TypeError, ValueError):
            entry_utc = None
        entry_source = "native_fill_anchored_bracket_receipt"
        entry_signal = None
    if entry_quantity <= 0 or entry_price is None or entry_utc is None:
        audit["discrepancies"].append("native_entry_receipt_incomplete")
        return None, audit
    if abs(entry_quantity - exit_quantity) > 1e-9:
        audit["discrepancies"].append("native_entry_exit_quantity_mismatch")

    native_exit_price = sum(
        row["fill"] * abs(row["signed_quantity"]) for row in terminal_events
    ) / exit_quantity
    native_exit_utc = max(row["recorded_utc"] for row in terminal_events)
    tick_size = _float(bracket_fields, "tick_size")
    price_tolerance = max(float(tick_size or 0) / 2, 1e-8)
    native_entries = [row["entry"] for row in terminal_events if row["entry"] is not None]
    if native_entries and any(
        abs(float(value) - entry_price) > price_tolerance
        for value in native_entries
    ):
        audit["discrepancies"].append("native_entry_price_mismatch")
    native_kinds = {row["close_kind"] for row in terminal_events}
    if len(native_kinds) != 1:
        audit["discrepancies"].append("native_close_kind_ambiguous")

    native_pnls = [row["realized_pnl_usd"] for row in terminal_events]
    point_values = {
        row["point_value_usd"]
        for row in terminal_events
        if row["point_value_usd"] is not None and row["point_value_usd"] > 0
    }
    bracket_point_value = _float(bracket_fields, "point_value_usd")
    if not point_values and bracket_point_value is not None and bracket_point_value > 0:
        point_values.add(bracket_point_value)
    if len(point_values) > 1:
        audit["discrepancies"].append("native_point_value_mismatch")
    point_value = next(iter(point_values)) if len(point_values) == 1 else None
    pnl_points = (native_exit_price - entry_price) * entry_sign * exit_quantity
    geometry_pnl_usd = pnl_points * point_value if point_value is not None else None
    receipt_pnl_usd = (
        sum(float(value) for value in native_pnls)
        if native_pnls and all(value is not None for value in native_pnls)
        else None
    )
    if (
        receipt_pnl_usd is not None and geometry_pnl_usd is not None
        and abs(receipt_pnl_usd - geometry_pnl_usd) > 0.01
    ):
        audit["discrepancies"].append("native_realized_pnl_mismatch")

    close_kind = next(iter(native_kinds)) if len(native_kinds) == 1 else "unknown"
    exit_type = {"stop": "SL", "target": "TP", "managed_exit": "EXIT"}.get(close_kind, "Unknown")
    close_reason = {
        "stop": "Stop Loss", "target": "Take Profit", "managed_exit": "Managed Exit"
    }.get(close_kind, "Unknown")
    trade = {
        "trade_id": f"native-receipt:{intent.get('intent_id')}",
        "account": master_account,
        "instrument": _instrument_root(intent.get("instrument")),
        "side": "long" if entry_sign > 0 else "short",
        "contracts": entry_quantity,
        "entry_utc": entry_utc,
        "exit_utc": native_exit_utc,
        "entry_price": entry_price,
        "exit_price": native_exit_price,
        "pnl_points": pnl_points,
        "realized_pnl_usd": receipt_pnl_usd if receipt_pnl_usd is not None else geometry_pnl_usd,
        "point_value_usd": point_value,
        "commission_total": 0.0,
        "commission_status": "unavailable_not_assumed",
        "trade_source": "Strategy",
        "entry_type": "ENTRY",
        "exit_type": exit_type,
        "entry_signal": entry_signal,
        "exit_signal": next((row["native_order"] for row in terminal_events if row["native_order"]), None),
        "open_reason": "Hermes Entry",
        "close_reason": close_reason,
        "native_entry_source": entry_source,
    }

    audit["native_aggregate"] = {
        "entry_utc": entry_utc.isoformat().replace("+00:00", "Z"),
        "entry_price": entry_price,
        "exit_utc": native_exit_utc.isoformat().replace("+00:00", "Z"),
        "exit_price": native_exit_price,
        "quantity": exit_quantity,
        "close_kinds": sorted(native_kinds),
        "realized_pnl_usd": trade["realized_pnl_usd"],
        "point_value_usd": point_value,
        "entry_source": entry_source,
    }
    derived_discrepancies = []
    if derived_trade is None:
        audit["derived_trade_ledger"] = {
            "status": "missing",
            "effect": "diagnostic_only_no_master_learning_effect",
        }
    else:
        try:
            if abs(float(derived_trade.get("contracts") or 0) - entry_quantity) > 1e-9:
                derived_discrepancies.append("quantity_mismatch")
            if abs(float(derived_trade.get("entry_price")) - entry_price) > price_tolerance:
                derived_discrepancies.append("entry_price_mismatch")
            if abs(float(derived_trade.get("exit_price")) - native_exit_price) > price_tolerance:
                derived_discrepancies.append("exit_price_mismatch")
            if abs((derived_trade["exit_utc"] - native_exit_utc).total_seconds()) > NATIVE_OUTCOME_TIME_TOLERANCE_SECONDS:
                derived_discrepancies.append("exit_time_mismatch")
            if infer_close_kind(derived_trade) != close_kind:
                derived_discrepancies.append("close_kind_mismatch")
        except (KeyError, TypeError, ValueError):
            derived_discrepancies.append("record_incomplete")
        audit["derived_trade_ledger"] = {
            "status": "matched" if not derived_discrepancies else "mismatch",
            "effect": "diagnostic_only_no_master_learning_effect",
            "trade_id": derived_trade.get("trade_id"),
            "discrepancies": derived_discrepancies,
        }
    if not audit["discrepancies"]:
        audit["status"] = "reconciled"
        audit["learning_eligible"] = True
    return trade, audit


def _float(fields, key, fallback=None):
    try:
        return float(fields.get(key))
    except (TypeError, ValueError):
        return fallback


def _instrument_root(value):
    return str(value or "").split()[0].upper()


def _native_log_field(message, name):
    match = re.search(rf"(?:^|\s){re.escape(name)}='([^']*)'", message)
    return match.group(1) if match else ""


def parse_native_protection_log_line(raw):
    """Parse one positive native follower-protection order lifecycle row."""
    if "Name='GLT-COPY-" not in raw:
        return None
    parts = raw.rstrip("\r\n").split("|", 3)
    if len(parts) != 4:
        return None
    try:
        recorded_local = datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S:%f")
    except ValueError:
        return None
    message = parts[3]
    signal = COPY_PROTECTION_SIGNAL_PATTERN.match(_native_log_field(message, "Name"))
    if signal is None or _native_log_field(message, "New state").lower() not in NATIVE_PROTECTION_STATES:
        return None
    order = _native_log_field(message, "Order")
    if "/" not in order:
        return None
    quantity_match = NATIVE_LOG_QUANTITY_PATTERN.search(message)
    try:
        quantity_value = float(quantity_match.group("quantity") if quantity_match else "")
        quantity = int(quantity_value)
    except (TypeError, ValueError):
        return None
    oco = _native_log_field(message, "Oco").strip()
    if quantity <= 0 or quantity_value != quantity or not oco:
        return None
    return {
        "recorded_local": recorded_local,
        "account": order.rsplit("/", 1)[1].strip(),
        "instrument_root": _instrument_root(_native_log_field(message, "Instrument")),
        "role": signal.group("role").upper(),
        "correlation": signal.group("correlation").lower(),
        "oco": oco,
        "quantity": quantity,
    }


def read_native_protection_log_day(log_directory, date_key):
    if not log_directory.is_dir():
        return []
    paths = sorted(log_directory.glob(f"log.{date_key}.*.txt"))
    primary_paths = [path for path in paths if not path.name.lower().endswith(".en.txt")]
    rows = []
    for path in primary_paths or paths:
        try:
            with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
                for raw in stream:
                    row = parse_native_protection_log_line(raw)
                    if row is not None:
                        rows.append(row)
        except OSError:
            continue
    return rows


def native_protection_rows_for_trade(log_directory, trade, cache):
    entry_local = trade["entry_utc"].astimezone().replace(tzinfo=None)
    date_keys = {
        (entry_local + timedelta(seconds=offset)).strftime("%Y%m%d")
        for offset in (-NATIVE_PROTECTION_WINDOW_SECONDS, NATIVE_PROTECTION_WINDOW_SECONDS)
    }
    rows = []
    for date_key in sorted(date_keys):
        if date_key not in cache:
            cache[date_key] = read_native_protection_log_day(log_directory, date_key)
        rows.extend(cache[date_key])
    return entry_local, rows


def native_follower_protection_submitted(log_directory, trade, account, cache):
    entry_signal = COPY_ENTRY_SIGNAL_PATTERN.match(str(trade.get("entry_signal") or ""))
    if entry_signal is None:
        return False
    entry_local, rows = native_protection_rows_for_trade(log_directory, trade, cache)
    correlation = entry_signal.group("correlation").lower()
    instrument = _instrument_root(trade.get("instrument"))
    pairs = {}
    for row in rows:
        if str(row.get("account", "")).lower() != account.lower():
            continue
        if row.get("instrument_root") != instrument or row.get("correlation") != correlation:
            continue
        if abs((row["recorded_local"] - entry_local).total_seconds()) > NATIVE_PROTECTION_WINDOW_SECONDS:
            continue
        pair = pairs.setdefault(row["oco"], {})
        role = row["role"]
        pair[role] = max(int(pair.get(role, 0)), int(row["quantity"]))
    protected_quantity = sum(
        min(pair.get("S", 0), pair.get("T", 0))
        for pair in pairs.values()
    )
    return protected_quantity >= int(abs(trade.get("contracts") or 0)) > 0


def initial_native_risk(entry_price, quantity, fields, point_value):
    if not isinstance(point_value, (int, float)) or point_value <= 0:
        return [], None, "native_point_value_missing"
    legs = []
    remaining = int(quantity)
    for index in range(1, 4):
        stop = _float(fields, f"sl{index}")
        leg_quantity = int(_float(fields, f"leg{index}_qty", 0) or 0)
        if index == 1 and leg_quantity <= 0 and stop is not None:
            leg_quantity = remaining
        if stop is None or leg_quantity <= 0:
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


def _match_ledger_trades(ledger, expected_accounts, bracket_by_account, intent, correlation, journal):
    instrument = _instrument_root(intent.get("instrument", "MNQ"))
    side = "long" if intent.get("action") == "ENTER_LONG" else "short"
    matched = {}
    master = str(intent.get("account") or "")
    master_bracket = bracket_by_account.get(master.lower())
    if master_bracket is None:
        return None

    follower_protection = {}
    for row in journal:
        if str(row.get("category", "")).lower() != "replication":
            continue
        fields = message_fields(row.get("message"))
        if fields.get("result") not in {"submitted", "accepted"}:
            continue
        entry_signal = str(fields.get("entry") or "").strip()
        account = str(row.get("account") or "").strip()
        if entry_signal and account:
            follower_protection[(account.lower(), entry_signal.lower())] = row

    for account in expected_accounts:
        account_key = account.lower()
        has_account_bracket = account_key in bracket_by_account
        bracket_event, bracket_fields = bracket_by_account.get(account_key, master_bracket)
        bracket_time = parse_utc(bracket_event["recorded_utc"])
        bracket_fill = _float(bracket_fields, "fill") if has_account_bracket else None
        candidates = []
        for trade in ledger:
            if str(trade.get("account", "")).lower() != account_key:
                continue
            if _instrument_root(trade.get("instrument")) != instrument:
                continue
            if str(trade.get("side", "")).lower() != side:
                continue
            delta_seconds = abs((trade["entry_utc"] - bracket_time).total_seconds())
            if delta_seconds > 30:
                continue
            if bracket_fill is not None and abs(trade["entry_price"] - bracket_fill) > 2:
                continue
            if account_key == master.lower() and correlation:
                identity = "|".join(str(trade.get(key) or "") for key in (
                    "trade_id", "open_reason", "entry_signal", "exit_signal"
                )).lower()
                if correlation.lower() not in identity:
                    continue
            price_distance = abs(trade["entry_price"] - bracket_fill) if bracket_fill is not None else 0
            candidates.append((delta_seconds, price_distance, trade["exit_utc"], trade["trade_id"], trade))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[:4])
        matched[account.lower()] = candidates[0][4]
    return matched, follower_protection


def attribute_native_terminal_events(executions, by_intent, trade_ledger=None):
    """Bind EXIT-intent native fills back to the open ENTER lifecycle."""
    open_entries = {}
    seen_executions = set()
    ledger_exit_by_entry = {}
    for trade in trade_ledger or []:
        account = str(trade.get("account") or "").lower()
        instrument = _instrument_root(trade.get("instrument"))
        exit_utc = trade.get("exit_utc")
        if not account or not instrument or not isinstance(exit_utc, datetime):
            continue
        for field in ("entry_signal", "entry_order_identity"):
            native_order = str(trade.get(field) or "").strip().lower()
            if native_order:
                ledger_exit_by_entry[(account, instrument, native_order)] = exit_utc
    for row in sorted(executions, key=lambda value: str(value.get("recorded_utc") or "")):
        code = str(row.get("code") or "")
        if code != "master_entry_fill_observed" and code not in MASTER_TERMINAL_CODES:
            continue
        fields = message_fields(row.get("message"))
        account = str(fields.get("account") or "").lower()
        instrument = _instrument_root(fields.get("contract"))
        execution_id = str(fields.get("execution_id") or "").strip()
        if not account or not instrument:
            continue
        identity = (account, instrument, execution_id)
        if execution_id and identity in seen_executions:
            continue
        if execution_id:
            seen_executions.add(identity)
        quantity = abs(_float(fields, "signed_quantity", 0) or 0)
        if quantity <= 0:
            continue
        key = (account, instrument)
        intent_id = str(row.get("intent_id") or "")
        if code == "master_entry_fill_observed":
            entries = open_entries.setdefault(key, [])
            try:
                entry_utc = parse_utc(row.get("recorded_utc"))
            except (TypeError, ValueError):
                entry_utc = None
            if entry_utc is not None:
                entries[:] = [
                    entry for entry in entries
                    if entry.get("ledger_exit_utc") is None
                    or entry["ledger_exit_utc"] > entry_utc
                ]
            current = next(
                (entry for entry in entries if entry["intent_id"] == intent_id), None
            )
            if current is None:
                native_order = str(fields.get("native_order") or "").strip().lower()
                current = {
                    "intent_id": intent_id,
                    "quantity": 0.0,
                    "ledger_exit_utc": ledger_exit_by_entry.get(
                        (account, instrument, native_order)
                    ),
                }
                entries.append(current)
            current["quantity"] += quantity
            continue

        entries = open_entries.get(key, [])
        if not entries:
            continue
        remaining = quantity
        native_sign = 1 if (_float(fields, "signed_quantity", 0) or 0) > 0 else -1
        last_attributed = None
        while entries and remaining > 1e-9:
            current = entries[0]
            allocated = min(current["quantity"], remaining)
            attributed = dict(row)
            attributed["_source_intent_id"] = intent_id
            attributed["_attributed_signed_quantity"] = native_sign * allocated
            if current["intent_id"] == intent_id:
                row["_attributed_signed_quantity"] = native_sign * allocated
                last_attributed = row
            else:
                by_intent.setdefault(current["intent_id"], []).append(attributed)
                last_attributed = attributed
            current["quantity"] -= allocated
            remaining -= allocated
            if current["quantity"] <= 1e-9:
                entries.pop(0)
        if remaining > 1e-9 and last_attributed is not None:
            last_attributed["_unallocated_signed_quantity"] = native_sign * remaining
        if not entries:
            open_entries.pop(key, None)


def reconcile(glitch_data, evidence_root, output_path, decision_root=None, decision_log=None):
    executions = read_jsonl(glitch_data / "intents" / "executions.jsonl")
    intents = find_intents(evidence_root, decision_root, decision_log)
    trade_ledger = read_trade_ledger(glitch_data / "TradeLedger.tsv")
    journal = read_journal(glitch_data / "Journal.tsv")
    native_protection_log = glitch_data.parent / "log"
    native_protection_cache = {}
    existing = {str(row.get("intent_id")): row for row in read_jsonl(output_path) if row.get("intent_id")}
    by_intent = {}
    for row in executions:
        by_intent.setdefault(str(row.get("intent_id") or ""), []).append(row)
    attribute_native_terminal_events(executions, by_intent, trade_ledger)
    snapshots = portfolio_snapshots(
        glitch_data,
        reconciliation_snapshot_intervals(trade_ledger, intents, by_intent, existing),
    )
    market_frames = market_snapshot_rows(glitch_data)

    for intent_id, intent in intents.items():
        if intent.get("action") not in {"ENTER_LONG", "ENTER_SHORT"}:
            continue
        events = by_intent.get(intent_id, [])
        submitted = next((row for row in events if row.get("code") in {"master_entry_submitted", "group_entries_submitted"}), None)
        brackets = [row for row in events if row.get("code") in {
            "group_structural_brackets_submitted",
            "group_fill_anchored_brackets_submitted",
            "follower_structural_brackets_submitted",
        }]
        if not submitted or not brackets:
            continue

        master = str(intent.get("account") or "")
        submit_fields = message_fields(submitted.get("message"))
        expected_accounts = [value for value in submit_fields.get("expected_accounts", "").split(",") if value]
        if not expected_accounts:
            expected_accounts = parse_group_accounts_tsv(
                intent.get("_account_groups_tsv"), master
            )
        # Reconciliation must never pull a historical trade into a group that
        # the operator configured after that intent was sent.
        if not expected_accounts:
            continue
        bracket_by_account = {}
        for row in brackets:
            fields = message_fields(row.get("message"))
            account = fields.get("account") or (master if row.get("code") != "follower_structural_brackets_submitted" else None)
            if account:
                bracket_by_account[account.lower()] = (row, fields)
        if master.lower() not in bracket_by_account:
            continue

        correlation = submit_fields.get("correlation", "")
        matched = _match_ledger_trades(
            trade_ledger, expected_accounts, bracket_by_account, intent, correlation, journal
        )
        ledger_by_account, follower_protection = matched

        derived_master_trade = ledger_by_account.get(master.lower())
        master_bracket_event, master_bracket_fields = bracket_by_account[master.lower()]
        master_trade, native_outcome_reconciliation = native_master_trade_from_events(
            events,
            intent,
            master,
            master_bracket_event,
            master_bracket_fields,
            derived_master_trade,
        )
        if master_trade is None:
            continue
        ledger_by_account[master.lower()] = master_trade
        entry_utc = master_trade["entry_utc"]
        exit_utc = master_trade["exit_utc"]
        terminal_check_utc = max(row["exit_utc"] for row in ledger_by_account.values())
        terminal_utc = terminal_group_snapshot(snapshots, exit_utc, [master])
        if terminal_utc is None:
            continue
        group_terminal_utc = terminal_group_snapshot(snapshots, terminal_check_utc, expected_accounts)
        instrument_root = str(intent.get("instrument", "MNQ")).upper()
        account_outcomes = []
        incomplete_outcome = False
        process_error = group_terminal_utc is None
        replication_diagnostics = []
        for account in expected_accounts:
            trade = ledger_by_account.get(account.lower())
            if trade is None:
                process_error = True
                replication_diagnostics.append({
                    "account": account,
                    "status": "missing_round_trip",
                    "learning_role": "replication_only",
                })
                continue
            has_account_bracket = account.lower() in bracket_by_account
            _, fields = bracket_by_account.get(account.lower(), bracket_by_account[master.lower()])
            entry_price = trade["entry_price"]
            exit_price = trade["exit_price"]
            quantity = int(abs(trade["contracts"]) or 1)
            stop_price = _float(fields, "sl", _float(intent, "stop_loss"))
            target_price = _float(fields, "tp1", _float(intent, "take_profit_1"))
            point_value = _float(fields, "point_value_usd", _float(submit_fields, "point_value_usd"))
            tick_size = _float(fields, "tick_size", _float(submit_fields, "tick_size"))
            # TradeLedger pnl_points is already quantity-weighted by
            # GlitchTradeInsightsService as each closing fill is accumulated.
            if account.lower() == master.lower():
                pnl_usd = trade.get("realized_pnl_usd")
            else:
                pnl_usd = (
                    trade["pnl_points"] * point_value - trade["commission_total"]
                    if point_value is not None and point_value > 0
                    else None
                )
            protection_legs, initial_risk_usd, risk_status = initial_native_risk(
                entry_price, quantity, fields, point_value
            ) if has_account_bracket else ([], None, "native_follower_bracket_facts_missing")
            protection_evidence = "execution_receipt"
            protection_status = "submitted"
            if not has_account_bracket:
                entry_signal = str(trade.get("entry_signal") or "").lower()
                protection = follower_protection.get((account.lower(), entry_signal))
                if protection is not None and abs(
                    (protection["recorded_utc"] - trade["entry_utc"]).total_seconds()
                ) <= 5:
                    protection_evidence = "copy_engine_journal"
                elif native_follower_protection_submitted(
                    native_protection_log, trade, account, native_protection_cache
                ):
                    protection_evidence = "ninjatrader_daily_log"
                else:
                    protection_evidence = "unavailable"
                    protection_status = "unknown"
                    replication_diagnostics.append({
                        "account": account,
                        "status": "follower_protection_evidence_unknown",
                        "learning_role": "replication_only",
                    })
            account_outcomes.append({
                "account": account,
                "quantity": quantity,
                "entry_utc": trade["entry_utc"].isoformat().replace("+00:00", "Z"),
                "exit_utc": trade["exit_utc"].isoformat().replace("+00:00", "Z"),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "realized_pnl_usd": pnl_usd,
                "point_value_usd": point_value,
                "tick_size": tick_size,
                "instrument_economics_source": (
                    "native_execution_receipt"
                    if point_value is not None and point_value > 0 and tick_size is not None and tick_size > 0
                    else "unavailable"
                ),
                "initial_protection_legs": protection_legs,
                "initial_native_risk_usd": initial_risk_usd,
                "risk_normalization_status": risk_status,
                "risk_normalization_eligible": risk_status == "complete",
                "trade_id": trade["trade_id"],
                "trade_evidence_source": (
                    "intent_bound_native_execution_receipts"
                    if account.lower() == master.lower() else "derived_trade_ledger"
                ),
                "commission_status": trade.get("commission_status", "included_in_trade_ledger"),
                "protection_evidence": protection_evidence,
                "protection_status": protection_status,
                "close_kind": infer_close_kind(trade),
                **excursion(
                    snapshots, account, trade["entry_utc"], trade["exit_utc"],
                    instrument_root, pnl_usd if pnl_usd is not None else 0.0
                ),
            })
        if incomplete_outcome:
            continue

        master_outcome = next((row for row in account_outcomes if row["account"].lower() == master.lower()), None)
        if master_outcome is None:
            continue
        market_reference = market_snapshot_reference(
            glitch_data, entry_utc, instrument_root, market_frames
        )
        management_history = management_intent_counterfactuals(
            intents,
            snapshots,
            master,
            instrument_root,
            entry_utc,
            exit_utc,
            master_outcome.get("realized_pnl_usd"),
        )
        canonical_layers = canonical_outcome_layers(
            intent,
            master_outcome,
            submitted,
            master_bracket_event,
            market_reference,
            events,
            management_history,
        )
        master_learning_eligible = native_outcome_reconciliation["learning_eligible"] is True
        canonical_layers["attribution"]["master_learning_eligible"] = master_learning_eligible
        canonical_layers["attribution"]["native_outcome_reconciliation_status"] = (
            native_outcome_reconciliation["status"]
        )
        existing[intent_id] = {
            "schema_version": "glitch.hermes.trade_outcome.v1",
            "recorded_utc": exit_utc.isoformat().replace("+00:00", "Z"),
            "intent_id": intent_id,
            "cycle_id": intent.get("_cycle_id"),
            "origin": "ai",
            "route_id": intent.get("operator_profile"),
            "master_account": master,
            "instrument": instrument_root,
            "contract": submit_fields.get("contract"),
            "action": intent.get("action"),
            "confidence": intent.get("confidence"),
            "entry_utc": entry_utc.isoformat().replace("+00:00", "Z"),
            "exit_utc": exit_utc.isoformat().replace("+00:00", "Z"),
            "terminal_verified_utc": terminal_utc.isoformat().replace("+00:00", "Z"),
            "replication_terminal_verified_utc": (
                group_terminal_utc.isoformat().replace("+00:00", "Z")
                if group_terminal_utc is not None else None
            ),
            "planned_stop": intent.get("stop_loss"),
            "planned_target": intent.get("take_profit_1"),
            "reason": intent.get("reason"),
            "decision_audit": intent.get("decision_audit"),
            "account_outcomes": account_outcomes,
            "replication_diagnostics": replication_diagnostics,
            "master_realized_pnl_usd": master_outcome["realized_pnl_usd"],
            "group_realized_pnl_usd": (
                sum(row["realized_pnl_usd"] for row in account_outcomes)
                if all(row["realized_pnl_usd"] is not None for row in account_outcomes)
                else None
            ),
            "master_attribution_status": (
                "complete" if master_learning_eligible else "native_outcome_unreconciled"
            ),
            "master_learning_eligible": master_learning_eligible,
            "attribution_status": (
                "native_outcome_unreconciled"
                if not master_learning_eligible
                else "process_error" if process_error else "complete"
            ),
            "learning_eligible": master_learning_eligible,
            "native_outcome_reconciliation": native_outcome_reconciliation,
            "evidence": intent.get("_evidence_path"),
            "snapshot_reference": {
                "market": market_reference,
                "status": "complete" if market_reference else "unavailable",
            },
            **canonical_layers,
        }

    master_accounts = configured_master_accounts(glitch_data / "AccountGroups.tsv")
    for trade in trade_ledger:
        if master_accounts and str(trade.get("account") or "").lower() not in master_accounts:
            continue
        manual = manual_trade_outcome(
            glitch_data, snapshots, intents, trade, market_frames
        )
        if manual is not None:
            replace_manual_outcome(existing, manual, trade)

    ordered = sorted(existing.values(), key=lambda row: (row.get("exit_utc", ""), row.get("intent_id", "")))
    write_jsonl_atomic(output_path, ordered)
    return ordered


def process_is_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def process_start_utc(pid):
    if not isinstance(pid, int) or pid <= 0 or os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return datetime.fromtimestamp(
            (ticks - 116444736000000000) / 10_000_000,
            tz=timezone.utc,
        )
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def process_matches_owner(pid, started_utc):
    if not process_is_alive(pid):
        return False
    actual = process_start_utc(pid)
    if actual is None:
        return True
    try:
        recorded = parse_utc(started_utc)
    except (TypeError, ValueError):
        return False
    return abs((actual - recorded).total_seconds()) <= 30


def acquire_lock(path, unreadable_grace_seconds=15):
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = json.loads(path.read_text(encoding="utf-8"))
                if process_matches_owner(int(owner.get("pid", 0)), owner.get("started_utc")):
                    return False
                path.unlink()
                continue
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                if path.exists() and time.time() - path.stat().st_mtime <= unreadable_grace_seconds:
                    return False
                path.unlink(missing_ok=True)
                continue
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                started = process_start_utc(os.getpid())
                json.dump({
                    "pid": os.getpid(),
                    "started_utc": (started or datetime.now(timezone.utc)).isoformat(),
                }, stream)
                stream.flush()
                os.fsync(stream.fileno())
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--decision-root", type=Path)
    parser.add_argument("--decision-log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.evidence_root and not args.decision_root and not args.decision_log:
        parser.error("one of --evidence-root, --decision-root, or --decision-log is required")
    output = args.output or args.glitch_data / "intents" / "hermes-trade-outcomes.jsonl"
    lock_path = output.parent / "outcome-reconcile.lock"
    if not acquire_lock(lock_path):
        print(json.dumps({"schema_version": "glitch.hermes.outcome_reconcile.v1", "status": "owned_by_live_process"}))
        return
    try:
        rows = reconcile(
            args.glitch_data,
            args.evidence_root,
            output,
            args.decision_root,
            args.decision_log,
        )
        print(json.dumps({"schema_version": "glitch.hermes.outcome_reconcile.v1", "outcomes": len(rows), "output": str(output)}))
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
