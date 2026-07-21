"""Reconcile completed master/follower trades into Hermes learning outcomes.

The direct exchange outbox is the decision authority. NinjaTrader execution
events prove the AI-owned master lifecycle; CopyEngine Journal events prove
follower-native protection; TradeLedger.tsv proves each observed account round
trip. A complete terminal master trade is always attributable to Hermes.
Follower misses remain replication diagnostics and never erase master learning.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


POINT_VALUE = {"MNQ": 2.0}
DOTNET_EPOCH_TICKS = 621355968000000000


def parse_utc(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def read_trade_ledger(path):
    """Read Glitch's authoritative completed round trips.

    Followers are owned by GlitchCopyEngine, not GlitchAiOrderExecutor, so the
    AI execution journal intentionally has one group-close event rather than a
    fabricated close event per follower. TradeLedger.tsv is the account-level
    execution truth used to prove that every expected member actually closed.
    """
    if not path.exists():
        return []
    columns = [
        "trade_id", "entry_utc_ticks", "exit_utc_ticks", "account", "instrument",
        "side", "contracts", "entry_price", "exit_price", "pnl_points",
        "open_reason", "close_reason", "entry_session", "exit_session",
        "trade_source", "entry_type", "exit_type", "entry_signal", "exit_signal",
        "commission_total",
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


def _remember_intent(intents, row, evidence, cycle_id=None):
    if not isinstance(row, dict):
        return
    intent_id = str(row.get("intent_id") or "")
    if not intent_id:
        return
    value = dict(row)
    value["_evidence_path"] = str(evidence)
    value["_cycle_id"] = str(cycle_id or row.get("cycle_id") or "")
    intents[intent_id] = value


def find_intents(evidence_root=None, decision_root=None):
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
            for row in batch.get("decisions", []):
                _remember_intent(intents, row, path, cycle_id)
    return intents


def parse_group_accounts(path, master_account):
    groups = {}
    if not path.exists():
        return [master_account]
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
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
    return [master_account]


def portfolio_snapshots(glitch_data):
    snapshots = []
    root = glitch_data / "snapshots" / "historical" / "portfolio"
    for path in root.glob("*.json"):
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
    # Minute snapshots are lower-resolution than fills. Include flat-at-entry
    # and the realized terminal result so observed MFE cannot be negative and
    # observed MAE cannot be positive for trades that close between samples.
    values = [0.0, float(realized_pnl)]
    for stamp, snapshot in snapshots:
        if stamp < entry_utc or stamp > exit_utc:
            continue
        account_row = account_at(snapshot, account)
        if not account_row:
            continue
        for position in account_row.get("positions", []):
            if str(position.get("instrument_root", "")).upper() == instrument_root:
                values.append(float(position.get("unrealized_pnl", 0)))
    return {
        "observed_mfe_usd": max(values) if values else None,
        "observed_mae_usd": min(values) if values else None,
        "excursion_samples": max(0, len(values) - 2),
        "excursion_quality": "minute_unrealized_plus_terminal_bounds",
    }


def infer_close_kind(trade):
    exit_type = str(trade.get("exit_type") or "").strip().lower()
    exit_signal = str(trade.get("exit_signal") or "").strip()
    close_reason = str(trade.get("close_reason") or "").strip().lower()
    signal_parts = exit_signal.upper().split("-")
    signal_role = signal_parts[2] if len(signal_parts) > 2 else ""
    if "stop" in exit_type or "stop" in close_reason or signal_role == "S":
        return "stop"
    if "target" in exit_type or "target" in close_reason or signal_role == "T":
        return "target"
    if exit_type in {"exit", "manual", "close"} or exit_signal.lower() == "close" or "manual" in close_reason:
        return "managed_exit"
    return "unknown"


def _float(fields, key, fallback=None):
    try:
        return float(fields.get(key))
    except (TypeError, ValueError):
        return fallback


def _instrument_root(value):
    return str(value or "").split()[0].upper()


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
            if account_key == master.lower():
                return None
            continue
        candidates.sort(key=lambda item: item[:4])
        matched[account.lower()] = candidates[0][4]
    return matched, follower_protection


def reconcile(glitch_data, evidence_root, output_path, decision_root=None):
    executions = read_jsonl(glitch_data / "intents" / "executions.jsonl")
    intents = find_intents(evidence_root, decision_root)
    snapshots = portfolio_snapshots(glitch_data)
    trade_ledger = read_trade_ledger(glitch_data / "TradeLedger.tsv")
    journal = read_journal(glitch_data / "Journal.tsv")
    existing = {str(row.get("intent_id")): row for row in read_jsonl(output_path) if row.get("intent_id")}
    by_intent = {}
    for row in executions:
        by_intent.setdefault(str(row.get("intent_id") or ""), []).append(row)

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
            expected_accounts = parse_group_accounts(glitch_data / "AccountGroups.tsv", master)
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
        if matched is None:
            continue
        ledger_by_account, follower_protection = matched

        master_trade = ledger_by_account.get(master.lower())
        if master_trade is None:
            continue
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
            point_value = POINT_VALUE.get(instrument_root)
            if point_value is None:
                incomplete_outcome = True
                continue
            # TradeLedger pnl_points is already quantity-weighted by
            # GlitchTradeInsightsService as each closing fill is accumulated.
            pnl_usd = trade["pnl_points"] * point_value - trade["commission_total"]
            protection_evidence = "execution_receipt"
            protection_status = "submitted"
            if not has_account_bracket:
                entry_signal = str(trade.get("entry_signal") or "").lower()
                protection = follower_protection.get((account.lower(), entry_signal))
                if protection is not None and abs(
                    (protection["recorded_utc"] - trade["entry_utc"]).total_seconds()
                ) <= 5:
                    protection_evidence = "copy_engine_journal"
                else:
                    protection_evidence = "terminal_trade_ledger"
                    protection_status = "failed_or_missing"
                    process_error = True
            account_outcomes.append({
                "account": account,
                "quantity": quantity,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "realized_pnl_usd": pnl_usd,
                "trade_id": trade["trade_id"],
                "protection_evidence": protection_evidence,
                "protection_status": protection_status,
                "close_kind": infer_close_kind(trade),
                **excursion(snapshots, account, trade["entry_utc"], trade["exit_utc"], instrument_root, pnl_usd),
            })
        if incomplete_outcome:
            continue

        master_outcome = next((row for row in account_outcomes if row["account"].lower() == master.lower()), None)
        if master_outcome is None:
            continue
        existing[intent_id] = {
            "schema_version": "glitch.hermes.trade_outcome.v1",
            "recorded_utc": exit_utc.isoformat().replace("+00:00", "Z"),
            "intent_id": intent_id,
            "cycle_id": intent.get("_cycle_id"),
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
            "group_realized_pnl_usd": sum(row["realized_pnl_usd"] for row in account_outcomes),
            "master_attribution_status": "complete",
            "master_learning_eligible": True,
            "attribution_status": "process_error" if process_error else "complete",
            "learning_eligible": not process_error,
            "evidence": intent.get("_evidence_path"),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(existing.values(), key=lambda row: (row.get("exit_utc", ""), row.get("intent_id", "")))
    output_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in ordered), encoding="utf-8")
    return ordered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--decision-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.evidence_root and not args.decision_root:
        parser.error("one of --evidence-root or --decision-root is required")
    output = args.output or args.glitch_data / "intents" / "hermes-trade-outcomes.jsonl"
    rows = reconcile(args.glitch_data, args.evidence_root, output, args.decision_root)
    print(json.dumps({"schema_version": "glitch.hermes.outcome_reconcile.v1", "outcomes": len(rows), "output": str(output)}))


if __name__ == "__main__":
    main()
