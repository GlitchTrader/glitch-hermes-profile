"""Hermes-owned Glitch debrief, supervision, planning, and learning loop.

The native 15-minute cron launches this slow worker in an independent process,
so learning can never occupy the minute operator's scheduler lane. It calls
Hermes only when new authoritative evidence makes a loop due. Every call uses
an isolated `trading` session and durable Glitch/Hermes stores provide
continuity; Codex is not in the runtime path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


MODEL = "gpt-5.6-sol"
PROVIDER = "openai-codex"
SOURCE = "trading"
DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
EASTERN = ZoneInfo("America/New_York")
LOOP_SCHEMAS = {
    "debrief": "glitch.hermes.trade_episode.v1",
    "hourly": "glitch.hermes.hourly_review.v1",
    "planning": "glitch.hermes.portfolio_plan.v2",
    "daily": "glitch.hermes.daily_journal.v1",
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


def invoke_hermes(profile: str, prompt: str, skills: str, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("hermes_executable_not_found")
    python_executable = Path(executable).with_name("python.exe")
    if not python_executable.is_file():
        raise RuntimeError("hermes_python_runtime_not_found")
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
    completed = subprocess.run(
        [str(python_executable), "-c", wrapper],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"hermes_failed:{completed.returncode}:{completed.stderr.strip()[:400]}")
    return DIRECT.extract_json(completed.stdout, "glitch.hermes.learning_output.v1")


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
        current_price = float(scenario["market"]["current_price"])
        legs = DIRECT.entry_risk_legs(entry_intent, current_price)
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
    planned_risk = sum(float(leg["planned_risk_usd"]) for leg in legs)
    selected_quantity = int(entry_intent["quantity"])
    result = master_result or {}

    def per_contract(key: str) -> float | None:
        value = result.get(key)
        return round(float(value) / selected_quantity, 2) if isinstance(value, (int, float)) else None

    realized = result.get("realized_pnl_usd", outcome.get("master_realized_pnl_usd"))
    return {
        "status": "complete",
        "cycle_id": cycle_id,
        "packet_hash": packet.get("packet_hash"),
        "pre_entry": book.get("position_building_context"),
        "selected_plan": {
            "action": entry_intent.get("action"),
            "quantity": selected_quantity,
            "entry_role": (book.get("position_building_context") or {}).get("next_entry_role"),
            "legs": legs,
            "planned_risk_usd": round(planned_risk, 2),
        },
        "normalized_outcome": {
            "realized_pnl_per_contract_usd": (
                round(float(realized) / selected_quantity, 2)
                if isinstance(realized, (int, float)) else None
            ),
            "observed_mfe_per_contract_usd": per_contract("observed_mfe_usd"),
            "observed_mae_per_contract_usd": per_contract("observed_mae_usd"),
            "realized_r_multiple": (
                round(float(realized) / planned_risk, 4)
                if isinstance(realized, (int, float)) and planned_risk > 0 else None
            ),
            "observed_mfe_r": (
                round(float(result["observed_mfe_usd"]) / planned_risk, 4)
                if isinstance(result.get("observed_mfe_usd"), (int, float)) and planned_risk > 0 else None
            ),
            "observed_mae_r": (
                round(float(result["observed_mae_usd"]) / planned_risk, 4)
                if isinstance(result.get("observed_mae_usd"), (int, float)) and planned_risk > 0 else None
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
            id_field = {"hourly": "review_id", "planning": "plan_id", "daily": "journal_id"}[loop_id]
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
                        "target": "core_prompt", "instruction": "REPLACE_OR_EMPTY",
                        "evidence_episode_ids": [], "expected_effect": "REPLACE_OR_EMPTY",
                        "evaluation_metric": "REPLACE_OR_EMPTY", "rollback_condition": "REPLACE_OR_EMPTY",
                    },
                })
            elif loop_id == "planning":
                record.update({
                    "horizon_minutes": 300,
                    "performance_objective": "Pursue the proportional target without forcing trades.",
                    "regime_posture": "REPLACE", "objectives": ["REPLACE"],
                    "sizing_guidance": "REPLACE", "geometry_guidance": "REPLACE",
                    "management_guidance": "REPLACE", "experiments": ["REPLACE"],
                    "preservation_conditions": ["REPLACE"], "revision_triggers": ["REPLACE"],
                })
            else:
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
                        "target": "core_prompt", "instruction": "REPLACE_OR_EMPTY",
                        "evidence_episode_ids": [], "expected_effect": "REPLACE_OR_EMPTY",
                        "evaluation_metric": "REPLACE_OR_EMPTY", "rollback_condition": "REPLACE_OR_EMPTY",
                    },
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
            "Reconstruct why Hermes entered, why the trade actually exited, geometry, quantity, every management decision, favorable excursion/rollback, and plausible alternatives. "
            "Use entry_decision_context to judge whether quantity and position architecture were evidence-based or habitual, and whether native target legs, reserved capacity, "
            "or a later independently protected addition deserved consideration. Do not assume a different quantity would have received identical fills; preserve that uncertainty. "
            "A repeated stop geometry mistake is evidence for self-improvement, not permission to invent a fixed stop formula. Process errors are not strategy lessons."
        ),
        "hourly": (
            "Supervise the latest episodes. Identify repeated correct reasoning, repeated mistakes, geometry/management/quantity patterns, false abstention versus overtrading, and system defects. "
            "Issue advisory guidance, never an order. Attributable evidence may produce one compact versioned cognitive proposal now rather than waiting for the daily loop; proposal does not activate it. Preserve its uncertainty until later comparable evidence exists. "
            "For a proposed overlay, return activate or rollback only with at least two later comparable episodes and explicit contradiction review. "
            "For an active overlay, return promote, continue, or rollback only with later episode evidence."
        ),
        "planning": (
            "Create the next 300-minute Hermes plan. Hermes owns strategy and master quantity within current master limits. Set questions, hypotheses, sizing/geometry/management posture and experiments without deterministic entry gates. "
            "Do not create a fixed or provisional quantity baseline: calibrate quantity from repeated risk-adjusted outcomes, current edge, structural risk, remaining opportunity, drawdown, and the long-run objective. "
            "Keep initial native target legs, reserved capacity, and later thesis-supported protected additions available as choices rather than mandatory recipes. "
            "Follower ratios are user configuration and must not affect the master plan."
        ),
        "daily": (
            "Write the daily trader journal, compare the master against its proportional objective, update native semantic memory from repeated completed evidence, and decide how Hermes should improve. "
            "You may propose one compact versioned cognitive change targeting core_prompt, soul, or skill:<name>. It must state exact replacement guidance, evidence IDs, expected effect, evaluation metric, and rollback condition. "
            "A proposal is staged and changes no trading cognition until a later independent review activates it with new evidence. "
            "Do not edit Glitch policy, groups, ratios, prop limits, execution, or code."
        ),
    }[loop_id]
    memory_instruction = (
        "Use native memory retrieval exactly once before reasoning. "
        + ("For this daily loop, write or revise compact durable memory only when repeated attributable master outcomes support it. " if loop_id == "daily" else "Do not write native memory in this loop. ")
    )
    return (
        "Apply the Glitch SOUL and loaded learning skills. NinjaTrader/Glitch facts outrank memory; Hermes owns cognition, strategy, master sizing, and self-improvement. "
        "The long-run objective is approximately 0.4%-2% of master account size per trading day ($100-$500 on $25k; $1,000-$5,000 on $250k). "
        "Use it to evaluate expectancy and master-quantity calibration across repeated outcomes, never as a quota, promise, forced per-trade risk, or entry gate. "
        "Do not turn caution or insufficient evidence for larger size into a fixed one-contract baseline; Hermes must keep quantity adaptive within current master limits. "
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
    id_field = {"debrief": "episode_id", "hourly": "review_id", "planning": "plan_id", "daily": "journal_id"}[loop_id]
    ids = [str(record.get(id_field) or "") for record in records if isinstance(record, dict)]
    if ids != expected_ids:
        raise ValueError("learning_output_identity_mismatch")
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


def continuity(supervisor: Path) -> dict[str, Any]:
    return {
        "current_plan": DIRECT.read_current_learning_artifact(
            supervisor / "current-plan.json", DIRECT.CURRENT_PLAN_SCHEMA
        ),
        "current_guidance": DIRECT.read_current_learning_artifact(
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
    skills = {
        "debrief": "glitch-review-outcomes,glitch-self-learning,glitch-learning-loop",
        "hourly": "glitch-review-outcomes,glitch-self-learning,glitch-self-heal,glitch-supervisor-ledger,glitch-learning-loop",
        "planning": "glitch-self-learning,glitch-supervisor-ledger,glitch-learning-loop",
        "daily": "glitch-review-outcomes,glitch-self-learning,glitch-supervisor-ledger,glitch-learning-loop",
    }[loop_id]
    prompt = build_prompt(loop_id, evidence, template, continuity(supervisor))
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
        value = invoke_hermes(args.profile, repair_prompt, skills, args.timeout_seconds)
        return validate_output(value, loop_id, ids)


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
        and active.get("instruction")
        and str(decision.get("candidate_id")) == str(active.get("candidate_id"))
    ):
        evidence_cursor = int(active.get("evaluation_episode_count", active.get("baseline_episode_count")) or 0)
        later_episode_ids = set(episode_ids[evidence_cursor:])
        later = [value for value in decision.get("evidence_episode_ids", []) if value in later_episode_ids]
        if (
            len(set(later)) < 2
            or action not in {"continue", "promote", "rollback"}
            or not contradiction_review
        ):
            return
        active["status"] = {"continue": "active", "promote": "promoted", "rollback": "rolled_back"}[action]
        active["evaluated_utc"] = utc_now()
        active["evaluation_episode_count"] = len(episode_ids)
        active["evaluation"] = decision
        if action == "rollback":
            active.pop("instruction", None)
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
        or not proposed.get("instruction")
        or str(decision.get("candidate_id")) != str(proposed.get("candidate_id"))
        or action not in {"activate", "rollback"}
    ):
        return
    evidence_cursor = int(proposed.get("baseline_episode_count") or 0)
    later_episode_ids = set(episode_ids[evidence_cursor:])
    later = [value for value in decision.get("evidence_episode_ids", []) if value in later_episode_ids]
    if len(set(later)) < 2 or not contradiction_review:
        return
    proposed["status"] = "activated" if action == "activate" else "rolled_back"
    proposed["evaluated_utc"] = utc_now()
    proposed["evaluation"] = decision
    if action == "rollback":
        proposed.pop("instruction", None)
    DIRECT.write_json_atomic(proposed_path, proposed)
    if action == "activate":
        active = {
            **proposed,
            "status": "active",
            "activated_utc": utc_now(),
            "baseline_episode_count": len(episode_ids),
            "evaluation_episode_count": len(episode_ids),
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
    if current and current.get("status") in {"active", "promoted"} and current.get("instruction"):
        return
    proposed_path = supervisor / "proposed-cognitive-overlay.json"
    proposed = DIRECT.read_optional_json(proposed_path)
    if proposed and proposed.get("status") == "proposed" and proposed.get("instruction"):
        return
    target = str(candidate.get("target") or "")
    instruction = str(candidate.get("instruction") or "").strip()
    evidence_ids = [str(value) for value in candidate.get("evidence_episode_ids", [])]
    episode_ids = [str(row.get("episode_id")) for row in read_jsonl(supervisor / "trade-episodes.jsonl") if row.get("episode_id")]
    known_episode_ids = set(episode_ids)
    if target not in {"core_prompt", "soul"} and not target.startswith("skill:"):
        return
    if (
        not instruction
        or len(instruction) > 1200
        or len(set(evidence_ids)) < 1
        or any(value not in known_episode_ids for value in evidence_ids)
    ):
        return
    candidate_id = str(candidate.get("candidate_id") or stable_id("cognitive-change", target + "|" + instruction))
    value = {
        "schema_version": "glitch.hermes.cognitive_overlay.v1",
        "candidate_id": candidate_id,
        "recorded_utc": utc_now(),
        "baseline_episode_count": len(episode_ids),
        "target": target,
        "instruction": instruction,
        "evidence_episode_ids": evidence_ids,
        "expected_effect": candidate.get("expected_effect"),
        "evaluation_metric": candidate.get("evaluation_metric"),
        "rollback_condition": candidate.get("rollback_condition"),
        "status": "proposed",
        "activation_scope": "configured_glitch_scope",
    }
    value["change_event_id"] = stable_id("cognitive-change-event", candidate_id + "|proposed")
    value["event"] = "proposed"
    append_unique(supervisor / "cognitive-changes.jsonl", [value], "change_event_id")
    DIRECT.write_json_atomic(proposed_path, value)


def persist_hourly(record: dict[str, Any], supervisor: Path, episode_ids: list[str]) -> None:
    append_unique(supervisor / "observations.jsonl", [record], "review_id")
    guidance = {
        "schema_version": DIRECT.CURRENT_GUIDANCE_SCHEMA,
        "guidance_id": stable_id("guidance", str(record["review_id"])),
        "recorded_utc": record.get("recorded_utc") or utc_now(),
        "source_review_id": record["review_id"],
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
    journals: list[dict[str, Any]],
    now: datetime,
) -> list[tuple[str, list[dict[str, Any]]]]:
    completed_through = latest_completed_apex_session_date(now)
    written = {str(row.get("session_date_et")) for row in journals if row.get("session_date_et")}
    episodes_by_intent = {
        str(row.get("intent_id")): row for row in episodes if row.get("intent_id")
    }
    by_session: dict[str, list[dict[str, Any]]] = {}
    for outcome in eligible_outcomes:
        intent_id = str(outcome.get("intent_id") or "")
        if intent_id not in episodes_by_intent or not outcome.get("exit_utc"):
            continue
        try:
            session_date = apex_session_date_et(outcome["exit_utc"])
        except (TypeError, ValueError):
            continue
        if session_date <= completed_through and session_date not in written:
            by_session.setdefault(session_date, []).append(episodes_by_intent[intent_id])
    return [(session_date, by_session[session_date]) for session_date in sorted(by_session)]


def run_once(args) -> dict[str, Any]:
    glitch_data = args.glitch_data.resolve()
    exchange = glitch_data / "hermes" / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    state_path = supervisor / "learning-state.json"
    state = DIRECT.read_optional_json(state_path) or {"schema_version": "glitch.hermes.learning_state.v1"}
    if not args.dry_run:
        DIRECT.reconcile_completed_outcomes(glitch_data, exchange)

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
    )[:8]
    now = datetime.now(timezone.utc)
    result = {"debriefed": 0, "hourly": False, "planning": False, "daily": False}

    if new_outcomes and args.force_loop in {None, "debrief"}:
        ids = [stable_id("episode", str(row["intent_id"])) for row in new_outcomes]
        if not args.dry_run:
            records = invoke_loop(args, "debrief", debrief_evidence(glitch_data, new_outcomes), ids, supervisor)
            validate_debrief_attribution(records, new_outcomes)
            append_unique(supervisor / "trade-episodes.jsonl", records, "episode_id")
            state["debriefed_intent_ids"] = sorted(processed | {str(row["intent_id"]) for row in new_outcomes})
        result["debriefed"] = len(new_outcomes)

    episodes = read_jsonl(supervisor / "trade-episodes.jsonl")
    episode_ids = [str(row.get("episode_id")) for row in episodes if row.get("episode_id")]
    hourly_due = (
        bool(episodes)
        and minutes_since(state.get("last_hourly_utc"), now) >= 60
        and int(state.get("hourly_episode_count", 0)) < len(episodes)
    )
    if (hourly_due or args.force_loop == "hourly") and args.force_loop in {None, "hourly"}:
        review_id = stable_id("hourly-review", now.strftime("%Y%m%dT%H"))
        if not args.dry_run:
            records = invoke_loop(args, "hourly", {"episodes": episodes[-24:]}, [review_id], supervisor)
            persist_hourly(records[0], supervisor, episode_ids)
            state["last_hourly_utc"] = utc_now()
            state["hourly_episode_count"] = len(episodes)
        result["hourly"] = True

    reviews = read_jsonl(supervisor / "observations.jsonl")
    planning_due = (
        bool(reviews)
        and minutes_since(state.get("last_planning_utc"), now) >= 300
        and int(state.get("planning_review_count", 0)) < len(reviews)
    )
    if (planning_due or args.force_loop == "planning") and args.force_loop in {None, "planning"}:
        plan_id = stable_id("plan", now.strftime("%Y%m%dT%H") + f":{now.minute // 5 * 5:02d}")
        if not args.dry_run:
            records = invoke_loop(args, "planning", {"reviews": reviews[-6:], "episodes": episodes[-24:]}, [plan_id], supervisor)
            append_unique(supervisor / "plans.jsonl", records, "plan_id")
            DIRECT.write_json_atomic(supervisor / "current-plan.json", records[0])
            state["last_planning_utc"] = utc_now()
            state["planning_review_count"] = len(reviews)
        result["planning"] = True

    existing_journals = read_jsonl(supervisor / "daily-journal.jsonl")
    due_sessions = unjournaled_completed_sessions(eligible, episodes, existing_journals, now)
    if args.force_loop == "daily" and not due_sessions:
        completed_through = latest_completed_apex_session_date(now)
        all_sessions = unjournaled_completed_sessions(eligible, episodes, [], now)
        if all_sessions:
            due_sessions = [next(
                (item for item in reversed(all_sessions) if item[0] <= completed_through),
                all_sessions[-1],
            )]
    if due_sessions and args.force_loop in {None, "daily"}:
        session_date, session_episodes = due_sessions[0]
        journal_id = stable_id("daily-journal", session_date)
        if not args.dry_run:
            evidence = {
                "session_date_et": session_date,
                "episodes": session_episodes,
                "reviews": reviews[-12:],
                "plans": read_jsonl(supervisor / "plans.jsonl")[-4:],
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
            state["last_daily_session_date_et"] = session_date
        result["daily"] = True
        result["daily_session_date_et"] = session_date

    if not args.dry_run:
        state["updated_utc"] = utc_now()
        DIRECT.write_json_atomic(state_path, state)
    result["eligible_outcomes"] = len(eligible)
    result["episodes"] = len(episodes)
    result["selected_intent_ids"] = [str(row.get("intent_id")) for row in new_outcomes]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, default=DEFAULT_GLITCH_DATA)
    parser.add_argument("--profile", default="glitch")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-loop", choices=("debrief", "hourly", "planning", "daily"))
    args = parser.parse_args()
    exchange = args.glitch_data.resolve() / "hermes" / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    status_path = supervisor / "learning-worker-status.json"
    lock_path = exchange / "hermes" / "learning-cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if time.time() - lock_path.stat().st_mtime <= max(args.timeout_seconds * 4, 1800):
                return 0
            lock_path.unlink()
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileNotFoundError, FileExistsError):
            return 0
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
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
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
