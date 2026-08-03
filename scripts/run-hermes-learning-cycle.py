"""Hermes-owned Glitch debrief, supervision, planning, and learning loop.

The native 30-minute cron launches this slow worker in an independent process,
so learning can never occupy the minute operator's scheduler lane. It calls
Hermes only when new authoritative evidence makes a loop due. Every call uses
an isolated `trading` session and durable Glitch/Hermes stores provide
continuity; Codex is not in the runtime path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from win_subprocess import hermes_profile_lock, hide_flags, resolve_python_invocation


MODEL = "gpt-5.6-luna"
PROVIDER = "openai-codex"
SOURCE = "trading"
DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
EASTERN = ZoneInfo("America/New_York")
LOOP_SCHEMAS = {
    "debrief": "glitch.hermes.trade_episode.v1",
    "hourly": "glitch.hermes.hourly_review.v1",
    "planning": "glitch.hermes.portfolio_plan.v2",
    "daily": "glitch.hermes.daily_journal.v1",
    "weekly": "glitch.hermes.weekly_skill_proposal.v1",
}
MAX_DEBRIEF_OUTCOMES = 1
MAX_HOURLY_EVIDENCE = 24
MAX_PLANNING_REVIEWS = 6
MAX_PLANNING_EPISODES = 12
MAX_PROMPT_CHARS = 300_000

# Only market/geometry/capacity decisions belong in cognitive evidence. Missing
# services, stale state, policy/auth failures, and native API faults remain code
# evidence and must never teach Hermes a trading rule.
COGNITIVE_FIREWALL_REJECTIONS = {
    "bracket_invalid",
    "position_conflict",
    "max_contracts_exceeded",
    "apex_liquidation_buffer_exceeded",
    "account_risk_locked",
    "eval_target_locked",
}
COGNITIVE_EXECUTOR_REJECTIONS = {
    "group_structural_geometry_invalid_at_decision",
    "master_quantity_must_be_integer",
    "master_quantity_split_invalid",
    "master_three_leg_quantity_split_invalid",
    "opposite_position_exists",
    "master_contract_ceiling_exceeded",
    "apex_liquidation_buffer_exceeded",
    "move_stop_market_side_invalid",
    "move_tp_market_side_invalid",
    "move_tp_stop_market_side_invalid",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def load_direct_module():
    path = Path(__file__).with_name("run-direct-glitch-cycle.py")
    spec = importlib.util.spec_from_file_location("glitch_direct_cycle", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("direct_cycle_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIRECT = load_direct_module()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def append_unique(path: Path, records: list[dict[str, Any]], id_field: str) -> None:
    existing = {str(row.get(id_field)) for row in read_jsonl(path) if row.get(id_field)}
    for record in records:
        record_id = str(record.get(id_field) or "")
        if record_id and record_id not in existing:
            DIRECT.append_event(path, record)
            existing.add(record_id)


def process_text(value: Any) -> str:
    """Return captured child output safely even when Windows decoding failed."""
    return value if isinstance(value, str) else ""


def invoke_hermes(profile: str, prompt: str, skills: str, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("hermes_executable_not_found")
    python_executable = Path(executable).with_name("python.exe")
    if not python_executable.is_file():
        raise RuntimeError("hermes_python_runtime_not_found")
    resolved_python, env_overlay = resolve_python_invocation(str(python_executable))
    env = os.environ.copy()
    env.update(env_overlay)
    args = [
        "chat", "-Q", "--source", SOURCE,
        "--model", MODEL, "--provider", PROVIDER,
        "--max-turns", "8", "--skills", skills,
        "--toolsets", "memory",
    ]
    wrapper = (
        "import os,sys;from pathlib import Path;"
        "os.environ['HERMES_HOME']=str(Path.home()/'AppData'/'Local'/'hermes'/'profiles'/"
        + repr(profile)
        + ");from hermes_cli.main import main;prompt=sys.stdin.read();"
        "sys.argv=[sys.argv[0]]+" + repr(args) + "+['-q',prompt];main()"
    )
    with hermes_profile_lock(
        profile,
        timeout_seconds=min(timeout_seconds, 60),
        priority="background",
    ):
        completed = subprocess.run(
            [resolved_python, "-c", wrapper],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=env,
            creationflags=hide_flags(),
        )
    if completed.returncode != 0:
        stderr = process_text(completed.stderr)
        stdout = process_text(completed.stdout)
        raise RuntimeError(
            f"hermes_failed:{completed.returncode}:"
            f"stderr={stderr.strip()[-1200:]}:"
            f"stdout={stdout.strip()[-400:]}"
        )
    return DIRECT.extract_json(
        process_text(completed.stdout),
        "glitch.hermes.learning_output.v1",
    )


def bounded_learning_rows(
    rows: list[dict[str, Any]], max_rows: int, max_chars: int
) -> list[dict[str, Any]]:
    """Keep the newest complete records within the learner prompt budget."""
    selected: list[dict[str, Any]] = []
    used_chars = 0
    for row in reversed(rows):
        row_chars = len(json.dumps(row, separators=(",", ":"), ensure_ascii=False))
        if len(selected) >= max_rows or used_chars + row_chars > max_chars:
            break
        selected.append(row)
        used_chars += row_chars
    return list(reversed(selected))


def stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"glitch:{kind}:{value}"))


def market_path(glitch_data: Path, entry: datetime, exit_time: datetime) -> list[dict[str, Any]]:
    values = []
    root = glitch_data / "snapshots" / "historical" / "market"
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            row = DIRECT.read_json(path)
            stamp = parse_utc(row.get("created_utc"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if stamp > exit_time + timedelta(minutes=1):
            continue
        if stamp < entry - timedelta(minutes=1):
            break
        instruments = row.get("instruments")
        instrument = next((item for item in instruments or [] if item.get("instrument_root") == "MNQ" or item.get("instrument") == "MNQ"), None)
        if not isinstance(instrument, dict):
            continue
        one_minute = next((bar for bar in instrument.get("timeframe_bars", []) if bar.get("minutes") == 1), {})
        values.append({
            "created_utc": row.get("created_utc"),
            "price": instrument.get("current_price"),
            "open": one_minute.get("open"),
            "high": one_minute.get("high"),
            "low": one_minute.get("low"),
            "close": one_minute.get("close"),
            "atr": (one_minute.get("indicators") or {}).get("atr"),
            "directional_score": (one_minute.get("derived_analytics") or {}).get("directional_score"),
            "tradeability_score": (one_minute.get("derived_analytics") or {}).get("tradeability_score"),
        })
    return list(reversed(values[-90:]))


def entry_decision_context(
    glitch_data: Path,
    outcome: dict[str, Any],
    entry_intent: dict[str, Any] | None,
    master_result: dict[str, Any] | None,
) -> dict[str, Any]:
    cycle_id = str(outcome.get("cycle_id") or "")
    if not cycle_id or not isinstance(entry_intent, dict):
        return {"status": "unavailable", "reason": "entry_identity_missing"}
    packet_path = (
        glitch_data / "hermes" / "exchange" / "glitch" / "decision-packets" / f"{cycle_id}.json"
    )
    if not packet_path.is_file():
        return {"status": "unavailable", "reason": "decision_packet_missing", "cycle_id": cycle_id}
    try:
        packet = DIRECT.read_json(packet_path)
        if str(packet.get("packet_id") or "") != cycle_id:
            raise ValueError("decision_packet_identity_mismatch")
        scenario = DIRECT.build_scenario(packet)
        book = next(
            value for value in scenario["books"]
            if str(value.get("master_account") or "").lower()
            == str(outcome.get("master_account") or "").lower()
        )
        decision_reference_price = float(scenario["market"]["current_price"])
        legs = DIRECT.entry_risk_legs(entry_intent, decision_reference_price)
    except (KeyError, StopIteration, TypeError, ValueError, OSError) as error:
        return {"status": "unavailable", "reason": str(error)[:160], "cycle_id": cycle_id}

    targets = [
        entry_intent.get("take_profit_1"),
        entry_intent.get("take_profit_2"),
        entry_intent.get("take_profit_3"),
    ]
    for index, leg in enumerate(legs):
        leg["target_price"] = targets[index]
        leg["planned_risk_usd"] = round(float(leg["planned_risk_usd"]), 2)
        leg["risk_points_per_contract"] = round(float(leg["risk_points_per_contract"]), 8)
    decision_reference_risk = sum(float(leg["planned_risk_usd"]) for leg in legs)
    selected_quantity = int(entry_intent["quantity"])
    result = master_result or {}
    actual_entry_vwap = result.get("entry_price")
    initial_native_risk = result.get("initial_native_risk_usd")
    risk_normalization_eligible = (
        result.get("risk_normalization_status") == "complete"
        and isinstance(initial_native_risk, (int, float))
        and float(initial_native_risk) > 0
    )

    def per_contract(key: str) -> float | None:
        value = result.get(key)
        return round(float(value) / selected_quantity, 2) if isinstance(value, (int, float)) else None

    realized = result.get("realized_pnl_usd")
    if not isinstance(realized, (int, float)):
        realized = outcome.get("master_realized_pnl_usd")
    return {
        "status": "complete",
        "intent_id": str(entry_intent.get("intent_id") or outcome.get("intent_id") or ""),
        "master_account": str(outcome.get("master_account") or ""),
        "cycle_id": cycle_id,
        "packet_hash": packet.get("packet_hash"),
        "snapshot_hash": entry_intent.get("snapshot_hash") or scenario["market"].get("snapshot_hash"),
        "rationale": {
            "reason": entry_intent.get("reason"),
            "decision_audit": entry_intent.get("decision_audit"),
        },
        "pre_entry": book.get("position_building_context"),
        "decision_reference_price": decision_reference_price,
        "actual_entry_vwap": actual_entry_vwap,
        "selected_plan": {
            "action": entry_intent.get("action"),
            "quantity": selected_quantity,
            "entry_role": (book.get("position_building_context") or {}).get("next_entry_role"),
            "legs": legs,
            "decision_reference_risk_usd": round(decision_reference_risk, 2),
        },
        "native_entry_facts": {
            "point_value_usd": result.get("point_value_usd"),
            "tick_size": result.get("tick_size"),
            "instrument_economics_source": result.get("instrument_economics_source"),
            "initial_protection_legs": result.get("initial_protection_legs", []),
            "initial_native_risk_usd": initial_native_risk,
            "risk_normalization_status": result.get("risk_normalization_status", "unavailable"),
            "risk_normalization_eligible": risk_normalization_eligible,
        },
        "normalized_outcome": {
            "realized_pnl_per_contract_usd": (
                round(float(realized) / selected_quantity, 2)
                if isinstance(realized, (int, float)) else None
            ),
            "sampled_mfe_per_contract_usd": per_contract("sampled_mfe_usd"),
            "sampled_mae_per_contract_usd": per_contract("sampled_mae_usd"),
            "excursion_sampling_method": result.get("excursion_sampling_method"),
            "excursion_sample_count": result.get("excursion_sample_count"),
            "excursion_eligible": result.get("excursion_eligible") is True,
            "realized_r_multiple": (
                round(float(realized) / float(initial_native_risk), 4)
                if isinstance(realized, (int, float)) and risk_normalization_eligible else None
            ),
            "sampled_mfe_r": (
                round(float(result["sampled_mfe_usd"]) / float(initial_native_risk), 4)
                if isinstance(result.get("sampled_mfe_usd"), (int, float)) and risk_normalization_eligible else None
            ),
            "sampled_mae_r": (
                round(float(result["sampled_mae_usd"]) / float(initial_native_risk), 4)
                if isinstance(result.get("sampled_mae_usd"), (int, float)) and risk_normalization_eligible else None
            ),
            "close_kind": result.get("close_kind"),
        },
    }


def debrief_evidence(glitch_data: Path, outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = read_jsonl(glitch_data / "intents" / "decisions.jsonl")
    executions = read_jsonl(glitch_data / "intents" / "executions.jsonl")
    evidence = []
    for outcome in outcomes:
        entry = parse_utc(outcome["entry_utc"])
        exit_time = parse_utc(outcome["exit_utc"])
        account = str(outcome.get("master_account") or "")
        related_decisions = []
        for row in decisions:
            intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
            if str(intent.get("account") or "") != account:
                continue
            try:
                stamp = parse_utc(row.get("recorded_utc"))
            except (TypeError, ValueError):
                continue
            if entry - timedelta(seconds=90) <= stamp <= exit_time + timedelta(seconds=90):
                related_decisions.append(row)
        related_ids = {
            str(row.get("intent", {}).get("intent_id"))
            for row in related_decisions if isinstance(row.get("intent"), dict)
        }
        related_executions = [row for row in executions if str(row.get("intent_id")) in related_ids]
        master_result = next((
            row for row in outcome.get("account_outcomes", [])
            if str(row.get("account", "")).lower() == account.lower()
        ), None)
        entry_intent = next((
            row.get("intent") for row in decisions
            if isinstance(row.get("intent"), dict)
            and str(row["intent"].get("intent_id") or "") == str(outcome.get("intent_id") or "")
        ), None)
        master_outcome = {
            key: outcome.get(key)
            for key in (
                "schema_version", "recorded_utc", "intent_id", "cycle_id", "route_id",
                "master_account", "instrument", "contract", "action", "confidence",
                "entry_utc", "exit_utc", "terminal_verified_utc", "planned_stop",
                "planned_target", "reason", "decision_audit", "master_realized_pnl_usd",
                "master_attribution_status", "master_learning_eligible", "evidence",
            )
        }
        evidence.append({
            "expected_episode_id": stable_id("episode", str(outcome.get("intent_id"))),
            "master_outcome": master_outcome,
            "master_result": master_result,
            "entry_decision_context": entry_decision_context(
                glitch_data, outcome, entry_intent, master_result
            ),
            "management_decisions": related_decisions,
            "execution_events": related_executions,
            "market_path": market_path(glitch_data, entry, exit_time),
            "replication_diagnostics": outcome.get("replication_diagnostics", []),
        })
    return evidence


def _mnq_observation(frame: dict[str, Any]) -> dict[str, Any] | None:
    market = frame.get("market_snapshot") if isinstance(frame, dict) else None
    instruments = market.get("instruments") if isinstance(market, dict) else None
    instrument = next((
        row for row in instruments or []
        if isinstance(row, dict)
        and str(row.get("instrument") or row.get("instrument_root") or "").upper() == "MNQ"
    ), None)
    if not isinstance(instrument, dict):
        return None
    current = instrument.get("current_price")
    try:
        close = float(current)
    except (TypeError, ValueError):
        return None
    one_minute = next((
        row for row in instrument.get("timeframe_bars", [])
        if isinstance(row, dict) and int(row.get("minutes", 0) or 0) == 1
    ), {})
    def number(key: str, fallback: float) -> float:
        try:
            return float(one_minute.get(key, fallback))
        except (TypeError, ValueError):
            return fallback
    return {
        "minute_id": frame.get("minute_id"),
        "high": number("high", close),
        "low": number("low", close),
        "close": number("close", close),
    }


def is_cognitive_rejection(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    body = result.get("body")
    if not isinstance(body, dict):
        return False
    firewall_code = str(body.get("failed_check_code") or "")
    executor_code = str(body.get("executor_code") or "")
    return (
        firewall_code in COGNITIVE_FIREWALL_REJECTIONS
        or executor_code in COGNITIVE_EXECUTOR_REJECTIONS
    )


def collect_decision_episodes(
    glitch_data: Path,
    exchange: Path,
    supervisor: Path,
) -> list[dict[str, Any]]:
    output_path = supervisor / "decision-episodes.jsonl"
    existing = {str(row.get("intent_id")) for row in read_jsonl(output_path) if row.get("intent_id")}
    frames_root = exchange / "glitch" / "minute-frames"
    records: list[dict[str, Any]] = []
    for outbox_path in sorted((exchange / "hermes" / "outbox").glob("*.json")):
        cycle_id = outbox_path.stem
        packet_path = exchange / "glitch" / "decision-packets" / f"{cycle_id}.json"
        receipt_path = exchange / "hermes" / "receipts" / f"{cycle_id}.json"
        if not packet_path.is_file() or not receipt_path.is_file():
            continue
        try:
            packet = DIRECT.read_json(packet_path)
            batch = DIRECT.read_json(outbox_path)
            receipt = DIRECT.read_json(receipt_path)
            scenario = DIRECT.build_scenario(packet)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if DIRECT.receipt_classification(receipt) == "transport_uncertain":
            continue
        future_paths = [path for path in sorted(frames_root.glob("*.json")) if path.stem > cycle_id][:5]
        if len(future_paths) < 5:
            continue
        future = []
        try:
            for path in future_paths:
                observed = _mnq_observation(DIRECT.read_json(path))
                if observed is None:
                    raise ValueError("future_observation_missing")
                future.append(observed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        result_by_intent = {
            str(item.get("intent_id")): item.get("result")
            for item in receipt.get("results", []) if isinstance(item, dict)
        }
        books_by_route = {str(book.get("route_id")): book for book in scenario.get("books", [])}
        for intent in batch.get("decisions", []):
            if not isinstance(intent, dict):
                continue
            intent_id = str(intent.get("intent_id") or "")
            if not intent_id or intent_id in existing:
                continue
            action = str(intent.get("action") or "")
            book = books_by_route.get(str(intent.get("operator_profile") or ""), {})
            exposure = book.get("exposure") if isinstance(book, dict) else None
            master = exposure[0] if isinstance(exposure, list) and exposure else {}
            result = result_by_intent.get(intent_id)
            http_status = result.get("http_status") if isinstance(result, dict) else None
            body = result.get("body") if isinstance(result, dict) else None
            flat_nothing = action == "NOTHING" and int(master.get("current_mnq_quantity", 0) or 0) == 0
            relevant_failure = (
                action in {"ENTER_LONG", "ENTER_SHORT", "MOVE_STOP", "MOVE_TP"}
                and is_cognitive_rejection(result)
            )
            if not flat_nothing and not relevant_failure:
                continue
            try:
                initial = float(scenario["market"]["current_price"])
            except (KeyError, TypeError, ValueError):
                continue
            forward_high = max(row["high"] for row in future)
            forward_low = min(row["low"] for row in future)
            record = {
                "schema_version": "glitch.hermes.decision_episode.v1",
                "episode_id": stable_id("decision-episode", intent_id),
                "recorded_utc": utc_now(),
                "intent_id": intent_id,
                "cycle_id": cycle_id,
                "decision_utc": intent.get("created_utc"),
                "window_close_utc": packet.get("window_close_utc"),
                "route_id": intent.get("operator_profile"),
                "master_account": intent.get("account"),
                "instrument": intent.get("instrument"),
                "action": action,
                "reason": intent.get("reason"),
                "decision_audit": intent.get("decision_audit"),
                "pre_decision_state": {
                    "position": master,
                    "position_building_context": book.get("position_building_context"),
                    "available_quantities": book.get("valid_entry_quantities"),
                    "initial_price": initial,
                },
                "proposed_geometry": {
                    key: intent.get(key) for key in (
                        "quantity", "stop_loss", "take_profit_1", "take_profit_2",
                        "quantity_tp1", "stop_loss_2", "take_profit_3", "quantity_tp2",
                        "stop_loss_3", "protection_updates",
                    ) if key in intent
                },
                "receipt": result,
                "evidence_kind": "flat_nothing" if flat_nothing else "rejected_or_nonexecuted_intent",
                "forward_observation_count": len(future),
                "forward_observations": future,
                "forward_high": forward_high,
                "forward_low": forward_low,
                "forward_close": future[-1]["close"],
                "upward_excursion_points": forward_high - initial,
                "downward_excursion_points": initial - forward_low,
                "counterfactual_pnl": None,
                "classification": None,
                "classification_owner": "hermes",
            }
            records.append(record)
            existing.add(intent_id)
    append_unique(output_path, records, "episode_id")
    return read_jsonl(output_path)


def output_template(loop_id: str, record_ids: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    records = []
    for record_id in record_ids:
        if loop_id == "debrief":
            records.append({
                "schema_version": LOOP_SCHEMAS[loop_id],
                "episode_id": record_id,
                "recorded_utc": utc_now(),
                "intent_id": "COPY_FROM_EVIDENCE",
                "instrument": "MNQ",
                "master_account": "COPY_FROM_EVIDENCE",
                "entry_assessment": "REPLACE",
                "exit_assessment": "REPLACE",
                "what_went_well": ["REPLACE"],
                "what_went_wrong": ["REPLACE"],
                "geometry_assessment": "REPLACE",
                "management_assessment": "REPLACE",
                "quantity_assessment": "REPLACE",
                "market_behavior": "REPLACE",
                "lesson_candidates": ["REPLACE"],
                "uncertainties": ["REPLACE"],
            })
        else:
            id_field = {"hourly": "review_id", "planning": "plan_id", "daily": "journal_id", "weekly": "skill_proposal_id"}[loop_id]
            record = {
                "schema_version": LOOP_SCHEMAS[loop_id],
                id_field: record_id,
                "recorded_utc": utc_now(),
            }
            if loop_id == "hourly":
                record.update({
                    "working": ["REPLACE"], "failing": ["REPLACE"], "unknown": ["REPLACE"],
                    "repeated_patterns": ["REPLACE"], "system_findings": ["REPLACE"],
                    "candidate_lessons": [],
                    "guidance": {"summary": "REPLACE", "consider": ["REPLACE"], "avoid": ["REPLACE"]},
                    "cognitive_change_decision": {
                        "candidate_id": "COPY_ACTIVE_ID_OR_EMPTY", "action": "none",
                        "evidence_episode_ids": [], "contradiction_review": "REPLACE_OR_EMPTY",
                        "reason": "REPLACE_OR_EMPTY",
                    },
                    "cognitive_change_candidate": {
                        "propose": False, "candidate_id": "GENERATE_OR_EMPTY",
                        "operation": "replace", "target": "core_prompt",
                        "expected_old_text": "EXACT_CURRENT_TEXT_OR_EMPTY",
                        "replacement_text": "MINIMAL_REPLACEMENT_OR_EMPTY",
                        "evidence_episode_ids": [], "expected_effect": "REPLACE_OR_EMPTY",
                        "evaluation_metric": "REPLACE_OR_EMPTY", "rollback_condition": "REPLACE_OR_EMPTY",
                    },
                })
            elif loop_id == "planning":
                record.update({
                    "horizon_minutes": 360,
                    "performance_objective": "Pursue the proportional target without forcing trades.",
                    "regime_posture": "REPLACE", "objectives": ["REPLACE"],
                    "sizing_guidance": "REPLACE", "geometry_guidance": "REPLACE",
                    "management_guidance": "REPLACE", "experiments": ["REPLACE"],
                    "preservation_conditions": ["REPLACE"], "revision_triggers": ["REPLACE"],
                })
            elif loop_id == "daily":
                record.update({
                    "session_date_et": str((extra or {}).get(
                        "session_date_et", datetime.now(EASTERN).date().isoformat()
                    )),
                    "master_performance": "REPLACE", "what_worked": ["REPLACE"],
                    "what_failed": ["REPLACE"], "lessons_promoted": [],
                    "lessons_revised": [], "tomorrow_questions": ["REPLACE"],
                    "memory_updates": ["REPLACE_OR_EMPTY"],
                    "cognitive_change_decision": {
                        "candidate_id": "COPY_ACTIVE_ID_OR_EMPTY", "action": "none",
                        "evidence_episode_ids": [], "contradiction_review": "REPLACE_OR_EMPTY",
                        "reason": "REPLACE_OR_EMPTY",
                    },
                    "cognitive_change_candidate": {
                        "propose": False, "candidate_id": "GENERATE_OR_EMPTY",
                        "operation": "replace", "target": "core_prompt",
                        "expected_old_text": "EXACT_CURRENT_TEXT_OR_EMPTY",
                        "replacement_text": "MINIMAL_REPLACEMENT_OR_EMPTY",
                        "evidence_episode_ids": [], "expected_effect": "REPLACE_OR_EMPTY",
                        "evaluation_metric": "REPLACE_OR_EMPTY", "rollback_condition": "REPLACE_OR_EMPTY",
                    },
                })
            else:
                record.update({
                    "source_daily_journal_ids": [],
                    "distilled_lessons": ["REPLACE"],
                    "contradictions": ["REPLACE_OR_EMPTY"],
                    "skill_proposals": [],
                    "evaluation_plan": "REPLACE",
                })
            records.append(record)
    value = {"schema_version": "glitch.hermes.learning_output.v1", "loop_id": loop_id, "records": records}
    if extra:
        value.update({key: item for key, item in extra.items() if key != "session_date_et"})
    return value


def build_prompt(loop_id: str, evidence: Any, template: dict[str, Any], continuity: dict[str, Any]) -> str:
    loop_instruction = {
        "debrief": (
            "Produce exactly one honest human-trader debrief per supplied outcome. Attribute cognition and PnL to the master only; follower ratios and follower PnL are replication diagnostics. "
            "Every supplied master_outcome has master_learning_eligible=true; that field alone authorizes cognitive learning, and replication diagnostics can never suppress it. "
            "Reconstruct the pre-decision regime, why Hermes entered, why the trade actually exited, geometry versus pivots/volatility/liquidity/drift, quantity, every management decision, duration, favorable excursion/rollback, and plausible alternatives. "
            "Use entry_decision_context to judge whether quantity and position architecture were evidence-based or habitual, and whether native target legs, reserved capacity, "
            "or a later independently protected addition deserved consideration. Do not assume a different quantity would have received identical fills; preserve that uncertainty. "
            "A repeated stop geometry mistake is evidence for self-improvement, not permission to invent a fixed stop formula. Process errors are not strategy lessons."
        ),
        "hourly": (
            "Supervise the latest completed-trade and decision episodes. Classify NOTHING evidence as disciplined abstention, missed opportunity, or uncertainty; classify rejected intents as correct factual rejection, cognitive mistake, or uncertainty. "
            "For each flat NOTHING, preserve the developing movement, the observable condition or price that would have offered favorable participation, invalidation, and the later observed path. Label the actual outcome no trade and every counterfactual informational only. "
            "Never infer counterfactual PnL when target/stop ordering is unobserved. Infrastructure and transport failures are code evidence, never strategy memory. Identify repeated regime-conditioned reasoning, geometry relative to structure/ATR/drift, duration, churn, management, quantity, false abstention versus overtrading, and system defects. "
            "Issue advisory guidance, never an order. Decision episodes may improve questions and attention, but they may not create entry pressure, anti-abstention pressure, quantity pressure, or activate trading cognition. "
            "Attributable evidence may produce one compact versioned cognitive proposal now rather than waiting for the daily loop; proposal does not activate it. Preserve its uncertainty until later comparable completed master outcomes exist. "
            "For a proposed overlay, return activate or rollback only from later comparable completed master evidence and explicit contradiction review. "
            "For an active overlay, return promote, continue, or rollback from later comparable completed master evidence."
        ),
        "planning": (
            "Create the next six-hour Hermes plan. Hermes owns strategy and master quantity under the operator capacity mandate. Set regime questions, hypotheses, sizing/geometry/management posture and experiments without deterministic entry gates. "
            "Use completed decision episodes to question habitual abstention and rejected geometry, while preserving uncertainty and excluding infrastructure faults from strategy. Decision-only findings are observational and cannot pressure entries or size. "
            "Activity, fear of inactivity, and desire for more data are never evidence; flat counterfactuals remain informational and never count as realized performance. "
            "Do not create a fixed or provisional quantity baseline: calibrate quantity from repeated risk-adjusted outcomes, current edge, structural risk, remaining opportunity, drawdown, and the long-run objective. Preserve 25k at no more than one total contract and 250k at no more than ten total contracts. "
            "Keep initial native target legs, reserved capacity, and later thesis-supported protected additions available as choices rather than mandatory recipes. "
            "Follower ratios are user configuration and must not affect the master plan."
        ),
        "daily": (
            "Distill the supplied six-hour plans and supervision summaries into a compact maintenance learning journal. Do not reconstruct a whole trading session or consume raw decision history. Compare authoritative aggregate performance, preserve contradictions, update durable lessons only from repeated completed evidence, and decide how Hermes should improve. "
            "You may propose one compact versioned core-prompt change. Use operation=replace, copy one exact current sentence or clause into expected_old_text, and put only its minimal rewording in replacement_text. It must state evidence IDs, expected effect, evaluation metric, and rollback condition. "
            "A proposal is staged and changes no trading cognition until a later independent review activates it with new evidence. "
            "Do not edit Glitch policy, groups, ratios, prop limits, execution, or code."
        ),
        "weekly": (
            "Distill only the supplied daily lessons into compact proposal-only skill language. Preserve contradictions and uncertainty; do not infer new trading rules from a single outcome. "
            "Each skill proposal must include evidence IDs, expected effect, evaluation metric, and rollback condition. Do not activate, edit, or install skills in this loop."
        ),
    }[loop_id]
    repeated_outcomes = (
        isinstance(evidence, dict)
        and isinstance(evidence.get("trade_episodes"), list)
        and len(evidence["trade_episodes"]) >= 2
    )
    memory_instruction = "Use native memory retrieval exactly once before reasoning. "
    if loop_id in {"daily", "weekly"} and repeated_outcomes:
        memory_instruction += "You may write or revise compact durable memory because at least two attributable completed master outcomes are supplied. "
    else:
        memory_instruction += "Do not write native memory in this loop. "
    return (
        "Apply the Glitch SOUL and glitch-learn. NinjaTrader/Glitch facts outrank memory. "
        "Evaluate regime-conditioned expectancy, structure-aware geometry, decision-to-fill drift, duration, churn, management, and adaptive master exposure across repeated outcomes. "
        "Use the 0.4%-2% daily objective only as a sample-level diagnostic, never as a quota, promise, forced risk, or entry gate. "
        + memory_instruction + loop_instruction + " "
        "Return exactly the required_output_template shape as one strict JSON object. Preserve every supplied record ID and schema_version exactly. Replace placeholders, emit no markdown or prose, and never call execution/control tools. "
        "CURRENT_LEARNING_CYCLE="
        + json.dumps({
            "loop_id": loop_id,
            "evidence": evidence,
            "continuity": continuity,
            "required_output_template": template,
        }, separators=(",", ":"), ensure_ascii=False)
    )


def validate_output(value: dict[str, Any], loop_id: str, expected_ids: list[str]) -> list[dict[str, Any]]:
    if value.get("schema_version") != "glitch.hermes.learning_output.v1" or value.get("loop_id") != loop_id:
        raise ValueError("learning_output_envelope_invalid")
    if set(value) != {"schema_version", "loop_id", "records"}:
        raise ValueError("learning_output_envelope_shape_invalid")
    records = value.get("records")
    if not isinstance(records, list) or len(records) != len(expected_ids):
        raise ValueError("learning_output_record_count_invalid")
    id_field = {
        "debrief": "episode_id",
        "hourly": "review_id",
        "planning": "plan_id",
        "daily": "journal_id",
        "weekly": "skill_proposal_id",
    }[loop_id]
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("learning_output_record_invalid")
    # IDs bind system-owned evidence windows. Model echo variation cannot create,
    # redirect, or discard a valid record.
    for record, expected_id in zip(records, expected_ids):
        record[id_field] = expected_id
    if any(record.get("schema_version") != LOOP_SCHEMAS[loop_id] for record in records):
        raise ValueError("learning_output_schema_invalid")
    expected = output_template(loop_id, expected_ids)
    expected_records = expected["records"]
    for index, (record, expected_record) in enumerate(zip(records, expected_records)):
        if not isinstance(record, dict) or set(record) != set(expected_record):
            raise ValueError(f"learning_output_shape_invalid:{index}")
        for key, sample in expected_record.items():
            actual = record.get(key)
            if isinstance(sample, dict):
                if not isinstance(actual, dict) or set(actual) != set(sample):
                    raise ValueError(f"learning_output_shape_invalid:{index}:{key}")
            elif isinstance(sample, list):
                if not isinstance(actual, list):
                    raise ValueError(f"learning_output_type_invalid:{index}:{key}")
            elif isinstance(sample, bool):
                if not isinstance(actual, bool):
                    raise ValueError(f"learning_output_type_invalid:{index}:{key}")
            elif isinstance(sample, str) and not isinstance(actual, str):
                raise ValueError(f"learning_output_type_invalid:{index}:{key}")
    return records


def validate_debrief_attribution(records: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> None:
    for record, outcome in zip(records, outcomes):
        if str(record.get("intent_id")) != str(outcome.get("intent_id")):
            raise ValueError("debrief_intent_attribution_invalid")
        if str(record.get("master_account", "")).lower() != str(outcome.get("master_account", "")).lower():
            raise ValueError("debrief_master_attribution_invalid")
        if str(record.get("instrument", "")).upper() != str(outcome.get("instrument", "MNQ")).upper():
            raise ValueError("debrief_instrument_attribution_invalid")


def attach_fact_envelopes(
    records: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    enriched = []
    for record, facts in zip(records, evidence):
        canonical = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        enriched.append({
            **record,
            "schema_version": "glitch.hermes.trade_episode.v2",
            "facts": facts,
            "facts_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        })
    return enriched


def compact_episode(row: dict[str, Any]) -> dict[str, Any]:
    """Keep decision-quality evidence while excluding raw paths and packet payloads."""
    common = {
        key: row.get(key)
        for key in (
            "schema_version", "episode_id", "recorded_utc", "intent_id", "cycle_id",
            "decision_utc", "window_close_utc", "route_id", "master_account",
            "instrument", "action", "reason", "decision_audit", "evidence_kind",
            "classification", "entry_assessment", "exit_assessment", "what_went_well",
            "what_went_wrong", "geometry_assessment", "management_assessment",
            "quantity_assessment", "market_behavior", "lesson_candidates", "uncertainties",
            "proposed_geometry", "forward_observation_count", "forward_high", "forward_low",
            "forward_close", "upward_excursion_points", "downward_excursion_points",
        )
        if key in row
    }
    pre_decision = row.get("pre_decision_state")
    if isinstance(pre_decision, dict):
        common["pre_decision_state"] = pre_decision
    receipt = row.get("receipt")
    if isinstance(receipt, dict):
        common["receipt"] = {
            key: receipt.get(key)
            for key in ("http_status", "body")
            if key in receipt
        }
    facts = row.get("facts")
    if isinstance(facts, dict):
        master_outcome = facts.get("master_outcome")
        master_result = facts.get("master_result")
        entry_context = facts.get("entry_decision_context")
        common["deterministic_facts"] = {
            "master_outcome": {
                key: master_outcome.get(key)
                for key in (
                    "intent_id", "master_account", "instrument", "action", "confidence",
                    "entry_utc", "exit_utc", "planned_stop", "planned_target", "reason",
                    "decision_audit", "master_realized_pnl_usd", "master_attribution_status",
                    "master_learning_eligible",
                )
                if isinstance(master_outcome, dict) and key in master_outcome
            },
            "master_result": {
                key: master_result.get(key)
                for key in (
                    "entry_price", "exit_price", "quantity", "realized_pnl_usd",
                    "initial_native_risk_usd", "realized_r", "sampled_mfe_usd",
                    "sampled_mae_usd", "sampled_mfe_r", "sampled_mae_r", "close_kind",
                    "initial_stop_prices", "initial_target_prices",
                )
                if isinstance(master_result, dict) and key in master_result
            },
            "entry_decision_context": {
                key: entry_context.get(key)
                for key in (
                    "status", "reason", "cycle_id", "packet_hash", "pre_entry",
                    "intent_id", "master_account", "snapshot_hash", "rationale",
                    "decision_reference_price", "actual_entry_vwap", "selected_plan",
                    "native_entry_facts", "normalized_outcome",
                )
                if isinstance(entry_context, dict) and key in entry_context
            },
        }
        common["facts_sha256"] = row.get("facts_sha256")
    return common


def compact_review(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "schema_version", "review_id", "recorded_utc", "evidence_episode_ids",
            "working", "failing", "unknown", "repeated_patterns", "system_findings",
            "candidate_lessons", "guidance", "cognitive_change_decision",
            "cognitive_change_candidate",
        )
        if key in row
    }


def cognitive_evidence(supervisor: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(supervisor / "trade-episodes.jsonl") + read_jsonl(
        supervisor / "decision-episodes.jsonl"
    )
    rows.sort(key=lambda row: str(row.get("recorded_utc") or row.get("decision_utc") or ""))
    return [row for row in rows if row.get("episode_id")]


def checkpoint_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_utc"] = utc_now()
    DIRECT.write_json_atomic(path, state)


def continuity(supervisor: Path) -> dict[str, Any]:
    return {
        "current_plan": DIRECT.read_trading_learning_artifact(
            supervisor / "current-plan.json", DIRECT.CURRENT_PLAN_SCHEMA
        ),
        "current_guidance": DIRECT.read_trading_learning_artifact(
            supervisor / "current-guidance.json", DIRECT.CURRENT_GUIDANCE_SCHEMA
        ),
        "proposed_cognitive_overlay": DIRECT.read_optional_json(
            supervisor / "proposed-cognitive-overlay.json"
        ),
        "active_cognitive_overlay": DIRECT.read_optional_json(supervisor / "active-cognitive-overlay.json"),
    }


def invoke_loop(
    args,
    loop_id: str,
    evidence: Any,
    ids: list[str],
    supervisor: Path,
    template_extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    template = output_template(loop_id, ids, template_extra)
    skills = "glitch-learn"
    prompt = build_prompt(loop_id, evidence, template, continuity(supervisor))
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"learning_prompt_too_large:{loop_id}:{len(prompt)}")
    try:
        value = invoke_hermes(args.profile, prompt, skills, args.timeout_seconds)
        return validate_output(value, loop_id, ids)
    except (json.JSONDecodeError, ValueError) as error:
        repair_prompt = (
            prompt
            + "\nThe previous response failed strict validation with: "
            + f"{type(error).__name__}:{error}"[:300]
            + ". Re-answer the same evidence once using exactly required_output_template. "
            + "Return one complete JSON object only; do not explain the repair."
        )
        if len(repair_prompt) > MAX_PROMPT_CHARS:
            raise ValueError(f"learning_repair_prompt_too_large:{loop_id}:{len(repair_prompt)}")
        value = invoke_hermes(args.profile, repair_prompt, skills, args.timeout_seconds)
        return validate_output(value, loop_id, ids)


def cognitive_evidence_ids(supervisor: Path) -> list[str]:
    return [str(row["episode_id"]) for row in cognitive_evidence(supervisor)]


def trade_evidence_ids(supervisor: Path) -> list[str]:
    return [
        str(row.get("episode_id"))
        for row in read_jsonl(supervisor / "trade-episodes.jsonl")
        if row.get("episode_id")
    ]


def later_evidence_ids(value: dict[str, Any], episode_ids: list[str]) -> set[str]:
    baseline = value.get("baseline_evidence_ids")
    if isinstance(baseline, list):
        return set(episode_ids).difference(str(item) for item in baseline)
    cursor = int(value.get("evaluation_episode_count", value.get("baseline_episode_count")) or 0)
    return set(episode_ids[cursor:])


def apply_cognitive_decision(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    active_path = supervisor / "active-cognitive-overlay.json"
    active = DIRECT.read_optional_json(active_path)
    decision = record.get("cognitive_change_decision")
    if not isinstance(decision, dict):
        return
    action = str(decision.get("action") or "").lower()
    contradiction_review = str(decision.get("contradiction_review") or "").strip()
    if (
        active
        and active.get("status") in {"active", "promoted"}
        and active.get("replacement_text")
        and str(decision.get("candidate_id")) == str(active.get("candidate_id"))
    ):
        later_episode_ids = later_evidence_ids(active, episode_ids).intersection(
            trade_evidence_ids(supervisor)
        )
        later = [value for value in decision.get("evidence_episode_ids", []) if value in later_episode_ids]
        if (
            len(set(later)) < 1
            or action not in {"continue", "promote", "rollback"}
            or not contradiction_review
        ):
            return
        active["status"] = {"continue": "active", "promote": "promoted", "rollback": "rolled_back"}[action]
        active["evaluated_utc"] = utc_now()
        active["evaluation_episode_count"] = len(episode_ids)
        active["baseline_evidence_ids"] = list(episode_ids)
        active["evaluation"] = decision
        if action == "rollback":
            active.pop("replacement_text", None)
        DIRECT.write_json_atomic(active_path, active)
        event = {
            **active,
            "change_event_id": stable_id(
                "cognitive-change-event",
                str(active["candidate_id"]) + "|" + action + "|" + "|".join(sorted(set(later))),
            ),
            "event": "evaluated",
        }
        append_unique(supervisor / "cognitive-changes.jsonl", [event], "change_event_id")
        return

    proposed_path = supervisor / "proposed-cognitive-overlay.json"
    proposed = DIRECT.read_optional_json(proposed_path)
    if (
        not proposed
        or proposed.get("status") != "proposed"
        or not proposed.get("replacement_text")
        or str(decision.get("candidate_id")) != str(proposed.get("candidate_id"))
        or action not in {"activate", "rollback"}
    ):
        return
    later_episode_ids = later_evidence_ids(proposed, episode_ids).intersection(
        trade_evidence_ids(supervisor)
    )
    later = [value for value in decision.get("evidence_episode_ids", []) if value in later_episode_ids]
    if len(set(later)) < 1 or not contradiction_review:
        return
    proposed["status"] = "activated" if action == "activate" else "rolled_back"
    proposed["evaluated_utc"] = utc_now()
    proposed["evaluation"] = decision
    if action == "rollback":
        proposed.pop("replacement_text", None)
    DIRECT.write_json_atomic(proposed_path, proposed)
    if action == "activate":
        active = {
            **proposed,
            "status": "active",
            "activated_utc": utc_now(),
            "activation_evidence_kind": "completed_master_outcomes",
            "activation_trade_episode_ids": sorted(set(later)),
            "baseline_episode_count": len(episode_ids),
            "evaluation_episode_count": len(episode_ids),
            "baseline_evidence_ids": list(episode_ids),
        }
        DIRECT.write_json_atomic(active_path, active)
    event = {
        **proposed,
        "change_event_id": stable_id(
            "cognitive-change-event",
            str(proposed["candidate_id"]) + "|" + action + "|" + "|".join(sorted(set(later))),
        ),
        "event": "activated" if action == "activate" else "proposal_rolled_back",
    }
    append_unique(supervisor / "cognitive-changes.jsonl", [event], "change_event_id")


def activate_cognitive_candidate(record: dict[str, Any], supervisor: Path) -> None:
    candidate = record.get("cognitive_change_candidate")
    if not isinstance(candidate, dict):
        return
    if candidate.get("propose") is not True:
        return
    current = DIRECT.read_optional_json(supervisor / "active-cognitive-overlay.json")
    if current and current.get("status") in {"active", "promoted"} and current.get("replacement_text"):
        return
    proposed_path = supervisor / "proposed-cognitive-overlay.json"
    proposed = DIRECT.read_optional_json(proposed_path)
    if proposed and proposed.get("status") == "proposed" and proposed.get("replacement_text"):
        return
    target = str(candidate.get("target") or "")
    operation = str(candidate.get("operation") or "")
    expected_old_text = str(candidate.get("expected_old_text") or "").strip()
    replacement_text = str(candidate.get("replacement_text") or "").strip()
    evidence_ids = [str(value) for value in candidate.get("evidence_episode_ids", [])]
    episode_ids = cognitive_evidence_ids(supervisor)
    known_episode_ids = set(episode_ids)
    if target != "core_prompt" or operation != "replace":
        return
    if (
        not expected_old_text
        or not replacement_text
        or expected_old_text == replacement_text
        or len(expected_old_text) > 600
        or len(replacement_text) > 600
        or len(set(evidence_ids)) < 1
        or any(value not in known_episode_ids for value in evidence_ids)
    ):
        return
    candidate_id = str(candidate.get("candidate_id") or stable_id(
        "cognitive-change", target + "|" + expected_old_text + "|" + replacement_text
    ))
    value = {
        "schema_version": "glitch.hermes.cognitive_overlay.v1",
        "candidate_id": candidate_id,
        "recorded_utc": utc_now(),
        "baseline_episode_count": len(episode_ids),
        "baseline_evidence_ids": list(episode_ids),
        "target": target,
        "operation": operation,
        "expected_old_text": expected_old_text,
        "expected_old_sha256": hashlib.sha256(expected_old_text.encode("utf-8")).hexdigest(),
        "replacement_text": replacement_text,
        "evidence_episode_ids": evidence_ids,
        "expected_effect": candidate.get("expected_effect"),
        "evaluation_metric": candidate.get("evaluation_metric"),
        "rollback_condition": candidate.get("rollback_condition"),
        "status": "proposed",
        "activation_scope": "configured_glitch_scope",
        "decision_prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
    }
    value["change_event_id"] = stable_id("cognitive-change-event", candidate_id + "|proposed")
    value["event"] = "proposed"
    append_unique(supervisor / "cognitive-changes.jsonl", [value], "change_event_id")
    DIRECT.write_json_atomic(proposed_path, value)


def persist_hourly(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    append_unique(supervisor / "observations.jsonl", [record], "review_id")
    trade_count = len(trade_evidence_ids(supervisor))
    decision_count = len(read_jsonl(supervisor / "decision-episodes.jsonl"))
    guidance = {
        "schema_version": DIRECT.CURRENT_GUIDANCE_SCHEMA,
        "guidance_id": stable_id("guidance", str(record["review_id"])),
        "recorded_utc": record.get("recorded_utc") or utc_now(),
        "source_review_id": record["review_id"],
        "decision_prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
        "trading_influence": "outcome_backed" if trade_count >= 2 else "observational",
        "trade_episode_count": trade_count,
        "decision_episode_count": decision_count,
        "guidance": record.get("guidance"),
    }
    append_unique(supervisor / "trading-guidance.jsonl", [guidance], "guidance_id")
    DIRECT.write_json_atomic(supervisor / "current-guidance.json", guidance)
    lessons = []
    for index, lesson in enumerate(record.get("candidate_lessons", [])):
        if not isinstance(lesson, dict):
            continue
        lessons.append({
            "schema_version": "glitch.hermes.candidate_lesson.v1",
            "lesson_id": str(lesson.get("lesson_id") or stable_id("lesson", f"{record['review_id']}:{index}")),
            "recorded_utc": utc_now(),
            "source_review_id": record["review_id"],
            **lesson,
        })
    append_unique(supervisor / "lessons.jsonl", lessons, "lesson_id")
    apply_cognitive_decision(record, supervisor, episode_ids)
    activate_cognitive_candidate(record, supervisor)


def minutes_since(value: Any, now: datetime) -> float:
    try:
        return (now - parse_utc(value)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")


def outcome_completed_utc(row: dict[str, Any]) -> datetime:
    try:
        return parse_utc(row.get("exit_utc") or row.get("recorded_utc"))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def apex_session_date_et(value: Any) -> str:
    local = parse_utc(value).astimezone(EASTERN)
    session_date = local.date() + timedelta(days=1) if local.hour >= 18 else local.date()
    return session_date.isoformat()


def latest_completed_apex_session_date(now: datetime) -> str:
    local = now.astimezone(EASTERN)
    completed = local.date() if local.hour >= 17 else local.date() - timedelta(days=1)
    return completed.isoformat()


def unjournaled_completed_sessions(
    eligible_outcomes: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    decision_episodes: list[dict[str, Any]],
    journals: list[dict[str, Any]],
    now: datetime,
) -> list[tuple[str, dict[str, list[dict[str, Any]]]]]:
    completed_through = latest_completed_apex_session_date(now)
    written = {str(row.get("session_date_et")) for row in journals if row.get("session_date_et")}
    episodes_by_intent = {
        str(row.get("intent_id")): row for row in episodes if row.get("intent_id")
    }
    by_session: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for outcome in eligible_outcomes:
        intent_id = str(outcome.get("intent_id") or "")
        if intent_id not in episodes_by_intent or not outcome.get("exit_utc"):
            continue
        try:
            session_date = apex_session_date_et(outcome["exit_utc"])
        except (TypeError, ValueError):
            continue
        if session_date <= completed_through and session_date not in written:
            by_session.setdefault(session_date, {"trade_episodes": [], "decision_episodes": []})[
                "trade_episodes"
            ].append(episodes_by_intent[intent_id])
    for episode in decision_episodes:
        try:
            session_date = apex_session_date_et(episode.get("window_close_utc") or episode.get("decision_utc"))
        except (TypeError, ValueError):
            continue
        if session_date <= completed_through and session_date not in written:
            by_session.setdefault(session_date, {"trade_episodes": [], "decision_episodes": []})[
                "decision_episodes"
            ].append(episode)
    return [(session_date, by_session[session_date]) for session_date in sorted(by_session)]


def recent_learning_rows(
    rows: list[dict[str, Any]], now: datetime, timestamp_fields: tuple[str, ...], minutes: int = 30
) -> list[dict[str, Any]]:
    cutoff = now - timedelta(minutes=minutes)
    recent = []
    for row in rows:
        stamp = None
        for field in timestamp_fields:
            try:
                stamp = parse_utc(row.get(field))
            except (TypeError, ValueError):
                continue
            if stamp is not None:
                break
        if stamp is not None and stamp >= cutoff:
            recent.append(row)
    return recent


def performance_summary(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    realized = [row.get("master_realized_pnl_usd") for row in outcomes if isinstance(row.get("master_realized_pnl_usd"), (int, float))]
    return {
        "eligible_outcome_count": len(outcomes),
        "realized_outcome_count": len(realized),
        "realized_pnl_usd": round(sum(realized), 2),
        "wins": sum(1 for value in realized if value > 0),
        "losses": sum(1 for value in realized if value < 0),
        "flat": sum(1 for value in realized if value == 0),
    }


def run_once(args) -> dict[str, Any]:
    glitch_data = args.glitch_data.resolve()
    exchange = glitch_data / "hermes" / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    feed_fresh = DIRECT.feed_observation_is_fresh(glitch_data)
    state_path = supervisor / "learning-state.json"
    state = DIRECT.read_optional_json(state_path) or {"schema_version": "glitch.hermes.learning_state.v1"}
    if feed_fresh and not args.dry_run:
        DIRECT.reconcile_completed_outcomes(glitch_data, exchange, timeout_seconds=120)
        decision_episodes = collect_decision_episodes(glitch_data, exchange, supervisor)
    else:
        decision_episodes = read_jsonl(supervisor / "decision-episodes.jsonl")

    outcomes = read_jsonl(glitch_data / "intents" / "hermes-trade-outcomes.jsonl")
    eligible = [row for row in outcomes if row.get("master_learning_eligible", row.get("learning_eligible")) is True]
    existing_episodes = read_jsonl(supervisor / "trade-episodes.jsonl")
    processed = set(state.get("debriefed_intent_ids", [])) | {
        str(row.get("intent_id")) for row in existing_episodes if row.get("intent_id")
    }
    pending = [row for row in eligible if str(row.get("intent_id")) not in processed]
    new_outcomes = sorted(
        pending,
        key=outcome_completed_utc,
        reverse=True,
    )[:MAX_DEBRIEF_OUTCOMES]
    now = datetime.now(timezone.utc)
    result = {
        "debriefed": 0,
        "hourly": False,
        "planning": False,
        "daily": False,
        "weekly": False,
    }

    # One bounded model loop per scheduler invocation. Each successful branch
    # checkpoints immediately, preventing a later due loop from replaying work
    # or extending this process's ownership of the shared Hermes profile.
    if feed_fresh and new_outcomes and args.force_loop in {None, "debrief"}:
        ids = [stable_id("episode", str(row["intent_id"])) for row in new_outcomes]
        if not args.dry_run:
            factual_evidence = debrief_evidence(glitch_data, new_outcomes)
            records = invoke_loop(args, "debrief", factual_evidence, ids, supervisor)
            validate_debrief_attribution(records, new_outcomes)
            append_unique(
                supervisor / "trade-episodes.jsonl",
                attach_fact_envelopes(records, factual_evidence),
                "episode_id",
            )
            state["debriefed_intent_ids"] = sorted(processed | {str(row["intent_id"]) for row in new_outcomes})
            checkpoint_state(state_path, state)
        result["debriefed"] = len(new_outcomes)
    else:
        episodes = read_jsonl(supervisor / "trade-episodes.jsonl")
        all_evidence = cognitive_evidence(supervisor)
        episode_ids = [str(row["episode_id"]) for row in all_evidence]
        reviewed_ids = {
            str(value) for value in state.get("hourly_reviewed_episode_ids", [])
            if value
        }
        if "hourly_reviewed_episode_ids" not in state:
            unified_cursor = int(state.get("hourly_episode_count", 0))
            if unified_cursor > 0:
                reviewed_ids.update(episode_ids[:unified_cursor])
            else:
                trade_cursor = int(state.get("supervision_trade_count", 0))
                decision_cursor = int(state.get("supervision_decision_count", 0))
                reviewed_ids.update(
                    str(row["episode_id"])
                    for row in episodes[:trade_cursor]
                    if row.get("episode_id")
                )
                reviewed_ids.update(
                    str(row["episode_id"])
                    for row in decision_episodes[:decision_cursor]
                    if row.get("episode_id")
                )
        unreviewed = [
            row for row in all_evidence
            if str(row.get("episode_id")) not in reviewed_ids
        ]
        hourly_due = bool(unreviewed) and (
            len(unreviewed) > MAX_HOURLY_EVIDENCE
            or minutes_since(state.get("last_hourly_utc"), now) >= 60
        )
        if args.force_loop == "hourly" and not unreviewed:
            unreviewed = all_evidence[-MAX_HOURLY_EVIDENCE:]
        if (
            feed_fresh
            and (hourly_due or args.force_loop == "hourly")
            and args.force_loop in {None, "hourly"}
        ):
            batch = unreviewed[:MAX_HOURLY_EVIDENCE]
            batch_ids = [str(row["episode_id"]) for row in batch]
            if batch:
                review_id = stable_id("hourly-review", "|".join(batch_ids))
                if not args.dry_run:
                    records = invoke_loop(
                        args,
                        "hourly",
                        {
                            "episodes": [compact_episode(row) for row in batch],
                            "scope": {
                                "kind": "oldest_unreviewed_supervision",
                                "evidence_episode_ids": batch_ids,
                            },
                        },
                        [review_id],
                        supervisor,
                    )
                    records[0]["evidence_episode_ids"] = batch_ids
                    persist_hourly(records[0], supervisor, episode_ids)
                    state["last_hourly_utc"] = utc_now()
                    state["hourly_reviewed_episode_ids"] = sorted(reviewed_ids | set(batch_ids))
                    state["supervision_trade_count"] = len(episodes)
                    state["supervision_decision_count"] = len(decision_episodes)
                    checkpoint_state(state_path, state)
                result["hourly"] = True
                result["hourly_evidence_ids"] = batch_ids
        else:
            reviews = read_jsonl(supervisor / "observations.jsonl")
            planned_review_ids = {
                str(value) for value in state.get("planning_reviewed_review_ids", [])
                if value
            }
            if "planning_reviewed_review_ids" not in state:
                prior_count = int(state.get("planning_review_count", 0))
                planned_review_ids.update(
                    str(row["review_id"])
                    for row in reviews[:prior_count]
                    if row.get("review_id")
                )
            unplanned_reviews = [
                row for row in reviews
                if str(row.get("review_id")) not in planned_review_ids
            ]
            planning_due = (
                bool(unplanned_reviews)
                and minutes_since(state.get("last_planning_utc"), now) >= 360
            )
            if args.force_loop == "planning" and not unplanned_reviews:
                unplanned_reviews = reviews[-MAX_PLANNING_REVIEWS:]
            if (
                feed_fresh
                and (planning_due or args.force_loop == "planning")
                and args.force_loop in {None, "planning"}
            ):
                review_batch = unplanned_reviews[:MAX_PLANNING_REVIEWS]
                review_ids = [
                    str(row["review_id"]) for row in review_batch if row.get("review_id")
                ]
                if review_batch:
                    plan_id = stable_id("plan", "|".join(review_ids))
                    if not args.dry_run:
                        records = invoke_loop(args, "planning", {
                            "reviews": [compact_review(row) for row in review_batch],
                            "recent_episodes": [
                                compact_episode(row)
                                for row in all_evidence[-MAX_PLANNING_EPISODES:]
                            ],
                            "performance_summary": performance_summary(eligible),
                            "active_plan": DIRECT.read_optional_json(supervisor / "current-plan.json"),
                        }, [plan_id], supervisor)
                        trade_count = len(episodes)
                        records[0]["trading_influence"] = "outcome_backed" if trade_count >= 2 else "observational"
                        records[0]["decision_prompt_version"] = DIRECT.DIRECT_PROMPT_VERSION
                        records[0]["trade_episode_count"] = trade_count
                        records[0]["decision_episode_count"] = len(decision_episodes)
                        records[0]["source_review_ids"] = review_ids
                        append_unique(supervisor / "plans.jsonl", records, "plan_id")
                        DIRECT.write_json_atomic(supervisor / "current-plan.json", records[0])
                        state["last_planning_utc"] = utc_now()
                        state["planning_reviewed_review_ids"] = sorted(
                            planned_review_ids | set(review_ids)
                        )
                        state["planning_review_count"] = len(
                            state["planning_reviewed_review_ids"]
                        )
                        checkpoint_state(state_path, state)
                    result["planning"] = True
                    result["planning_review_ids"] = review_ids
            else:
                plans = read_jsonl(supervisor / "plans.jsonl")
                daily_due = (
                    (not feed_fresh and (
                        len(reviews) > int(state.get("daily_review_count", 0))
                        or len(plans) > int(state.get("daily_plan_count", 0))
                    ))
                    or args.force_loop == "daily"
                )
                if daily_due and args.force_loop in {None, "daily"}:
                    session_date = datetime.now(EASTERN).date().isoformat()
                    journal_id = stable_id("daily-distill", f"{len(reviews)}:{len(plans)}")
                    if not args.dry_run:
                        evidence = {
                            "session_date_et": session_date,
                            "scope": {
                                "kind": "maintenance_distillation",
                                "source": "bounded_plans_plus_supervision_summaries",
                                "through_utc": now.isoformat(),
                            },
                            "reviews": [
                                compact_review(row)
                                for row in reviews[-12:]
                            ],
                            "plans": bounded_learning_rows(
                                plans, max_rows=4, max_chars=80_000
                            ),
                            "performance_summary": performance_summary(eligible),
                        }
                        records = invoke_loop(
                            args,
                            "daily",
                            evidence,
                            [journal_id],
                            supervisor,
                            {"session_date_et": session_date},
                        )
                        append_unique(supervisor / "daily-journal.jsonl", records, "journal_id")
                        apply_cognitive_decision(records[0], supervisor, episode_ids)
                        activate_cognitive_candidate(records[0], supervisor)
                        state["daily_review_count"] = len(reviews)
                        state["daily_plan_count"] = len(plans)
                        checkpoint_state(state_path, state)
                    result["daily"] = True
                    result["daily_distilled"] = True
                else:
                    daily_journals = read_jsonl(supervisor / "daily-journal.jsonl")
                    weekly_due = (
                        len(daily_journals) - int(state.get("weekly_daily_count", 0)) >= 7
                    )
                    if args.force_loop == "weekly":
                        weekly_due = True
                    if weekly_due and args.force_loop in {None, "weekly"}:
                        proposal_id = stable_id(
                            "weekly-skill-proposal", f"{len(daily_journals)}"
                        )
                        if not args.dry_run:
                            records = invoke_loop(args, "weekly", {
                                "scope": {
                                    "kind": "weekly_distillation",
                                    "daily_journal_count": len(daily_journals),
                                },
                                "daily_journals": bounded_learning_rows(
                                    daily_journals[-7:], 7, 180_000
                                ),
                                "recent_plans": bounded_learning_rows(
                                    plans[-4:], 4, 80_000
                                ),
                            }, [proposal_id], supervisor)
                            append_unique(
                                supervisor / "weekly-skill-proposals.jsonl",
                                records,
                                "skill_proposal_id",
                            )
                            state["weekly_daily_count"] = len(daily_journals)
                            checkpoint_state(state_path, state)
                        result["weekly"] = True

    episodes = read_jsonl(supervisor / "trade-episodes.jsonl")
    result["eligible_outcomes"] = len(eligible)
    result["episodes"] = len(episodes)
    result["decision_episodes"] = len(decision_episodes)
    result["selected_intent_ids"] = [str(row.get("intent_id")) for row in new_outcomes]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, default=DEFAULT_GLITCH_DATA)
    parser.add_argument("--profile", default="glitch")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-loop", choices=("debrief", "hourly", "planning", "daily", "weekly"))
    args = parser.parse_args()
    exchange = args.glitch_data.resolve() / "hermes" / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    status_path = supervisor / "learning-worker-status.json"
    lock_path = exchange / "hermes" / "learning-cycle.lock"
    if not DIRECT.acquire_owner_lock(lock_path):
        return 0
    try:
        try:
            result = run_once(args)
        except Exception as error:
            failure = {
                "schema_version": "glitch.hermes.learning_worker_status.v1",
                "recorded_utc": utc_now(),
                "status": "failed",
                "error": f"{type(error).__name__}:{error}"[:500],
            }
            DIRECT.write_json_atomic(status_path, failure)
            print(json.dumps(failure, separators=(",", ":")), file=sys.stderr)
            return 1
        DIRECT.write_json_atomic(status_path, {
            "schema_version": "glitch.hermes.learning_worker_status.v1",
            "recorded_utc": utc_now(),
            "status": "ok",
            "result": result,
        })
        print(json.dumps(result, separators=(",", ":")))
        return 0
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
