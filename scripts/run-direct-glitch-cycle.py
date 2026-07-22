"""Hermes-owned adaptive-cadence Glitch operator cycle.

This is installed as a Hermes native cron script. It makes no model call until
Glitch has published a new complete rolling five-frame packet, resumes one persistent
Hermes session, contract-validates the returned batch, and posts each intent to
Glitch's existing authenticated firewall. Codex is not part of this process.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIONS = {"ENTER_LONG", "ENTER_SHORT", "HOLD", "MOVE_STOP", "MOVE_TP", "EXIT", "NOTHING"}
ACTION_ALIASES = {"NO_ACTION": "NOTHING"}
CORE_MODEL = "gpt-5.6-luna"
CORE_PROVIDER = "openai-codex"
TRADING_SOURCE = "trading"
REQUIRED_ENTRY_FIELDS = {"quantity", "order_type", "stop_loss", "take_profit_1"}
ENTRY_FIELDS = REQUIRED_ENTRY_FIELDS | {
    "take_profit_2", "stop_loss_2", "quantity_tp1",
    "take_profit_3", "stop_loss_3", "quantity_tp2",
}
MOVE_STOP_FIELDS = {"stop_loss"}
MOVE_TP_FIELDS = {"take_profit_1", "stop_loss"}
DECISION_FIELDS = {
    "schema_version", "intent_id", "created_utc", "instrument", "account",
    "operator_profile", "action", "confidence", "snapshot_hash", "model_version",
    "prompt_version", "reason", "decision_audit",
}
ALLOWED_DECISION_FIELDS = DECISION_FIELDS | ENTRY_FIELDS
DECISION_AUDIT_FIELDS = {
    "bull_case", "bear_case", "flat_case", "aggressive_case", "conservative_case",
    "decisive_evidence", "disconfirming_evidence", "change_condition", "final_choice",
}
DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
CURRENT_PLAN_SCHEMA = "glitch.hermes.portfolio_plan.v2"
CURRENT_GUIDANCE_SCHEMA = "glitch.hermes.trading_guidance.v2"
MNQ_POINT_VALUE_USD = 2.0
MNQ_TICK_SIZE = 0.25


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    # Windows PowerShell 5 writes a BOM for -Encoding UTF8. Exchange JSON is
    # still valid UTF-8 and must not stop the native trading loop.
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected_object:{path}")
    return value


def trading_runtime_enabled(glitch_data: Path) -> bool:
    """The runtime has one operational switch and one valid Glitch scope.

    This check happens before invoking Hermes so a paused or invalid runtime
    cannot spend a model call merely to have Glitch reject the result.
    """
    state_path = glitch_data / "hermes" / "control-state.json"
    policy_path = glitch_data / "ai" / "policy.json"
    if not state_path.is_file() or not policy_path.is_file():
        return False
    state = read_json(state_path)
    policy = read_json(policy_path)
    return state.get("trading_paused") is False and runtime_policy_is_valid(policy)


def runtime_policy_is_valid(policy: dict[str, Any]) -> bool:
    if policy.get("schema_version") != "glitch.ai.policy.v2":
        return False
    if "mode" in policy:
        return False
    snapshot_age = policy.get("snapshot_max_age_seconds")
    if not isinstance(snapshot_age, int) or isinstance(snapshot_age, bool) or not 1 <= snapshot_age <= 900:
        return False
    for key in (
        "profile_account_bindings", "instrument_allowlist", "account_allowlist", "blocked_sessions",
    ):
        if not isinstance(policy.get(key), list):
            return False
    return True


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, separators=(",", ":"), ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_event(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n")


def parse_groups(tsv: str, policy: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw_line in tsv.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if fields[0] == "G" and len(fields) >= 4:
            group_id, master, size = fields[1], fields[2], fields[3]
            groups[group_id] = {
                "group_id": group_id,
                "master_account": master,
                "master_size": float(size),
                "followers": [],
            }
            order.append(group_id)
        elif fields[0] == "M" and len(fields) >= 7 and fields[1] in groups:
            groups[fields[1]]["followers"].append({
                "account": fields[2],
                "account_size": float(fields[3]),
                "ratio": float(fields[4]),
                "enabled": fields[6].strip() == "1",
            })

    route_by_account: dict[str, str] = {}
    for binding in policy.get("profile_account_bindings", []):
        if isinstance(binding, str) and "=" in binding:
            route, account = binding.split("=", 1)
            route_by_account[account.strip()] = route.strip()

    books: list[dict[str, Any]] = []
    for group_id in order:
        group = groups[group_id]
        master = group["master_account"]
        route = route_by_account.get(master)
        if not route:
            # Groups without an explicit AI route remain visible but are not AI-controlled.
            continue
        books.append({
            "book_id": group_id,
            "route_id": route,
            "master_account": master,
            "master_size": group["master_size"],
            "followers": group["followers"],
        })
    return books


def _account_mnq_quantity(account: dict[str, Any]) -> int:
    total = 0
    positions = account.get("positions", [])
    if not isinstance(positions, list):
        return 0
    for position in positions:
        if not isinstance(position, dict):
            continue
        root = str(position.get("instrument_root") or position.get("instrument") or "").upper()
        if root != "MNQ":
            continue
        quantity = int(round(abs(float(position.get("quantity", 0) or 0))))
        side = str(position.get("market_position", "")).lower()
        total += -quantity if side == "short" else quantity if side == "long" else 0
    return total


def _account_total_contracts(account: dict[str, Any]) -> int:
    positions = account.get("positions", [])
    if not isinstance(positions, list):
        return 0
    return sum(
        int(round(abs(float(position.get("quantity", 0) or 0))))
        for position in positions
        if isinstance(position, dict)
    )


def _mnq_position(account: dict[str, Any]) -> dict[str, Any]:
    positions = account.get("positions", [])
    if not isinstance(positions, list):
        return {}
    return next((
        position for position in positions
        if isinstance(position, dict)
        and str(position.get("instrument_root") or position.get("instrument") or "").upper() == "MNQ"
    ), {})


def _remaining_order_quantity(order: dict[str, Any]) -> int | None:
    try:
        remaining = float(order.get("quantity", 0) or 0) - float(order.get("filled", 0) or 0)
    except (TypeError, ValueError):
        return None
    rounded = int(round(remaining))
    return rounded if remaining > 0 and abs(remaining - rounded) < 1e-9 else None


def owned_native_protection(account: dict[str, Any], current_price: float) -> dict[str, Any]:
    signed_quantity = _account_mnq_quantity(account)
    expected = abs(signed_quantity)
    orders = account.get("working_order_details")
    if not isinstance(orders, list):
        return {
            "status": "unavailable",
            "coverage_complete": False,
            "expected_quantity": expected,
            "stop_coverage_quantity": 0,
            "target_coverage_quantity": 0,
            "existing_protected_downside_usd": None,
            "orders": [],
        }

    stop_coverage = 0
    target_coverage = 0
    downside = 0.0
    compact_orders = []
    valid = True
    for order in orders:
        if not isinstance(order, dict):
            continue
        root = str(order.get("instrument_root") or order.get("instrument") or "").upper()
        name = str(order.get("name") or "")
        role = "stop" if name.upper().startswith("GLT-AI-S-") else "target" if name.upper().startswith("GLT-AI-T-") else None
        if root != "MNQ" or role is None:
            continue
        remaining = _remaining_order_quantity(order)
        if remaining is None:
            valid = False
            continue
        compact_orders.append({
            "name": name,
            "role": role,
            "remaining_quantity": remaining,
            "stop_price": order.get("stop_price"),
            "limit_price": order.get("limit_price"),
            "oco": order.get("oco"),
        })
        if role == "target":
            target_coverage += remaining
            continue
        try:
            stop_price = float(order.get("stop_price"))
        except (TypeError, ValueError):
            valid = False
            continue
        points = current_price - stop_price if signed_quantity > 0 else stop_price - current_price
        if expected and points <= 0:
            valid = False
            continue
        stop_coverage += remaining
        downside += max(0.0, points) * MNQ_POINT_VALUE_USD * remaining

    complete = valid and stop_coverage == expected and target_coverage == expected
    return {
        "status": "complete" if complete else "incomplete",
        "coverage_complete": complete,
        "expected_quantity": expected,
        "stop_coverage_quantity": stop_coverage,
        "target_coverage_quantity": target_coverage,
        "existing_protected_downside_usd": round(downside, 2) if valid else None,
        "orders": compact_orders,
    }


def entry_risk_legs(intent: dict[str, Any], current_price: float) -> list[dict[str, Any]]:
    quantity = intent.get("quantity")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise ValueError("entry_quantity_invalid")
    is_long = intent.get("action") == "ENTER_LONG"
    if not is_long and intent.get("action") != "ENTER_SHORT":
        raise ValueError("entry_action_invalid")
    stop_1 = float(intent["stop_loss"])
    has_second = "take_profit_2" in intent
    has_third = "take_profit_3" in intent
    quantity_1 = int(intent["quantity_tp1"]) if has_second else quantity
    quantity_2 = int(intent["quantity_tp2"]) if has_third else quantity - quantity_1 if has_second else 0
    quantity_3 = quantity - quantity_1 - quantity_2
    leg_specs = [(quantity_1, stop_1)]
    if has_second:
        stop_2 = float(intent.get("stop_loss_2", stop_1))
        leg_specs.append((quantity_2, stop_2))
    if has_third:
        stop_3 = float(intent.get("stop_loss_3", intent.get("stop_loss_2", stop_1)))
        leg_specs.append((quantity_3, stop_3))

    legs = []
    for index, (leg_quantity, stop_price) in enumerate(leg_specs, start=1):
        points = current_price - stop_price if is_long else stop_price - current_price
        if leg_quantity < 1 or points <= 0:
            raise ValueError("entry_risk_not_computable")
        legs.append({
            "leg": index,
            "quantity": leg_quantity,
            "stop_price": stop_price,
            "risk_points_per_contract": points,
            "planned_risk_usd": points * MNQ_POINT_VALUE_USD * leg_quantity,
        })
    return legs


def validate_apex_survival(intent: dict[str, Any], book: dict[str, Any], current_price: float) -> None:
    context = book.get("position_building_context")
    if not isinstance(context, dict) or context.get("account_survival_scope_known") is not True:
        raise ValueError("account_rule_state_missing")
    if context.get("apex_legacy_survival_applicable") is not True:
        return
    protection = context.get("native_protection")
    if not isinstance(protection, dict) or protection.get("coverage_complete") is not True:
        raise ValueError("apex_existing_protection_incomplete")
    buffer_margin = context.get("liquidation_buffer_usd")
    existing = protection.get("existing_protected_downside_usd")
    if not isinstance(buffer_margin, (int, float)) or isinstance(buffer_margin, bool) or buffer_margin <= 0:
        raise ValueError("apex_liquidation_buffer_missing")
    if not isinstance(existing, (int, float)) or isinstance(existing, bool) or existing < 0:
        raise ValueError("apex_existing_protected_downside_missing")
    proposed = sum(leg["planned_risk_usd"] for leg in entry_risk_legs(intent, current_price))
    if existing + proposed >= float(buffer_margin):
        raise ValueError("apex_liquidation_buffer_exceeded")


def add_group_exposure_context(packet: dict[str, Any], books: list[dict[str, Any]], current_price: float) -> None:
    """Derive Hermes capacity from the master only.

    Followers remain visible replication context, but user-owned ratios and
    follower-local limits never change what Hermes may do on the master.
    """
    frames = packet.get("frames")
    latest = frames[-1] if isinstance(frames, list) and frames else {}
    portfolio = latest.get("portfolio_snapshot") if isinstance(latest, dict) else {}
    accounts = portfolio.get("accounts") if isinstance(portfolio, dict) else []
    by_name = {
        str(account.get("account")): account
        for account in accounts
        if isinstance(account, dict) and account.get("account")
    }

    for book in books:
        members = [{
            "account": book["master_account"],
            "account_size": book["master_size"],
            "ratio": 1.0,
            "role": "master",
        }]
        members.extend({
            "account": follower["account"],
            "account_size": follower.get("account_size", book["master_size"]),
            "ratio": float(follower["ratio"]),
            "role": "follower",
        } for follower in book["followers"] if follower["enabled"])

        exposure: list[dict[str, Any]] = []
        for member in members:
            observed = by_name.get(member["account"], {})
            ceiling = int(round(float(observed.get("max_contracts", 0) or 0)))
            current = _account_mnq_quantity(observed)
            total_contracts = _account_total_contracts(observed)
            remaining = max(0, ceiling - total_contracts)
            exposure.append({
                **member,
                "current_mnq_quantity": current,
                "current_total_contracts": total_contracts,
                "prop_firm_id": observed.get("prop_firm_id"),
                "rule_status": observed.get("rule_status") or observed.get("account_status"),
                "prop_contract_ceiling": ceiling,
                "remaining_account_capacity": remaining,
                "working_orders": observed.get("working_orders"),
                "native_state_available": observed.get("native_state_available"),
                "is_risk_locked": observed.get("is_risk_locked"),
                "is_eval_target_locked": observed.get("is_eval_target_locked"),
                "entry_window_open": observed.get("entry_window_open"),
            })

        master = exposure[0]
        upper_bound = max(0, int(master["prop_contract_ceiling"]) - int(master["current_total_contracts"]))
        valid_quantities = list(range(1, upper_bound + 1))
        book["exposure"] = exposure
        book["valid_entry_quantities"] = valid_quantities
        book["effective_master_remaining_capacity"] = max(valid_quantities, default=0)
        observed_master = by_name.get(book["master_account"], {})
        position = _mnq_position(observed_master)
        protection = owned_native_protection(observed_master, current_price)
        book["position_building_context"] = {
            "instrument": "MNQ",
            "point_value_usd": MNQ_POINT_VALUE_USD,
            "tick_size": MNQ_TICK_SIZE,
            "account_size": observed_master.get("account_size", book["master_size"]),
            "equity": observed_master.get("equity"),
            "liquidation_threshold": observed_master.get("liquidation_threshold"),
            "liquidation_buffer_usd": observed_master.get("buffer_margin"),
            "drawdown_headroom_ratio": observed_master.get("headroom_ratio"),
            "max_drawdown": observed_master.get("max_drawdown"),
            "prop_firm_id": master.get("prop_firm_id"),
            "rule_status": master.get("rule_status"),
            "current_signed_quantity": master["current_mnq_quantity"],
            "current_average_price": position.get("average_price"),
            "current_total_contracts": master["current_total_contracts"],
            "contract_ceiling": master["prop_contract_ceiling"],
            "valid_entry_quantities": valid_quantities,
            "next_entry_role": "initial_position" if master["current_mnq_quantity"] == 0 else "same_direction_addition",
            "native_protection": protection,
            "account_survival_scope_known": bool(master.get("prop_firm_id") and master.get("rule_status")),
            "apex_legacy_survival_applicable": (
                str(master.get("prop_firm_id") or "").lower() == "apextraderfunding"
                and str(master.get("rule_status") or "").lower() == "eval"
            ),
        }


def latest_market(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    frames = packet.get("frames")
    if not isinstance(frames, list) or len(frames) != 5:
        raise ValueError("packet_requires_exactly_five_frames")
    latest_frame = frames[-1]
    market = latest_frame.get("market_snapshot") if isinstance(latest_frame, dict) else None
    if not isinstance(market, dict):
        raise ValueError("latest_market_snapshot_missing")
    instruments = market.get("instruments")
    if not isinstance(instruments, list):
        raise ValueError("market_instruments_missing")
    mnq = next((item for item in instruments if isinstance(item, dict) and item.get("instrument") == "MNQ"), None)
    if mnq is None:
        mnq = next((item for item in instruments if isinstance(item, dict) and item.get("instrument_root") == "MNQ"), None)
    if not isinstance(mnq, dict):
        raise ValueError("mnq_missing")
    snapshot_hash = market.get("snapshot_hash")
    if not snapshot_hash:
        raise ValueError("snapshot_hash_missing")
    return market, mnq


def _is_current_utc_record(line: str, today: str) -> bool:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(value, dict):
        return False
    for key in ("recorded_utc", "created_utc", "entry_utc", "exit_utc"):
        raw = value.get(key)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat() == today
            except ValueError:
                continue
    return False


def _is_learning_eligible_outcome(line: str) -> bool:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and value.get(
        "master_learning_eligible",
        value.get("learning_eligible", True),
    ) is not False


def journal_tail(glitch_data: Path, max_lines: int = 6) -> dict[str, list[str]]:
    today = datetime.now(timezone.utc).date().isoformat()
    result: dict[str, list[str]] = {"received": [], "decisions": []}
    executions = glitch_data / "intents" / "executions.jsonl"
    execution_lines = executions.read_text(encoding="utf-8", errors="replace").splitlines() if executions.is_file() else []
    result["executions"] = [
        line for line in execution_lines if _is_current_utc_record(line, today)
    ][-max_lines:]

    decisions = glitch_data / "intents" / "decisions.jsonl"
    decision_lines = decisions.read_text(encoding="utf-8", errors="replace").splitlines() if decisions.is_file() else []
    result["decisions"] = [
        line for line in decision_lines if _is_current_utc_record(line, today)
    ][-max_lines:]

    outcomes = glitch_data / "intents" / "hermes-trade-outcomes.jsonl"
    outcome_lines = outcomes.read_text(encoding="utf-8", errors="replace").splitlines() if outcomes.is_file() else []
    result["outcomes"] = [line for line in outcome_lines if _is_learning_eligible_outcome(line)][-max_lines:]
    # Journal.tsv is a long-lived human ledger. It remains on disk and in
    # Hermes memory, but is deliberately excluded from the active entry gate;
    # current-day execution/outcome JSONL is the authoritative capacity input.
    result["journal"] = []
    return result


def read_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        return read_json(path) if path.is_file() else None
    except (OSError, ValueError):
        return None


def read_current_learning_artifact(path: Path, schema_version: str) -> dict[str, Any] | None:
    value = read_optional_json(path)
    return value if value and value.get("schema_version") == schema_version else None


def learning_context(exchange: Path) -> dict[str, Any]:
    supervisor = exchange / "hermes" / "supervisor"
    overlay = read_optional_json(supervisor / "active-cognitive-overlay.json")
    if not overlay or overlay.get("status") not in {"active", "promoted"} or not overlay.get("instruction"):
        overlay = None
    return {
        "current_plan": read_current_learning_artifact(
            supervisor / "current-plan.json", CURRENT_PLAN_SCHEMA
        ),
        "current_guidance": read_current_learning_artifact(
            supervisor / "current-guidance.json", CURRENT_GUIDANCE_SCHEMA
        ),
        "active_cognitive_overlay": overlay,
    }


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def active_trade_state(
    packet: dict[str, Any],
    scenario: dict[str, Any],
    glitch_data: Path,
    exchange: Path,
) -> dict[str, Any]:
    """Materialize bounded, authoritative open-trade continuity for Hermes."""
    frames = packet.get("frames")
    latest = frames[-1] if isinstance(frames, list) and frames and isinstance(frames[-1], dict) else {}
    portfolio = latest.get("portfolio_snapshot")
    accounts = portfolio.get("accounts") if isinstance(portfolio, dict) else []
    by_name = {
        str(account.get("account")): account
        for account in accounts if isinstance(account, dict) and account.get("account")
    }
    decisions = _jsonl_objects(glitch_data / "intents" / "decisions.jsonl")
    executions = _jsonl_objects(glitch_data / "intents" / "executions.jsonl")
    outcomes = _jsonl_objects(glitch_data / "intents" / "hermes-trade-outcomes.jsonl")
    closed_entries = {str(row.get("intent_id")) for row in outcomes if row.get("intent_id")}
    submitted_entries = {
        str(row.get("intent_id")) for row in executions
        if row.get("code") in {"master_entry_submitted", "group_entries_submitted"}
    }
    previous_path = exchange / "hermes" / "supervisor" / "active-trades.json"
    previous = read_optional_json(previous_path) or {}
    previous_by_account = {
        str(row.get("master_account")): row
        for row in previous.get("trades", []) if isinstance(row, dict)
    }
    now = datetime.now(timezone.utc)
    trades = []
    for book in scenario.get("books", []):
        master = str(book.get("master_account") or "")
        account = by_name.get(master, {})
        net = _account_mnq_quantity(account)
        if net == 0:
            continue
        side = "long" if net > 0 else "short"
        position = next((
            row for row in account.get("positions", [])
            if isinstance(row, dict)
            and str(row.get("instrument_root") or "").upper() == "MNQ"
        ), {})
        open_entries = []
        management = []
        for row in decisions:
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
            if str(intent.get("account")) != master:
                continue
            action = str(intent.get("action") or "")
            intent_id = str(intent.get("intent_id") or "")
            if action in {"ENTER_LONG", "ENTER_SHORT"} and intent_id in submitted_entries and intent_id not in closed_entries:
                if (action == "ENTER_LONG") == (side == "long"):
                    open_entries.append(intent)
            elif action in {"HOLD", "MOVE_STOP", "MOVE_TP", "EXIT"}:
                management.append(intent)
        entry_ids = [str(row.get("intent_id")) for row in open_entries]
        prior = previous_by_account.get(master, {})
        same_trade = prior.get("entry_intent_ids") == entry_ids and prior.get("side") == side
        unrealized = float(position.get("unrealized_pnl", 0) or 0)
        peak = max(float(prior.get("peak_unrealized_pnl_usd", unrealized) or unrealized), unrealized) if same_trade else unrealized
        trough = min(float(prior.get("trough_unrealized_pnl_usd", unrealized) or unrealized), unrealized) if same_trade else unrealized
        created_values = [str(row.get("created_utc")) for row in open_entries if row.get("created_utc")]
        entry_utc = min(created_values) if created_values else str(prior.get("entry_decision_utc") or "")
        if entry_utc:
            management = [row for row in management if str(row.get("created_utc") or "") >= entry_utc]
        try:
            age_seconds = max(0, int((now - datetime.fromisoformat(entry_utc.replace("Z", "+00:00"))).total_seconds()))
        except (TypeError, ValueError):
            age_seconds = None
        orders = [
            row for row in account.get("working_order_details", [])
            if isinstance(row, dict) and str(row.get("instrument_root") or "").upper() == "MNQ"
        ]
        trades.append({
            "master_account": master,
            "route_id": book.get("route_id"),
            "instrument": "MNQ",
            "side": side,
            "quantity": abs(net),
            "average_price": position.get("average_price"),
            "unrealized_pnl_usd": unrealized,
            "peak_unrealized_pnl_usd": peak,
            "trough_unrealized_pnl_usd": trough,
            "rollback_from_peak_usd": peak - unrealized,
            "entry_decision_utc": entry_utc or None,
            "trade_age_seconds": age_seconds,
            "entry_intent_ids": entry_ids,
            "entry_plans": [{
                "intent_id": row.get("intent_id"),
                "quantity": row.get("quantity"),
                "planned_stop": row.get("stop_loss"),
                "planned_targets": [row.get(key) for key in ("take_profit_1", "take_profit_2", "take_profit_3") if row.get(key) is not None],
                "reason": row.get("reason"),
            } for row in open_entries],
            "working_orders": orders,
            "recent_management": [{
                "intent_id": row.get("intent_id"),
                "created_utc": row.get("created_utc"),
                "action": row.get("action"),
                "stop_loss": row.get("stop_loss"),
                "take_profit_1": row.get("take_profit_1"),
                "reason": row.get("reason"),
            } for row in management[-20:]],
        })
    value = {
        "schema_version": "glitch.hermes.active_trade_state.v1",
        "recorded_utc": utc_now(),
        "trades": trades,
    }
    write_json_atomic(previous_path, value)
    return value


def reconcile_completed_outcomes(glitch_data: Path, exchange: Path) -> None:
    reconciler = Path(__file__).with_name("reconcile-hermes-outcomes.py")
    if not reconciler.is_file():
        raise FileNotFoundError("outcome_reconciler_missing")
    completed = subprocess.run(
        [
            sys.executable,
            str(reconciler),
            "--glitch-data",
            str(glitch_data),
            "--decision-root",
            str(exchange / "hermes" / "outbox"),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("outcome_reconcile_failed:" + (completed.stderr or completed.stdout).strip())


def read_operator_directive(exchange: Path) -> dict[str, Any] | None:
    path = exchange / "hermes" / "operator-directive.json"
    if not path.is_file():
        return None
    directive = read_json(path)
    if directive.get("schema_version") != "glitch.operator.directive.v1":
        return None
    if directive.get("status") != "pending":
        return None
    raw_expiry = str(directive.get("expires_utc", ""))
    if raw_expiry:
        expires = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expires:
            directive["status"] = "expired"
            directive["expired_utc"] = utc_now()
            write_json_atomic(path, directive)
            return None
    return directive


def consume_operator_directive(exchange: Path, directive: dict[str, Any], packet_id: str) -> bool:
    path = exchange / "hermes" / "operator-directive.json"
    if not path.is_file():
        return False
    current = read_json(path)
    if (
        current.get("schema_version") != "glitch.operator.directive.v1"
        or current.get("status") != "pending"
        or current.get("directive_id") != directive.get("directive_id")
    ):
        return False
    consumed = dict(current)
    consumed["status"] = "consumed"
    consumed["consumed_utc"] = utc_now()
    consumed["consumed_packet_id"] = packet_id
    write_json_atomic(path, consumed)
    return True


def outbox_context_path(exchange: Path, packet_id: str) -> Path:
    return exchange / "hermes" / "outbox-context" / f"{packet_id}.json"


def model_attempt_path(exchange: Path, packet_id: str) -> Path:
    return exchange / "hermes" / "model-attempts" / f"{packet_id}.json"


def persist_outbox(
    exchange: Path,
    outbox_path: Path,
    packet_id: str,
    batch: dict[str, Any],
    directive: dict[str, Any] | None,
) -> None:
    if directive is not None:
        write_json_atomic(outbox_context_path(exchange, packet_id), {
            "schema_version": "glitch.hermes.outbox_context.v1",
            "cycle_id": packet_id,
            "directive_id": directive.get("directive_id"),
        })
    write_json_atomic(outbox_path, batch)


def consume_outbox_directive(exchange: Path, packet_id: str) -> bool:
    context_path = outbox_context_path(exchange, packet_id)
    if not context_path.is_file():
        return False
    context = read_json(context_path)
    if (
        context.get("schema_version") != "glitch.hermes.outbox_context.v1"
        or context.get("cycle_id") != packet_id
        or not context.get("directive_id")
    ):
        raise ValueError("outbox_context_invalid")
    return consume_operator_directive(
        exchange,
        {"directive_id": context["directive_id"]},
        packet_id,
    )


def build_scenario(packet: dict[str, Any]) -> dict[str, Any]:
    policy = packet.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("policy_missing")
    books = parse_groups(str(packet.get("account_groups_tsv", "")), policy)
    if not books:
        raise ValueError("no_route_bound_groups")
    market, mnq = latest_market(packet)
    current_price = float(mnq.get("current_price"))
    add_group_exposure_context(packet, books, current_price)
    return {
        "cycle_id": packet["packet_id"],
        "packet_hash": packet.get("packet_hash"),
        "market": {
            "instrument": "MNQ",
            "current_price": mnq.get("current_price"),
            "snapshot_hash": market["snapshot_hash"],
        },
        "books": books,
    }


def validate_batch(
    batch: dict[str, Any],
    scenario: dict[str, Any],
    directive: dict[str, Any] | None = None,
) -> None:
    unknown_batch_fields = set(batch).difference(
        {"schema_version", "cycle_id", "next_review_seconds", "decisions"}
    )
    if unknown_batch_fields:
        raise ValueError("batch_unknown_fields:" + ",".join(sorted(unknown_batch_fields)))
    if batch.get("schema_version") != "glitch.intent.batch.v1":
        raise ValueError("batch_schema_version_invalid")
    if batch.get("cycle_id") != scenario["cycle_id"]:
        raise ValueError("cycle_id_mismatch")
    if batch.get("next_review_seconds", 300) not in {60, 300}:
        raise ValueError("next_review_seconds_invalid")
    decisions = batch.get("decisions")
    books = scenario["books"]
    if not isinstance(decisions, list) or len(decisions) != len(books):
        raise ValueError("decision_count_mismatch")
    seen_routes: set[str] = set()
    snapshot_hash = scenario["market"]["snapshot_hash"]
    for index, (book, intent) in enumerate(zip(books, decisions)):
        if not isinstance(intent, dict):
            raise ValueError(f"intent_contract_incomplete:{index}:not_object")
        missing = sorted(DECISION_FIELDS.difference(intent))
        if missing:
            raise ValueError(f"intent_contract_incomplete:{index}:{','.join(missing)}")
        unknown = sorted(set(intent).difference(ALLOWED_DECISION_FIELDS))
        if unknown:
            raise ValueError(f"intent_unknown_fields:{index}:{','.join(unknown)}")
        if intent.get("schema_version") != "glitch.intent.v2":
            raise ValueError(f"intent_schema_version_invalid:{index}")
        for field in (
            "intent_id", "created_utc", "instrument", "account", "operator_profile",
            "snapshot_hash", "model_version", "prompt_version", "reason",
        ):
            if not isinstance(intent.get(field), str) or not intent[field].strip():
                raise ValueError(f"intent_string_invalid:{index}:{field}")
        try:
            datetime.fromisoformat(intent["created_utc"].replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"intent_created_utc_invalid:{index}") from error
        confidence = intent.get("confidence")
        if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
                or not math.isfinite(float(confidence)) or not 0 <= confidence <= 1):
            raise ValueError(f"intent_confidence_invalid:{index}")
        audit = intent.get("decision_audit")
        if not isinstance(audit, dict) or set(audit) != DECISION_AUDIT_FIELDS:
            raise ValueError(f"decision_audit_contract_invalid:{index}")
        if any(not isinstance(audit[field], str) or not audit[field].strip()
               for field in DECISION_AUDIT_FIELDS):
            raise ValueError(f"decision_audit_value_invalid:{index}")
        route = intent.get("operator_profile")
        if route in seen_routes:
            raise ValueError("duplicate_route")
        seen_routes.add(route)
        if route != book["route_id"] or intent.get("account") != book["master_account"]:
            raise ValueError(f"book_scope_violation:{index}")
        if intent.get("instrument") != "MNQ" or intent.get("snapshot_hash") != snapshot_hash:
            raise ValueError(f"market_scope_violation:{index}")
        action = intent.get("action")
        if action not in ACTIONS:
            raise ValueError(f"action_invalid:{index}")
        if audit["final_choice"] != action:
            raise ValueError(f"decision_audit_choice_mismatch:{index}")
        if action in {"ENTER_LONG", "ENTER_SHORT"}:
            if not REQUIRED_ENTRY_FIELDS.issubset(intent) or intent.get("order_type") != "MARKET":
                raise ValueError(f"protected_market_entry_required:{index}")
            quantity = intent.get("quantity")
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                raise ValueError(f"entry_quantity_invalid:{index}")
            if quantity not in book.get("valid_entry_quantities", []):
                raise ValueError(f"entry_quantity_exceeds_group_capacity:{index}")
            if "take_profit_2" in intent:
                quantity_tp1 = intent.get("quantity_tp1")
                if (quantity < 2 or not isinstance(quantity_tp1, int)
                        or isinstance(quantity_tp1, bool) or quantity_tp1 < 1 or quantity_tp1 >= quantity):
                    raise ValueError(f"entry_quantity_split_invalid:{index}")
                if "take_profit_3" in intent:
                    quantity_tp2 = intent.get("quantity_tp2")
                    if (quantity < 3 or not isinstance(quantity_tp2, int)
                            or isinstance(quantity_tp2, bool) or quantity_tp2 < 1
                            or quantity_tp1 + quantity_tp2 >= quantity):
                        raise ValueError(f"entry_three_leg_quantity_split_invalid:{index}")
                elif "quantity_tp2" in intent or "stop_loss_3" in intent:
                    raise ValueError(f"entry_third_leg_incomplete:{index}")
            elif "quantity_tp1" in intent or "stop_loss_2" in intent:
                raise ValueError(f"entry_second_leg_incomplete:{index}")
            if "take_profit_3" in intent and "take_profit_2" not in intent:
                raise ValueError(f"entry_third_leg_requires_second:{index}")
            try:
                validate_apex_survival(intent, book, float(scenario["market"]["current_price"]))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"entry_survival_invalid:{index}:{error}") from error
        elif action == "MOVE_STOP":
            if not isinstance(intent.get("stop_loss"), (int, float)) or isinstance(intent.get("stop_loss"), bool):
                raise ValueError(f"move_stop_price_required:{index}")
            if any(field in intent for field in ENTRY_FIELDS.difference(MOVE_STOP_FIELDS)):
                raise ValueError(f"move_stop_contains_entry_fields:{index}")
        elif action == "MOVE_TP":
            if (not isinstance(intent.get("take_profit_1"), (int, float))
                    or isinstance(intent.get("take_profit_1"), bool)):
                raise ValueError(f"move_tp_price_required:{index}")
            if ("stop_loss" in intent
                    and (not isinstance(intent.get("stop_loss"), (int, float))
                         or isinstance(intent.get("stop_loss"), bool))):
                raise ValueError(f"move_tp_stop_price_invalid:{index}")
            if any(field in intent for field in ENTRY_FIELDS.difference(MOVE_TP_FIELDS)):
                raise ValueError(f"move_tp_contains_entry_fields:{index}")
        elif any(field in intent for field in ENTRY_FIELDS):
            raise ValueError(f"non_entry_contains_entry_fields:{index}")
    if directive and directive.get("directive_type") == "forced_entry":
        expected = "ENTER_LONG" if directive.get("bias") == "long" else "ENTER_SHORT"
        if any(intent.get("action") != expected for intent in decisions):
            raise ValueError(f"operator_forced_entry_not_honored:{expected}")


def normalize_batch(batch: dict[str, Any], scenario: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map the model's documented no-action synonym onto the wire enum."""
    if scenario is not None:
        batch.setdefault("schema_version", "glitch.intent.batch.v1")
        batch.setdefault("cycle_id", scenario["cycle_id"])
    batch.setdefault("next_review_seconds", 300)
    decisions = batch.get("decisions")
    if not isinstance(decisions, list) and isinstance(batch.get("intents"), list):
        decisions = batch.pop("intents")
        batch["decisions"] = decisions
    if not isinstance(decisions, list):
        return batch
    for intent in decisions:
        if isinstance(intent, dict):
            try:
                uuid.UUID(str(intent.get("intent_id", "")))
            except (ValueError, TypeError, AttributeError):
                route = str(intent.get("operator_profile", "unknown"))
                cycle = str(batch.get("cycle_id") or (scenario or {}).get("cycle_id") or "unknown")
                intent["intent_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch:{cycle}:{route}"))
            action = intent.get("action")
            if action in ACTION_ALIASES:
                action = ACTION_ALIASES[action]
                intent["action"] = action
            if action == "MOVE_STOP":
                for field in ENTRY_FIELDS.difference(MOVE_STOP_FIELDS):
                    intent.pop(field, None)
            elif action == "MOVE_TP":
                for field in ENTRY_FIELDS.difference(MOVE_TP_FIELDS):
                    intent.pop(field, None)
            elif action not in {"ENTER_LONG", "ENTER_SHORT"}:
                for field in ENTRY_FIELDS:
                    intent.pop(field, None)
    if scenario is not None:
        ordered: list[dict[str, Any]] = []
        for book in scenario["books"]:
            matches = [
                intent for intent in decisions
                if isinstance(intent, dict)
                and intent.get("operator_profile") == book["route_id"]
                and intent.get("account") == book["master_account"]
            ]
            if len(matches) != 1:
                break
            ordered.append(matches[0])
        if len(ordered) == len(scenario["books"]):
            batch["decisions"] = ordered
    return batch


def packet_for_model(packet: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """Expose only current routes, truthful observation semantics, and Glitch limits."""
    model_packet = json.loads(json.dumps(packet))
    policy = model_packet.get("policy")
    if not isinstance(policy, dict):
        return model_packet
    policy.pop("mode", None)
    policy.pop("max_trades_per_day", None)
    policy.pop("cooldown_after_loss_minutes", None)
    policy.pop("paper_daily_profit_objective_usd", None)
    # AI Auto is the operational authority. Do not expose the retired file
    # flag because it can contradict the live control state.
    policy.pop("ai_enabled", None)
    for legacy_key in (
        "max_contracts",
        "max_risk_per_contract_usd",
        "max_loss_per_trade_usd",
        "max_group_loss_per_trade_usd",
        "max_daily_loss_usd",
    ):
        policy.pop(legacy_key, None)
    scoped_accounts: list[str] = []
    for book in scenario["books"]:
        scoped_accounts.append(book["master_account"])
        scoped_accounts.extend(
            follower["account"] for follower in book["followers"] if follower["enabled"]
        )
    scoped_account_set = set(scoped_accounts)
    frames = model_packet.get("frames", [])
    for frame_index, frame in enumerate(frames):
        market = frame.get("market_snapshot") if isinstance(frame, dict) else None
        if isinstance(market, dict):
            market["instruments"] = [
                instrument for instrument in market.get("instruments", [])
                if isinstance(instrument, dict)
                and str(instrument.get("instrument") or instrument.get("instrument_root")) == "MNQ"
            ]
            market["coverage"] = [
                item for item in market.get("coverage", [])
                if isinstance(item, dict) and item.get("instrument_root") == "MNQ"
            ]
            market["instrument_count"] = len(market["instruments"])
        portfolio = frame.get("portfolio_snapshot") if isinstance(frame, dict) else None
        if not isinstance(portfolio, dict):
            continue
        # Account state is authoritative only in the current frame. Repeating
        # the same account/risk payload five times bloats the persistent Hermes
        # session and contributed directly to compaction failures. The five
        # MNQ market frames still preserve price path; the latest portfolio
        # preserves current positions, orders, risk, and capacity.
        if frame_index < len(frames) - 1:
            frame.pop("portfolio_snapshot", None)
            continue
        portfolio["accounts"] = [
            account for account in portfolio.get("accounts", [])
            if isinstance(account, dict) and account.get("account") in scoped_account_set
        ]
        portfolio["account_count"] = len(portfolio["accounts"])
    model_packet["observation_contract"] = {
        "timeframe_rows": "live_in_progress_observations",
        "utc_time": "observation_time_not_bar_close_time",
        "timeframe_roles": {
            "1m": "entry_timing_and_noise",
            "5m": "local_setup_and_timing",
            "15m": "regime_context",
            "60m": "regime_context",
        },
        "decision_horizon": "next_5m_when_flat; next_1m_when_positioned",
        "confirmation": "probabilistic_from_the_five_frame_path; closed_candle_not_required",
        "missing_order_flow": "neutral_not_bearish_or_bullish",
        "warning": "Do not treat 5m, 15m, or 60m rows as completed-candle confirmation.",
    }
    policy["profile_account_bindings"] = [
        f'{book["route_id"]}={book["master_account"]}' for book in scenario["books"]
    ]
    policy["account_allowlist"] = list(dict.fromkeys(scoped_accounts))
    return model_packet


def extract_json(stdout: str, expected_schema_version: str | None = None) -> dict[str, Any]:
    text = stdout.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        try:
            value, end = decoder.raw_decode(text)
            trailing = text[end:].strip()
            if trailing and any(character not in "]}" for character in trailing):
                raise original_error
        except json.JSONDecodeError:
            candidates = []
            for index, character in enumerate(text):
                if character != "{":
                    continue
                try:
                    candidate, _ = decoder.raw_decode(text, index)
                except json.JSONDecodeError:
                    continue
                if not isinstance(candidate, dict):
                    continue
                schema_matches = (
                    candidate.get("schema_version") == expected_schema_version
                    if expected_schema_version
                    else candidate.get("schema_version") == "glitch.intent.batch.v1"
                        or isinstance(candidate.get("decisions"), list)
                        or isinstance(candidate.get("intents"), list)
                )
                if schema_matches:
                    candidates.append(candidate)
            if len(candidates) != 1:
                raise original_error
            value = candidates[0]
    if not isinstance(value, dict):
        raise ValueError("hermes_output_not_object")
    if expected_schema_version and value.get("schema_version") != expected_schema_version:
        raise ValueError("hermes_output_schema_mismatch")
    return value


def invoke_hermes(profile: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("hermes_executable_not_found")
    # Do not put the packet in argv. Windows has a finite process command-line
    # limit and the five-frame packet can exceed it before Hermes starts.
    # Invoke the installed Hermes Python runtime with a tiny wrapper and pass
    # the prompt over stdin instead; the wrapper reconstructs the same CLI
    # arguments inside the child process.
    python_executable = Path(executable).with_name("python.exe")
    if not python_executable.is_file():
        raise RuntimeError("hermes_python_runtime_not_found")
    # Each decision gets a fresh session tagged as trading. Continuity is
    # explicit in the bounded ledger/current packet and native durable memory,
    # so one oversized or failed turn cannot poison the next decision.
    cli_args = [
        "chat", "-Q",
        "--source", TRADING_SOURCE,
        "--model", CORE_MODEL,
        "--provider", CORE_PROVIDER,
        "--max-turns", "4",
        "--skills", "glitch-observe-market,glitch-assess-risk,glitch-form-thesis,glitch-build-intent,glitch-self-learning",
        "--toolsets", "memory",
    ]
    wrapper = (
        "import os,sys;"
        "from pathlib import Path;"
        "os.environ['HERMES_HOME']=str(Path.home() / 'AppData' / 'Local' / 'hermes' / 'profiles' / "
        + repr(profile)
        + ");"
        "from hermes_cli.main import main;"
        "prompt=sys.stdin.read();"
        "sys.argv=[sys.argv[0]] + " + repr(cli_args) + " + ['-q',prompt];"
        "main()"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    completed = subprocess.run(
        [str(python_executable), "-c", wrapper],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        creationflags=creationflags,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"hermes_failed:{completed.returncode}:{completed.stderr.strip()}")
    # Fresh-session stdout is the sole response; never recover from a globally
    # latest assistant message shared with other chats.
    return extract_json(completed.stdout, "glitch.intent.batch.v1")


def invoke_validated_batch(
    profile: str,
    prompt: str,
    scenario: dict[str, Any],
    directive: dict[str, Any] | None,
    timeout_seconds: int,
) -> tuple[dict[str, Any], int]:
    """Regenerate once when Luna's content, rather than its provider, is invalid."""
    for repair_count in range(2):
        try:
            batch = normalize_batch(invoke_hermes(profile, prompt, timeout_seconds), scenario)
            validate_batch(batch, scenario, directive)
            return batch, repair_count
        except ValueError as error:
            if repair_count:
                raise
            prompt += (
                "\nSTRICT_OUTPUT_CORRECTION="
                + json.dumps({
                    "validation_error": str(error)[:240],
                    "instruction": (
                        "Regenerate the same CURRENT_CYCLE decision from the supplied required_output_template. "
                        "Return one complete strict JSON object only; do not change cycle or scoped identities."
                    ),
                }, separators=(",", ":"))
            )
    raise AssertionError("unreachable")


def post_intent(intent: dict[str, Any], token: str) -> dict[str, Any]:
    body = json.dumps(intent, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:8788/intent",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return {"http_status": response.status, "body": json.loads(payload)}
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace")
        try:
            body_value: Any = json.loads(payload)
        except json.JSONDecodeError:
            body_value = payload
        return {"http_status": error.code, "body": body_value}


def submit_batch(batch: dict[str, Any], glitch_data: Path, exchange: Path) -> dict[str, Any]:
    token = (glitch_data / "telemetry.token").read_text(encoding="utf-8").strip()
    results: list[dict[str, Any]] = []
    complete = True
    for intent in batch["decisions"]:
        try:
            result = post_intent(intent, token)
        except Exception as error:  # network failure is retriable with the same intent IDs
            complete = False
            result = {"transport_error": str(error)}
        status = result.get("http_status") if isinstance(result, dict) else None
        if isinstance(status, int) and (status in {408, 425, 429} or status >= 500):
            complete = False
        results.append({"intent_id": intent["intent_id"], "result": result})
    receipt = {
        "schema_version": "glitch.hermes.delivery_receipt.v1",
        "recorded_utc": utc_now(),
        "cycle_id": batch["cycle_id"],
        "complete": complete,
        "results": results,
    }
    write_json_atomic(exchange / "hermes" / "receipts" / f"{batch['cycle_id']}.json", receipt)
    return receipt


def receipt_requires_new_packet_retry(receipt: dict[str, Any]) -> bool:
    for item in receipt.get("results", []):
        result = item.get("result") if isinstance(item, dict) else None
        body = result.get("body") if isinstance(result, dict) else None
        if isinstance(body, dict) and body.get("executor") == "failed":
            return True
    return not receipt.get("complete", False)


def build_prompt(
    packet: dict[str, Any],
    scenario: dict[str, Any],
    journals: dict[str, Any],
    directive: dict[str, Any] | None = None,
) -> str:
    decisions = []
    for book in scenario["books"]:
        exposure = book.get("exposure")
        master = exposure[0] if isinstance(exposure, list) and exposure else {}
        action = "HOLD" if int(master.get("current_mnq_quantity", 0) or 0) != 0 else "NOTHING"
        route = str(book["route_id"])
        decisions.append({
            "schema_version": "glitch.intent.v2",
            "intent_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch:{scenario['cycle_id']}:{route}")),
            "created_utc": utc_now(),
            "instrument": "MNQ",
            "account": str(book["master_account"]),
            "operator_profile": route,
            "action": action,
            "confidence": 0.5,
            "snapshot_hash": str(scenario["market"]["snapshot_hash"]),
            "model_version": CORE_MODEL,
            "prompt_version": "direct-v2",
            "reason": "Replace with the current evidence-based decision.",
            "decision_audit": {
                "bull_case": "Replace with compact bullish evidence.",
                "bear_case": "Replace with compact bearish evidence.",
                "flat_case": "Replace with compact neutral evidence.",
                "aggressive_case": "Replace with the aggressive alternative.",
                "conservative_case": "Replace with the conservative alternative.",
                "decisive_evidence": "Replace with the most likely near-term path.",
                "disconfirming_evidence": "Replace with evidence against that path.",
                "change_condition": "Replace with the concrete reassessment trigger.",
                "final_choice": action,
            },
        })
    output_template = {
        "schema_version": "glitch.intent.batch.v1",
        "cycle_id": scenario["cycle_id"],
        "next_review_seconds": 60 if scoped_master_is_positioned(packet, scenario) else 300,
        "decisions": decisions,
    }
    envelope = {
        "decision_packet": packet_for_model(packet, scenario),
        "execution_scope": scenario,
        "recent_glitch_ledger": journals,
        "operator_advisory": directive,
        "required_output_template": output_template,
    }
    return (
        "Apply the Glitch SOUL and the five loaded trading skills to CURRENT_CYCLE. Glitch and NinjaTrader facts in the supplied "
        "packet and ledger outrank memory and interpretation. The timeframe rows are live in-progress observations: use 1m/5m "
        "for timing and noise, 15m/60m for regime context, and never treat a higher-timeframe row as a completed-candle confirmation. "
        "Confirmation is probabilistic: infer it from the five-frame price path and available structure; a closed candle is not required. "
        "Missing order flow is neutral, not evidence against a trade. When flat, predict and trade the most likely next five minutes, not "
        "the next fifteen. When positioned and reviewing each minute, predict the most likely next one-minute candle and manage the trade "
        "from that forecast, current structure, and risk. Avoid staying idle for too long: take a calculated-risk trade when current evidence "
        "offers positive expectancy, and do not let ordinary uncertainty become a permanent veto. Do not manufacture edge or force a trade. "
        "Mixed timeframes are normal; bounded experimentation may sample multiple valid setups without a trade quota or deterministic cooldown. After a stop, re-enter only "
        "when price or evidence has materially changed; a repeated thesis at nearly the same level is churn. State the most likely "
        "next-five-minute path in decisive_evidence and its concrete invalidation in change_condition. "
        "For entries, define structural invalidation before reward. Anchor every stop beyond a relevant recent pivot or swing, the actual "
        "invalidation, and observable noise rather than merely offsetting it from the immediate price; "
        "never compress a stop to create attractive R:R. Use realistic targets supported by the same horizon and regime. stop_loss and "
        "take_profit fields are absolute MNQ prices, not distances, and Glitch preserves them unless the live market has already crossed them. "
        "Choose quantity only from execution_scope.books[].valid_entry_quantities. Follower accounts and ratios are user-owned replication "
        "configuration: they never constrain cognition, strategy, or master quantity, and Glitch CopyEngine handles each follower independently. "
        "The long-run performance objective is approximately 0.4%-2% of master account size per trading day ($100-$500 on $25k; "
        "$1,000-$5,000 on $250k). Use it as long-run feedback for expectancy and master-quantity calibration, never as a trade quota, "
        "loss entitlement, forced per-trade sizing rule, or reason to manufacture a trade. Do not inherit any fixed or provisional quantity "
        "baseline from advisory plans: Hermes owns quantity from current evidence, structural risk, remaining opportunity, drawdown, and supplied valid quantities. "
        "When an entry is justified, use aggressive_case and conservative_case to compare one protected tranche, a multi-leg entry, "
        "reserving capacity for later evidence, a later independently protected addition, and leaving exposure unchanged. Choose freely; "
        "do not mechanically maximize size or default to one contract. A quantity of two or more may use TP2 plus quantity_tp1; "
        "Treat execution_scope as current capacity authority: a historical infrastructure or capacity rejection is not a continuing veto when "
        "the current book has valid_entry_quantities and current native state is eligible. "
        "a quantity of three or more may also use TP3 plus quantity_tp2. Each leg may have its own tighter initial stop, and every leg receives "
        "an independent native OCO pair. These native legs are the current scale-out mechanism; there is no partial-reduction action after entry. "
        "Same-direction protected tranches may add at favorable or adverse prices only when current evidence still supports the thesis, existing "
        "protection is complete, and the new tranche has its own protection. Never add merely because price moved against the position, to recover "
        "a loss, or through a mechanical grid or martingale rule; never reverse through an entry. "
        "Return exactly one glitch.intent.batch.v1 JSON object with one ordered glitch.intent.v2 decision per supplied book. "
        "Every decision must include exactly these core keys: "
        "schema_version, intent_id, created_utc, instrument, account, operator_profile, action, confidence, "
        "snapshot_hash, model_version, prompt_version, reason, decision_audit. Use only actions "
        "ENTER_LONG, ENTER_SHORT, HOLD, MOVE_STOP, MOVE_TP, EXIT, or NOTHING; NO_ACTION is accepted as NOTHING. "
        "decision_audit must be an object with bull_case, bear_case, flat_case, aggressive_case, "
        "conservative_case, decisive_evidence, disconfirming_evidence, change_condition, and final_choice; "
        "final_choice must appear exactly once, inside decision_audit only, and must equal action. final_choice is forbidden as a direct "
        "field of a decision. Start from required_output_template: preserve its object/array shape and exact scoped identity values, then "
        "replace its placeholder rationale and choose the evidence-based action and matching nested final_choice. For NOTHING, HOLD, and EXIT omit quantity, order_type, stop_loss, "
        "and take_profit_1. Keep reason to at most 24 words and each decision_audit value to at most 18 words. "
        "For ENTER_LONG/ENTER_SHORT use order_type=MARKET and include stop_loss/take_profit_1. Optional scale-out fields are "
        "take_profit_2, quantity_tp1, stop_loss_2, take_profit_3, quantity_tp2, and stop_loss_3. For MOVE_STOP include only "
        "stop_loss and tighten the active Glitch-owned native stops; never loosen risk. For MOVE_TP include take_profit_1 and optionally "
        "stop_loss: move every remaining Glitch-owned target to that absolute price and, when supplied, tighten every remaining stop. "
        "A MOVE_TP target may extend or reduce remaining opportunity but must stay on the live profit side. Echo cycle_id and account/operator_profile exactly. "
        "snapshot_hash must be a JSON string copied exactly from the MNQ market snapshot, even when it contains only digits. "
        "Use the top-level key decisions, never intents. Close every intent object before closing the decisions "
        "array. Before returning, silently verify that the entire response is one syntactically valid JSON object "
        "that a strict JSON parser can load. Return no markdown fences, commentary, or trailing text. "
        "For an open position, HOLD, MOVE_STOP, MOVE_TP, a same-direction entry, and EXIT are active management decisions; HOLD is not the default. "
        "Compare every valid action after meaningful favorable excursion, failed progress, objective rejection, pivot loss, or opportunity decay. "
        "A prior change_condition is an accountable forecast: current acceptance, rejection, structure, excursion, and changed evidence outrank "
        "a stale forecast or plan. When current evidence satisfies it, do not silently move the threshold or repeat the "
        "same HOLD thesis. Either choose the newly supported action or identify the genuinely new evidence that disproves the prior trigger. "
        "Separate current timing and management pivots from hard structural invalidation; an EXIT or amendment need not wait for the catastrophe stop. "
        "After a rejected amendment, reason immediately from the authoritative unchanged bracket. Compare excursion and rollback in initial-risk "
        "units, structure, volatility, and remaining opportunity rather than fixed dollar landmarks. Native "
        "brackets are catastrophe protection, not a substitute for active thesis review. You may persist only durable lessons supported "
        "by repeated completed outcomes; never "
        "store current positions, stale attempts, account eligibility, trade quotas, or temporary directives as memory. If "
        "operator_advisory has directive_type=forced_entry, this is an operator-directed experiment: when "
        "the supplied group is flat, you MUST emit ENTER_LONG for bias=long or ENTER_SHORT for bias=short and "
        "choose structure-aware native stop/target geometry within Glitch policy; market evidence informs geometry, "
        "confidence, and rationale but cannot change the requested direction to NOTHING. For an ordinary advisory, "
        "treat it as a soft one-cycle preference: consider it, explain agreement or disagreement in the audit, and "
        "never let it override market evidence, risk, bracket geometry, or Glitch policy. The current plan, guidance, active trade state, and "
        "active cognitive overlay in recent_glitch_ledger are Hermes-owned advisory continuity; use them when relevant and revise them when "
        "current evidence disagrees. Do not emit prose outside the required JSON or call execution or control tools. Before deciding, invoke "
        "native memory retrieval exactly once for relevant Glitch trading lessons, then return the strict intent JSON without writing memory. "
        "If operator_advisory has directive_type=native_tool_canary, the required retrieval also satisfies that diagnostic and must not bias the decision. "
        "Treat NinjaTrader/Glitch positions, orders, fills, balances, PnL, brackets, receipts, and outcomes as authoritative facts; "
        "memory and Hermes journals are interpretations. Never fabricate missing facts, hide a loss, reset a performance baseline, "
        "rewrite history, or mark a discrepancy resolved without current authoritative evidence. Preserve contradictions with "
        "append-only corrections and keep single outcomes episodic. Process defects are code evidence and never trading memory; "
        "then return the required strict JSON.\n"
        "CURRENT_CYCLE="
        + json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
    )


def packet_is_current(packet: dict[str, Any], max_age_seconds: int | None = None) -> bool:
    raw = str(packet.get("window_close_utc", ""))
    if not raw:
        return False
    if max_age_seconds is None:
        policy = packet.get("policy")
        configured = policy.get("snapshot_max_age_seconds", 180) if isinstance(policy, dict) else 180
        try:
            max_age_seconds = max(1, int(configured))
        except (TypeError, ValueError):
            max_age_seconds = 180
    closed = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    age = (datetime.now(timezone.utc) - closed).total_seconds()
    return -60 <= age <= max_age_seconds


def packet_window_utc(packet: dict[str, Any]) -> datetime:
    raw = str(packet.get("window_close_utc", ""))
    if raw:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    packet_id = str(packet.get("packet_id", ""))
    return datetime.strptime(packet_id, "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)


def scoped_master_is_positioned(packet: dict[str, Any], scenario: dict[str, Any]) -> bool:
    frames = packet.get("frames")
    if not isinstance(frames, list) or not frames:
        return False
    latest = frames[-1] if isinstance(frames[-1], dict) else {}
    portfolio = latest.get("portfolio_snapshot")
    accounts = portfolio.get("accounts") if isinstance(portfolio, dict) else None
    if not isinstance(accounts, list):
        return False
    masters = {book["master_account"] for book in scenario["books"]}
    for account in accounts:
        if not isinstance(account, dict) or account.get("account") not in masters:
            continue
        if _account_mnq_quantity(account) != 0:
            return True
    return False


def any_flat_book_is_entry_eligible(packet: dict[str, Any], scenario: dict[str, Any]) -> bool:
    frames = packet.get("frames")
    latest = frames[-1] if isinstance(frames, list) and frames and isinstance(frames[-1], dict) else {}
    portfolio = latest.get("portfolio_snapshot")
    if not isinstance(portfolio, dict):
        return False
    for book in scenario["books"]:
        exposure = book.get("exposure")
        if not isinstance(exposure, list) or not exposure or not book.get("valid_entry_quantities"):
            continue
        master = exposure[0]
        if int(master.get("current_mnq_quantity", 0)) != 0:
            continue
        if (master.get("entry_window_open") is not True
                or master.get("native_state_available") is not True
                or master.get("is_risk_locked") is not False
                or master.get("is_eval_target_locked") is not False
                or int(master.get("working_orders", 0) or 0) != 0):
            continue
        return True
    return False


def should_invoke_luna(
    packet: dict[str, Any],
    scenario: dict[str, Any],
    exchange: Path,
    directive: dict[str, Any] | None,
) -> bool:
    window = packet_window_utc(packet)
    positioned = scoped_master_is_positioned(packet, scenario)
    if not positioned and not any_flat_book_is_entry_eligible(packet, scenario):
        return False
    return (
        window.minute % 5 == 0
        or directive is not None
        or positioned
        or prior_failed_attempt_requires_retry(exchange, packet)
    )


def prior_failed_attempt_requires_retry(exchange: Path, packet: dict[str, Any]) -> bool:
    """Retry the latest failed decision on the next available pre-boundary packet."""
    attempts = exchange / "hermes" / "model-attempts"
    if not attempts.is_dir():
        return False
    current_window = packet_window_utc(packet)
    current_id = str(packet.get("packet_id", ""))
    for path in sorted(attempts.glob("*.json"), reverse=True):
        if path.stem >= current_id:
            continue
        try:
            prior_window = datetime.strptime(path.stem, "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)
            attempt = read_json(path)
        except (OSError, ValueError, TypeError):
            continue
        age = (current_window - prior_window).total_seconds()
        return attempt.get("status") in {"failed", "execution_failed", "delivery_incomplete"} and 0 < age < 300
    return False


def read_packet_after_imminent_rollover(packet_path: Path, wait_seconds: float) -> dict[str, Any]:
    """Avoid selecting the prior minute in the narrow publisher/cron race."""
    packet = read_json(packet_path)
    if wait_seconds <= 0 or not packet_is_current(packet):
        return packet
    try:
        created = datetime.fromisoformat(str(packet.get("created_utc", "")).replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds()
    except (TypeError, ValueError):
        return packet
    if age_seconds < 50:
        return packet
    packet_id = str(packet.get("packet_id", ""))
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        candidate = read_json(packet_path)
        if str(candidate.get("packet_id", "")) != packet_id:
            return candidate
    return packet


def wait_for_newer_packet(packet_path: Path, prior_packet_id: str, wait_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        try:
            candidate = read_json(packet_path)
            candidate_id = str(candidate.get("packet_id", ""))
            if candidate_id and candidate_id != prior_packet_id and packet_is_current(candidate):
                return True
        except (OSError, ValueError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.1, remaining))


def run_with_next_packet_fallback(args: argparse.Namespace, glitch_data: Path, exchange: Path) -> int:
    packet_path = exchange / "glitch" / "latest-decision-packet.json"
    try:
        prior_packet_id = str(read_json(packet_path).get("packet_id", ""))
    except (OSError, ValueError):
        prior_packet_id = ""
    try:
        result = run_once(args, glitch_data, exchange)
    except Exception:
        if wait_for_newer_packet(packet_path, prior_packet_id, args.error_retry_wait_seconds):
            return run_once(args, glitch_data, exchange)
        raise
    if result != 0 and wait_for_newer_packet(packet_path, prior_packet_id, args.error_retry_wait_seconds):
        return run_once(args, glitch_data, exchange)
    return result


def run_once(args: argparse.Namespace, glitch_data: Path, exchange: Path) -> int:
    if not trading_runtime_enabled(glitch_data):
        return 0

    packet_path = exchange / "glitch" / "latest-decision-packet.json"
    events_path = exchange / "hermes" / "events" / "cycles.jsonl"
    if not packet_path.is_file():
        return 0

    packet = read_packet_after_imminent_rollover(
        packet_path,
        float(getattr(args, "packet_rollover_wait_seconds", 0) or 0),
    )
    packet_id = str(packet.get("packet_id", ""))
    if not packet_id:
        raise ValueError("packet_id_missing")
    if not packet_is_current(packet):
        return 0
    receipt_path = exchange / "hermes" / "receipts" / f"{packet_id}.json"
    outbox_path = exchange / "hermes" / "outbox" / f"{packet_id}.json"
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        if receipt.get("complete"):
            return 0

    scenario = build_scenario(packet)
    trade_state = active_trade_state(packet, scenario, glitch_data, exchange)
    if outbox_path.is_file():
        batch = normalize_batch(read_json(outbox_path), scenario)
        validate_batch(batch, scenario)
        if args.dry_run:
            print(json.dumps({
                "cycle_id": packet_id,
                "decision_count": len(batch["decisions"]),
                "submitted": False,
                "reused_outbox": True,
            }))
            return 0
        consume_outbox_directive(exchange, packet_id)
        receipt = submit_batch(batch, glitch_data, exchange)
        print(json.dumps(receipt, separators=(",", ":")))
        return 0 if receipt["complete"] else 1
    if receipt_path.is_file():
        raise ValueError("receipt_without_outbox")

    directive = read_operator_directive(exchange)
    if not should_invoke_luna(packet, scenario, exchange, directive):
        return 0
    attempt_path = model_attempt_path(exchange, packet_id)
    if attempt_path.is_file():
        return 0
    reconcile_completed_outcomes(glitch_data, exchange)
    journals = journal_tail(glitch_data)
    journals.update(learning_context(exchange))
    journals["active_trade_state"] = trade_state
    prompt = build_prompt(packet, scenario, journals, directive)
    write_json_atomic(attempt_path, {
        "schema_version": "glitch.hermes.model_attempt.v1",
        "cycle_id": packet_id,
        "started_utc": utc_now(),
        "status": "started",
        "model": CORE_MODEL,
        "provider": CORE_PROVIDER,
        "hermes_session_source": TRADING_SOURCE,
        "hermes_session_mode": "isolated",
    })
    try:
        batch, output_repair_count = invoke_validated_batch(
            args.profile, prompt, scenario, directive, args.timeout_seconds
        )
        persist_outbox(exchange, outbox_path, packet_id, batch, directive)
        write_json_atomic(attempt_path, {
            "schema_version": "glitch.hermes.model_attempt.v1",
            "cycle_id": packet_id,
            "started_utc": read_json(attempt_path)["started_utc"],
            "completed_utc": utc_now(),
            "status": "decision_ready",
            "model": CORE_MODEL,
            "provider": CORE_PROVIDER,
            "hermes_session_source": TRADING_SOURCE,
            "hermes_session_mode": "isolated",
            "output_repair_count": output_repair_count,
        })
    except Exception as error:
        attempt = read_json(attempt_path)
        attempt["completed_utc"] = utc_now()
        attempt["status"] = "failed"
        attempt["error"] = f"{type(error).__name__}:{str(error)[:400]}"
        write_json_atomic(attempt_path, attempt)
        append_event(events_path, {
            "schema_version": "glitch.hermes.cycle_event.v1",
            "event": "decision_failed",
            "recorded_utc": utc_now(),
            "cycle_id": packet_id,
            "model": CORE_MODEL,
            "provider": CORE_PROVIDER,
            "hermes_session_source": TRADING_SOURCE,
            "hermes_session_mode": "isolated",
            "error": attempt["error"],
        })
        raise
    if directive and not args.dry_run:
        consume_operator_directive(exchange, directive, packet_id)
    append_event(events_path, {
        "schema_version": "glitch.hermes.cycle_event.v1",
        "event": "decision_ready",
        "recorded_utc": utc_now(),
        "cycle_id": packet_id,
        "decision_count": len(batch["decisions"]),
        "submitted": not args.dry_run,
    })
    if args.dry_run:
        print(json.dumps({"cycle_id": packet_id, "decision_count": len(batch["decisions"]), "submitted": False}))
        return 0
    receipt = submit_batch(batch, glitch_data, exchange)
    retry_on_next_packet = receipt_requires_new_packet_retry(receipt)
    if retry_on_next_packet:
        attempt = read_json(attempt_path)
        attempt["status"] = "execution_failed" if receipt.get("complete") else "delivery_incomplete"
        attempt["completed_utc"] = utc_now()
        write_json_atomic(attempt_path, attempt)
    print(json.dumps(receipt, separators=(",", ":")))
    return 1 if retry_on_next_packet else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, default=DEFAULT_GLITCH_DATA)
    parser.add_argument("--profile", default="glitch")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--packet-rollover-wait-seconds", type=float, default=5)
    parser.add_argument("--error-retry-wait-seconds", type=float, default=75)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    glitch_data = args.glitch_data.resolve()
    exchange = glitch_data / "hermes" / "exchange"
    lock_path = exchange / "hermes" / "direct-cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            stale_after = max(args.timeout_seconds * 2, 600)
            if time.time() - lock_path.stat().st_mtime <= stale_after:
                return 0
            lock_path.unlink()
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileNotFoundError, FileExistsError):
            return 0
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        return run_with_next_packet_fallback(args, glitch_data, exchange)
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"event": "direct_cycle_failed", "error": str(error)}), file=sys.stderr)
        raise SystemExit(1)
