"""Freeze and score Glitch cognition without participating in live decisions.

This process is deliberately outside the direct operator and scheduled learner.
It reads durable Hermes evidence, writes only checkpoint/report artifacts, and
never emits an intent, edits a prompt, or calls a model.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"
REPORT_LEDGER = "cognition-evaluation-reports.jsonl"
FREEZE_SCHEMA = "glitch.hermes.cognition_experiment.v1"
REPORT_SCHEMA = "glitch.hermes.cognition_evaluation.v1"
PUBLISHED_SCHEMA = "glitch.hermes.cognition_evaluation_publication.v1"
EVIDENCE_FILES = (
    "decision-episodes.jsonl",
    "trade-episodes.jsonl",
    "observations.jsonl",
    "cognitive-changes.jsonl",
    "distribution-candidates.jsonl",
    "proposed-cognitive-overlay.json",
    "active-cognitive-overlay.json",
)
PROFILE_CHECKPOINT_FILES = (
    "distribution.yaml",
    "SHA256SUMS",
    "scripts/run-hermes-learning-cycle.py",
    "scripts/evaluate-frozen-cognition.py",
)
LOCAL_POLICY = {
    "elapsed_days": 5,
    "sessions": 5,
    "completed_trades": 8,
    "resolved_entry_forecasts": 5,
    "resolved_nothing_forecasts": 10,
}
DISTRIBUTION_POLICY = {
    "elapsed_days": 21,
    "sessions": 10,
    "weeks": 3,
    "completed_trades": 20,
    "resolved_entry_forecasts": 20,
    "resolved_nothing_forecasts": 20,
    "positive_weeks": 2,
    "regime_buckets": 2,
    "trades_per_regime_bucket": 3,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    try:
        converted = float(str(value))
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path, *, strict: bool = False) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            if strict:
                raise ValueError(f"invalid_jsonl:{path.name}:{line_number}:{error.msg}") from error
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_direct_module(profile_root: Path):
    path = profile_root / "scripts" / "run-direct-glitch-cycle.py"
    spec = importlib.util.spec_from_file_location("glitch_direct_for_evaluation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("direct_cycle_module_unavailable")
    scripts = str(path.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def distribution_version(profile_root: Path) -> str:
    text = (profile_root / "distribution.yaml").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^version:\s*['\"]?([^'\"\s]+)", text)
    if not match:
        raise RuntimeError("distribution_version_unavailable")
    return match.group(1)


def supervisor_root(glitch_data: Path) -> Path:
    return glitch_data.resolve() / "hermes" / "exchange" / "hermes" / "supervisor"


def assert_freeze_is_quiescent(glitch_data: Path, profile_root: Path) -> None:
    state = read_json(glitch_data.resolve() / "hermes" / "control-state.json")
    if state.get("trading_paused") is not True:
        raise RuntimeError("freeze_requires_glitch_ai_paused")
    jobs = read_json(profile_root / "cron" / "jobs.json").get("jobs")
    supported = {"glitch-direct-operator", "glitch-learning-supervisor"}
    if not isinstance(jobs, list):
        raise RuntimeError("freeze_requires_persisted_cron_state")
    relevant = [row for row in jobs if isinstance(row, dict) and row.get("name") in supported]
    if {str(row.get("name")) for row in relevant} != supported:
        raise RuntimeError("freeze_requires_both_glitch_jobs")
    if any(row.get("enabled") is True or row.get("state") == "active" for row in relevant):
        raise RuntimeError("freeze_requires_glitch_jobs_paused")
    exchange = glitch_data.resolve() / "hermes" / "exchange" / "hermes"
    for name in ("direct-cycle.lock", "learning-cycle.lock"):
        if (exchange / name).exists():
            raise RuntimeError(f"freeze_requires_idle_worker:{name}")


def parse_cost_assignments(values: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for value in values:
        instrument, separator, raw = value.partition("=")
        amount = number(raw)
        root = instrument.strip().upper()
        if separator != "=" or not root or amount is None or amount < 0:
            raise ValueError(f"invalid_round_trip_cost:{value}")
        result[root] = round(amount, 6)
    return result


def build_cost_policy(round_trip_ticks: float, assignments: list[str], verified_source: str | None) -> dict[str, Any]:
    if round_trip_ticks < 0:
        raise ValueError("round_trip_ticks_must_be_non_negative")
    explicit = parse_cost_assignments(assignments)
    source = str(verified_source or "").strip()
    return {
        "schema_version": "glitch.hermes.evaluation_cost_policy.v1",
        "default_round_trip_ticks": round(round_trip_ticks, 6),
        "round_trip_cost_usd_per_contract": explicit,
        "verified": bool(source and explicit),
        "source": source or "research_stress_assumption_not_verified_broker_cost",
        "method": (
            "explicit_all_in_round_trip_usd_per_contract"
            if explicit else "native_tick_value_times_stress_ticks"
        ),
        "limitations": (
            "Native outcomes currently omit commissions; default tick stress is conservative research input, "
            "not a claim about the user's actual broker or prop-firm fees. Product promotion remains blocked "
            "until explicit all-in costs and their source are supplied."
        ),
    }


def evidence_id(row: dict[str, Any]) -> str:
    return str(row.get("episode_id") or "")


def evidence_time(row: dict[str, Any]) -> datetime | None:
    facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
    master = facts.get("master_result") if isinstance(facts.get("master_result"), dict) else {}
    for value in (
        row.get("decision_utc"),
        (facts.get("entry_decision_context") or {}).get("decision_utc")
        if isinstance(facts.get("entry_decision_context"), dict) else None,
        master.get("entry_utc"),
        row.get("recorded_utc"),
    ):
        parsed = parse_utc(value)
        if parsed is not None:
            return parsed
    return None


def session_date(row: dict[str, Any]) -> str:
    context = row.get("evidence_context")
    if isinstance(context, dict) and context.get("session_date_et"):
        return str(context["session_date_et"])
    facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
    entry = facts.get("entry_decision_context") if isinstance(facts.get("entry_decision_context"), dict) else {}
    nested = entry.get("evidence_context") if isinstance(entry.get("evidence_context"), dict) else {}
    if nested.get("session_date_et"):
        return str(nested["session_date_et"])
    stamp = evidence_time(row)
    return stamp.date().isoformat() if stamp else ""


def freeze_experiment(
    glitch_data: Path,
    profile_root: Path,
    experiment_id: str | None,
    cost_policy: dict[str, Any],
) -> Path:
    glitch_data = glitch_data.resolve()
    profile_root = profile_root.resolve()
    assert_freeze_is_quiescent(glitch_data, profile_root)
    direct = load_direct_module(profile_root)
    supervisor = supervisor_root(glitch_data)
    active = read_json(supervisor / "active-cognitive-overlay.json")
    active_is_current = bool(direct.cognitive_overlay_is_current(active))
    created = datetime.now(timezone.utc)
    started = parse_utc(active.get("activated_utc")) if active_is_current else created
    if started is None:
        started = created
    expected_prompt = direct.effective_prompt_version(active if active_is_current else None)
    candidate_id = str(active.get("candidate_id") or "") if active_is_current else None
    if active_is_current:
        baseline_ids = {str(value) for value in active.get("baseline_evidence_ids", []) if value}
        anchor = "active_overlay_activation_artifact"
    else:
        baseline_ids = {
            evidence_id(row)
            for name in ("decision-episodes.jsonl", "trade-episodes.jsonl")
            for row in read_jsonl(supervisor / name, strict=True)
            if evidence_id(row)
        }
        anchor = "verified_paused_evidence_checkpoint"
    identifier = experiment_id or (
        created.strftime("%Y%m%dT%H%M%SZ") + "-" + direct.cognitive_bundle_hash()
    )
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,96}", identifier):
        raise ValueError("experiment_id_must_be_filename_safe")
    parent = glitch_data / "hermes-checkpoints" / "cognition-experiments"
    target = parent / identifier
    if target.exists():
        raise FileExistsError(f"experiment_already_exists:{target}")
    temporary = parent / f".{identifier}.{uuid.uuid4().hex}.tmp"
    baseline = temporary / "baseline"
    baseline.mkdir(parents=True, exist_ok=False)
    copied: list[dict[str, Any]] = []
    try:
        for name in EVIDENCE_FILES:
            source = supervisor / name
            if not source.is_file():
                continue
            if source.suffix == ".jsonl":
                read_jsonl(source, strict=True)
            else:
                try:
                    parsed = json.loads(source.read_text(encoding="utf-8-sig"))
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid_json:{name}:{error.msg}") from error
                if not isinstance(parsed, dict):
                    raise ValueError(f"invalid_json_object:{name}")
            before = sha256_file(source)
            destination = baseline / name
            shutil.copy2(source, destination)
            after = sha256_file(source)
            copied_hash = sha256_file(destination)
            if before != after or before != copied_hash:
                raise RuntimeError(f"evidence_changed_during_freeze:{name}")
            copied.append({
                "name": name,
                "bytes": destination.stat().st_size,
                "sha256": copied_hash,
            })
        hot_files = []
        profile_files = tuple(dict.fromkeys(
            tuple(direct.COGNITIVE_BUNDLE_RELATIVE_PATHS) + PROFILE_CHECKPOINT_FILES
        ))
        profile_files = tuple(
            relative for relative in profile_files if (profile_root / relative).is_file()
        )
        for relative in profile_files:
            path = profile_root / relative
            destination = temporary / "profile" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_hash = sha256_file(path)
            shutil.copy2(path, destination)
            current_source_hash = sha256_file(path)
            copied_hash = sha256_file(destination)
            if source_hash != current_source_hash or source_hash != copied_hash:
                raise RuntimeError(f"profile_changed_during_freeze:{relative}")
            record = {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": source_hash,
                "checkpoint_path": f"profile/{relative}",
            }
            if relative in direct.COGNITIVE_BUNDLE_RELATIVE_PATHS:
                hot_files.append(record)
        manifest = {
            "schema_version": FREEZE_SCHEMA,
            "experiment_id": identifier,
            "created_utc": created.isoformat().replace("+00:00", "Z"),
            "experiment_started_utc": started.isoformat().replace("+00:00", "Z"),
            "prospective_anchor": anchor,
            "candidate_id": candidate_id,
            "expected_prompt_version": expected_prompt,
            "cognitive_bundle_hash": direct.cognitive_bundle_hash(),
            "distribution_version": distribution_version(profile_root),
            "profile_root_at_freeze": str(profile_root),
            "glitch_data": str(glitch_data),
            "baseline_evidence_ids": sorted(baseline_ids),
            "baseline_evidence": copied,
            "cognitive_bundle_files": hot_files,
            "profile_checkpoint_files": [
                {
                    "path": relative,
                    "bytes": (temporary / "profile" / relative).stat().st_size,
                    "sha256": sha256_file(temporary / "profile" / relative),
                    "checkpoint_path": f"profile/{relative}",
                }
                for relative in profile_files
            ],
            "cost_policy": cost_policy,
            "evaluation_policy": {
                "local_continuation": LOCAL_POLICY,
                "distribution": DISTRIBUTION_POLICY,
                "effect": "lesson_lifecycle_only_no_trade_or_execution_effect",
            },
        }
        manifest["manifest_sha256"] = canonical_sha256(manifest)
        write_json_atomic(temporary / "freeze.json", manifest)
        parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, target)
        write_json_atomic(parent / "latest.json", {
            "schema_version": "glitch.hermes.cognition_experiment_pointer.v1",
            "experiment_id": identifier,
            "path": str(target),
            "updated_utc": utc_now(),
        })
        return target
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def selection_audit(row: dict[str, Any]) -> dict[str, Any]:
    direct = row.get("selection_ev_arithmetic")
    if isinstance(direct, dict):
        return direct
    facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
    entry = facts.get("entry_decision_context") if isinstance(facts.get("entry_decision_context"), dict) else {}
    nested = entry.get("selection_ev_arithmetic")
    return nested if isinstance(nested, dict) else {}


def evidence_context(row: dict[str, Any]) -> dict[str, Any]:
    direct = row.get("evidence_context")
    if isinstance(direct, dict):
        return direct
    facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
    entry = facts.get("entry_decision_context") if isinstance(facts.get("entry_decision_context"), dict) else {}
    nested = entry.get("evidence_context")
    return nested if isinstance(nested, dict) else {}


def probability_range(audit: dict[str, Any]) -> tuple[float, float] | None:
    value = audit.get("estimated_target_first_range")
    if not isinstance(value, dict):
        return None
    low = number(value.get("low"))
    high = number(value.get("high"))
    if low is None or high is None or not (0 <= low <= high <= 1):
        return None
    return low, high


def geometry_from_decisive_evidence(row: dict[str, Any]) -> dict[str, Any]:
    audit = row.get("decision_audit")
    text = str(audit.get("decisive_evidence") or "") if isinstance(audit, dict) else ""
    match = re.search(r"(?mi)^SELECTION_EV\s*=\s*(.+?)\s*$", text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for component in match.group(1).split(";"):
        key, separator, value = component.partition("=")
        if separator:
            fields[key.strip().lower()] = value.strip()
    direction = fields.get("direction", "").upper()
    result: dict[str, Any] = {"direction": direction}
    for key in ("entry", "stop", "target"):
        converted = number(fields.get(key))
        if converted is not None:
            result[key] = converted
    return result if direction in {"LONG", "SHORT"} else {}


def first_touch(direction: str, stop: float, target: float, bars: list[dict[str, Any]]) -> str:
    for bar in bars:
        high = number(bar.get("high"))
        low = number(bar.get("low"))
        if high is None or low is None:
            continue
        target_hit = high >= target if direction == "LONG" else low <= target
        stop_hit = low <= stop if direction == "LONG" else high >= stop
        if target_hit and stop_hit:
            return "ambiguous_same_bar"
        if target_hit:
            return "target_before_stop"
        if stop_hit:
            return "stop_before_target"
    return "neither_reached"


def normalize_chronology(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    canonical = text.lower()
    if canonical in {
        "target_before_stop", "stop_before_target", "ambiguous_same_bar", "neither_reached"
    }:
        return canonical
    upper = re.sub(r"\s+", "_", text.upper())
    if any(token in upper for token in (
        "AMBIG", "UNCERTAIN", "UNRESOLVED", "SAME_BAR", "SAME_AGGREGATE",
        "ORDER_UNAVAILABLE", "ORDERING_IS_NOT", "CANNOT_ESTABLISH_SEQUENCE",
        "CHRONOLOGY_IS_UNAVAILABLE", "NOT_ESTABLISHED_AS_EXECUTABLE",
    )):
        return "ambiguous_or_unresolved"
    if (
        "TARGET_BEFORE" in upper
        or "OBJECTIVE_REACHED_BEFORE" in upper
        or "OBJECTIVE_TOUCHED" in upper and "INVALIDATION_NOT_TOUCHED" in upper
        or "TARGET_TOUCHED" in upper and "STOP_NOT_TOUCHED" in upper
        or upper.startswith("YES;")
        or upper.startswith("REACHED_BEFORE_INVALIDATION")
    ):
        return "target_before_stop"
    if "STOP_BEFORE" in upper or "INVALIDATION_REACHED_BEFORE" in upper:
        return "stop_before_target"
    if any(token in upper for token in (
        "NEITHER", "NOT_REACHED", "NO_TARGET", "OBJECTIVE_NOT_REACHED",
        "TARGET_NOT_REACHED", "NOT_OBSERVED",
    )):
        return "neither_reached"
    return "ambiguous_or_unresolved"


def review_map(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for observation in observations:
        review = observation.get("opportunity_review")
        rows = review.get("results") if isinstance(review, dict) else None
        if not isinstance(rows, list):
            continue
        for value in rows:
            if not isinstance(value, dict) or not value.get("episode_id"):
                continue
            representative = str(value["episode_id"])
            enriched = {**value, "representative_episode_id": representative}
            for episode in value.get("correlated_episode_ids", [representative]):
                result[str(episode)] = enriched
            result[representative] = enriched
    return result


def instrument_root(value: Any) -> str:
    return str(value or "").strip().upper().split()[0]


def round_trip_cost_usd(
    policy: dict[str, Any], instrument: str, quantity: float, point_value: float, tick_size: float
) -> tuple[float, str]:
    explicit = policy.get("round_trip_cost_usd_per_contract")
    if isinstance(explicit, dict):
        amount = number(explicit.get(instrument))
        if amount is not None:
            return amount * quantity, "explicit_all_in_cost"
    ticks = number(policy.get("default_round_trip_ticks")) or 0.0
    return ticks * tick_size * point_value * quantity, "tick_stress_assumption"


def expected_net_usd(
    probability_target: float,
    risk_points: float,
    reward_points: float,
    point_value: float,
    quantity: float,
    cost_usd: float,
) -> float:
    gross = probability_target * reward_points - (1 - probability_target) * risk_points
    return gross * point_value * quantity - cost_usd


def trade_score(
    row: dict[str, Any],
    policy: dict[str, Any],
    prospective_decision: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
    master = facts.get("master_result") if isinstance(facts.get("master_result"), dict) else {}
    outcome = facts.get("master_outcome") if isinstance(facts.get("master_outcome"), dict) else {}
    gross = number(master.get("realized_pnl_usd"))
    point_value = number(master.get("point_value_usd"))
    tick_size = number(master.get("tick_size"))
    quantity = number(master.get("quantity"))
    if gross is None or point_value is None or tick_size is None or quantity is None or quantity <= 0:
        return None
    instrument = instrument_root(row.get("instrument") or outcome.get("instrument"))
    cost, cost_method = round_trip_cost_usd(policy, instrument, quantity, point_value, tick_size)
    selection = selection_audit(row)
    inputs = selection.get("inputs") if isinstance(selection.get("inputs"), dict) else {}
    risk = number(inputs.get("risk_points"))
    reward = number(inputs.get("reward_points"))
    forecast = outcome.get("forecast_outcome") if isinstance(outcome.get("forecast_outcome"), dict) else {}
    stop_probability = number(forecast.get("probability"))
    p_range = probability_range(selection)
    target_probability = (
        1 - stop_probability
        if stop_probability is not None and 0 <= stop_probability <= 1
        else sum(p_range) / 2 if p_range else None
    )
    expected = (
        expected_net_usd(target_probability, risk, reward, point_value, quantity, cost)
        if target_probability is not None and risk is not None and reward is not None
        else None
    )
    observed_stop = forecast.get("observed")
    forecast_observation_source = forecast.get("observation_source")
    if (
        not isinstance(observed_stop, bool)
        and prospective_decision
        and stop_probability is not None
    ):
        action = str(outcome.get("action") or prospective_decision.get("action") or "")
        direction = "LONG" if action == "ENTER_LONG" else "SHORT" if action == "ENTER_SHORT" else ""
        stop = number(outcome.get("planned_stop"))
        target = number(outcome.get("planned_target"))
        if direction and stop is not None and target is not None:
            chronology = first_touch(
                direction,
                stop,
                target,
                [
                    bar for bar in prospective_decision.get("forward_observations", [])
                    if isinstance(bar, dict)
                ],
            )
            if chronology in {"target_before_stop", "stop_before_target"}:
                observed_stop = chronology == "stop_before_target"
                forecast_observation_source = "prospective_decision_five_bar_chronology"
    brier = None
    observed_target = None
    if isinstance(observed_stop, bool) and stop_probability is not None:
        observed_target = 0 if observed_stop else 1
        brier = (target_probability - observed_target) ** 2
    diagnostics = outcome.get("execution_diagnostics") if isinstance(outcome.get("execution_diagnostics"), dict) else {}
    fidelity = diagnostics.get("intent_fidelity") if isinstance(diagnostics.get("intent_fidelity"), dict) else {}
    fill_quality = fidelity.get("entry_range_fill_quality") if isinstance(fidelity.get("entry_range_fill_quality"), dict) else {}
    coverage = fidelity.get("coverage") if isinstance(fidelity.get("coverage"), dict) else {}
    timing = fidelity.get("timing") if isinstance(fidelity.get("timing"), dict) else {}
    context = evidence_context(row)
    path = context.get("path") if isinstance(context.get("path"), dict) else {}
    efficiencies = path.get("trend_efficiency") if isinstance(path.get("trend_efficiency"), dict) else {}
    decision_price = number((facts.get("entry_decision_context") or {}).get("decision_reference_price"))
    atr = number(context.get("atr_1m"))
    return {
        "episode_id": evidence_id(row),
        "intent_id": str(row.get("intent_id") or outcome.get("intent_id") or ""),
        "prompt_version": str(row.get("prompt_version") or ""),
        "instrument": instrument,
        "session_date_et": session_date(row),
        "gross_pnl_usd": round(gross, 6),
        "evaluation_cost_usd": round(cost, 6),
        "cost_method": cost_method,
        "net_pnl_usd": round(gross - cost, 6),
        "probability_target_first": round(target_probability, 8) if target_probability is not None else None,
        "forecast_source": (
            "formal_stop_before_target_forecast"
            if stop_probability is not None and 0 <= stop_probability <= 1
            else "selection_probability_range" if p_range else None
        ),
        "expected_net_usd": round(expected, 6) if expected is not None else None,
        "observed_target_first": observed_target,
        "brier_score": round(brier, 8) if brier is not None else None,
        "forecast_observation_source": forecast_observation_source,
        "entry_range_status": fill_quality.get("status"),
        "signed_adverse_drift_ticks": number(fidelity.get("signed_adverse_drift_ticks")),
        "native_protection_state": coverage.get("native_state"),
        "unprotected_quantity": number(coverage.get("unprotected_quantity")),
        "decision_to_submission_ms": number(timing.get("decision_to_submission_ms")),
        "submission_to_fill_ms": number(timing.get("submission_to_fill_ms")),
        "atr_ratio": (atr / decision_price) if atr is not None and decision_price else None,
        "trend_efficiency_15": number(efficiencies.get("15")),
    }


def nothing_score(
    row: dict[str, Any], policy: dict[str, Any], reviewed: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    selection = selection_audit(row)
    inputs = selection.get("inputs") if isinstance(selection.get("inputs"), dict) else {}
    risk = number(inputs.get("risk_points"))
    reward = number(inputs.get("reward_points"))
    probabilities = probability_range(selection)
    if risk is None or reward is None or not probabilities:
        return None
    point_value = number(row.get("instrument_point_value_usd"))
    tick_size = number(row.get("instrument_tick_size"))
    if point_value is None or tick_size is None:
        return None
    instrument = instrument_root(row.get("instrument"))
    cost, cost_method = round_trip_cost_usd(policy, instrument, 1.0, point_value, tick_size)
    probability = sum(probabilities) / 2
    geometry = geometry_from_decisive_evidence(row)
    review = reviewed.get(evidence_id(row), {})
    direction = str(geometry.get("direction") or "").upper()
    entry = number(geometry.get("entry"))
    stop = number(geometry.get("stop"))
    target = number(geometry.get("target"))
    raw_chronology = str(review.get("target_before_stop_chronology") or "")
    original_geometry_available = (
        direction in {"LONG", "SHORT"}
        and entry is not None
        and stop is not None
        and target is not None
    )
    if original_geometry_available:
        chronology = first_touch(direction, stop, target, [bar for bar in row.get("forward_observations", []) if isinstance(bar, dict)])
        chronology_source = "original_prospective_selection_geometry"
    else:
        chronology = normalize_chronology(raw_chronology)
        chronology_source = "learner_review_context_not_probability_calibration"
    observed_target = (
        1 if original_geometry_available and chronology == "target_before_stop"
        else 0 if original_geometry_available and chronology == "stop_before_target"
        else None
    )
    brier = (probability - observed_target) ** 2 if observed_target is not None else None
    expected = expected_net_usd(probability, risk, reward, point_value, 1.0, cost)
    context = evidence_context(row)
    return {
        "episode_id": evidence_id(row),
        "opportunity_group_id": str(row.get("opportunity_group_id") or evidence_id(row)),
        "representative_episode_id": review.get("representative_episode_id"),
        "instrument": instrument,
        "session_date_et": session_date(row),
        "estimated_target_first_range": {"low": probabilities[0], "high": probabilities[1]},
        "probability_target_first": round(probability, 8),
        "deterministic_breakeven_target_first": number(selection.get("deterministic_breakeven_target_first")),
        "expected_net_usd": round(expected, 6),
        "evaluation_cost_usd": round(cost, 6),
        "cost_method": cost_method,
        "counterfactual_chronology": chronology or "geometry_unavailable",
        "counterfactual_chronology_source": chronology_source,
        "raw_review_chronology": raw_chronology or None,
        "observed_target_first": observed_target,
        "brier_score": round(brier, 8) if brier is not None else None,
        "review_classification": review.get("classification"),
        "reviewed_one_contract_gross_opportunity_usd": number(review.get("one_contract_gross_opportunity_usd")),
        "evidence_context": {
            "atr_1m": context.get("atr_1m"),
            "order_flow_status": context.get("order_flow_status"),
            "depth_status": context.get("depth_status"),
        },
    }


def calibration(scores: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [row for row in scores if row.get("brier_score") is not None and row.get("observed_target_first") is not None]
    if not resolved:
        return {
            "resolved_count": 0,
            "brier_score": None,
            "climatology_brier_score": None,
            "beats_climatology": None,
        }
    observed = [float(row["observed_target_first"]) for row in resolved]
    base = sum(observed) / len(observed)
    brier = sum(float(row["brier_score"]) for row in resolved) / len(resolved)
    climatology = sum((base - value) ** 2 for value in observed) / len(observed)
    return {
        "resolved_count": len(resolved),
        "observed_target_first_rate": round(base, 8),
        "brier_score": round(brier, 8),
        "climatology_brier_score": round(climatology, 8),
        "beats_climatology": brier < climatology,
    }


def quantile_boundaries(values: list[float]) -> tuple[float, float] | None:
    ordered = sorted(values)
    if len(ordered) < 3:
        return None
    return ordered[(len(ordered) - 1) // 3], ordered[(2 * (len(ordered) - 1)) // 3]


def quantile_label(value: float | None, boundaries: tuple[float, float] | None) -> str:
    if value is None or boundaries is None:
        return "unknown"
    if value <= boundaries[0]:
        return "low"
    if value <= boundaries[1]:
        return "mid"
    return "high"


def aggregate_net(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(field) or "unknown")].append(row)
    return {
        key: {
            "trades": len(values),
            "gross_pnl_usd": round(sum(float(row["gross_pnl_usd"]) for row in values), 6),
            "net_pnl_usd": round(sum(float(row["net_pnl_usd"]) for row in values), 6),
        }
        for key, values in sorted(buckets.items())
    }


def check(name: str, passed: bool, observed: Any, required: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "observed": observed, "required": required}


def build_report(
    manifest: dict[str, Any],
    profile_root: Path,
    decisions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    direct = load_direct_module(profile_root)
    expected_prompt = str(manifest.get("expected_prompt_version") or "")
    baseline_ids = {str(value) for value in manifest.get("baseline_evidence_ids", []) if value}
    start = parse_utc(manifest.get("experiment_started_utc"))
    if start is None:
        raise ValueError("experiment_start_unavailable")

    def is_later(row: dict[str, Any]) -> bool:
        stamp = evidence_time(row)
        return bool(evidence_id(row) and evidence_id(row) not in baseline_ids and stamp and stamp >= start)

    later_decisions = [row for row in decisions if is_later(row)]
    later_trades = [row for row in trades if is_later(row)]
    exact_decisions = [row for row in later_decisions if str(row.get("prompt_version") or "") == expected_prompt]
    exact_trades = [row for row in later_trades if str(row.get("prompt_version") or "") == expected_prompt]
    drift_versions = Counter(
        str(row.get("prompt_version") or "missing")
        for row in later_decisions + later_trades
        if str(row.get("prompt_version") or "") != expected_prompt
    )
    policy = manifest.get("cost_policy") if isinstance(manifest.get("cost_policy"), dict) else {}
    decisions_by_intent = {
        str(row.get("intent_id")): row
        for row in exact_decisions
        if row.get("intent_id")
    }
    trade_scores = [
        score for row in exact_trades
        if (
            score := trade_score(
                row,
                policy,
                decisions_by_intent.get(str(row.get("intent_id") or "")),
            )
        ) is not None
    ]
    reviewed = review_map(observations)
    nothing_rows = [row for row in exact_decisions if row.get("action") == "NOTHING"]
    nothing_scores = [score for row in nothing_rows if (score := nothing_score(row, policy, reviewed)) is not None]
    grouped_nothings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in nothing_scores:
        grouped_nothings[str(row.get("opportunity_group_id") or row.get("episode_id"))].append(row)
    independent_nothings = []
    for values in grouped_nothings.values():
        representative = next(
            (
                row for row in values
                if row.get("representative_episode_id")
                and row.get("episode_id") == row.get("representative_episode_id")
            ),
            values[0],
        )
        independent_nothings.append(representative)

    entry_calibration = calibration(trade_scores)
    nothing_calibration = calibration(independent_nothings)
    combined_calibration = calibration(trade_scores + independent_nothings)
    gross = round(sum(float(row["gross_pnl_usd"]) for row in trade_scores), 6)
    costs = round(sum(float(row["evaluation_cost_usd"]) for row in trade_scores), 6)
    net = round(sum(float(row["net_pnl_usd"]) for row in trade_scores), 6)
    for row in trade_scores:
        date = str(row.get("session_date_et") or "")
        parsed_date = None
        try:
            parsed_date = datetime.fromisoformat(date).date()
        except ValueError:
            pass
        row["iso_week"] = (
            f"{parsed_date.isocalendar().year}-W{parsed_date.isocalendar().week:02d}"
            if parsed_date else "unknown"
        )
    atr_boundaries = quantile_boundaries([
        float(row["atr_ratio"]) for row in trade_scores if row.get("atr_ratio") is not None
    ])
    efficiency_boundaries = quantile_boundaries([
        float(row["trend_efficiency_15"]) for row in trade_scores if row.get("trend_efficiency_15") is not None
    ])
    for row in trade_scores:
        row["regime_bucket"] = "|".join((
            "vol-" + quantile_label(row.get("atr_ratio"), atr_boundaries),
            "path-" + quantile_label(row.get("trend_efficiency_15"), efficiency_boundaries),
        ))
    by_week = aggregate_net(trade_scores, "iso_week")
    by_instrument = aggregate_net(trade_scores, "instrument")
    by_regime = aggregate_net(trade_scores, "regime_bucket")
    positive_weeks = sum(1 for value in by_week.values() if value["net_pnl_usd"] > 0)
    qualifying_regimes = sum(
        1 for value in by_regime.values()
        if value["trades"] >= DISTRIBUTION_POLICY["trades_per_regime_bucket"]
    )
    positive_qualifying_regimes = sum(
        1 for value in by_regime.values()
        if value["trades"] >= DISTRIBUTION_POLICY["trades_per_regime_bucket"]
        and value["net_pnl_usd"] > 0
    )
    sessions = sorted({str(row.get("session_date_et")) for row in trade_scores if row.get("session_date_et")})
    weeks = sorted(key for key in by_week if key != "unknown")
    now = datetime.now(timezone.utc)
    elapsed_days = max(0.0, (now - start).total_seconds() / 86400)
    prompt_unchanged = (
        direct.cognitive_bundle_hash() == manifest.get("cognitive_bundle_hash")
        and direct.DIRECT_PROMPT_VERSION == str(expected_prompt).partition(direct.COGNITIVE_OVERLAY_VERSION_MARKER)[0]
        and not drift_versions
    )
    protected = [row for row in trade_scores if row.get("native_protection_state") == "fully_protected" and (row.get("unprotected_quantity") or 0) == 0]
    protection_complete = bool(trade_scores) and len(protected) == len(trade_scores)
    formal_trade_forecasts = sum(
        1 for row in trade_scores if row.get("forecast_source") == "formal_stop_before_target_forecast"
    )
    formal_trade_forecast_coverage = (
        formal_trade_forecasts / len(trade_scores) if trade_scores else 0.0
    )
    nothing_forecast_coverage = len(nothing_scores) / len(nothing_rows) if nothing_rows else 1.0
    local_checks = [
        check("active_candidate_attribution", bool(manifest.get("candidate_id")), manifest.get("candidate_id"), "non-empty active candidate id"),
        check("exact_frozen_prompt", prompt_unchanged, dict(drift_versions), "no prompt or cognitive-bundle drift"),
        check("elapsed_time", elapsed_days >= LOCAL_POLICY["elapsed_days"], round(elapsed_days, 3), LOCAL_POLICY["elapsed_days"]),
        check("distinct_sessions", len(sessions) >= LOCAL_POLICY["sessions"], len(sessions), LOCAL_POLICY["sessions"]),
        check("completed_trades", len(trade_scores) >= LOCAL_POLICY["completed_trades"], len(trade_scores), LOCAL_POLICY["completed_trades"]),
        check("beats_always_flat_after_costs", net > 0, net, "> 0 USD"),
        check("entry_forecast_resolution", entry_calibration["resolved_count"] >= LOCAL_POLICY["resolved_entry_forecasts"], entry_calibration["resolved_count"], LOCAL_POLICY["resolved_entry_forecasts"]),
        check("entry_forecast_beats_climatology", entry_calibration["beats_climatology"] is True, entry_calibration["beats_climatology"], True),
        check("nothing_forecast_resolution", nothing_calibration["resolved_count"] >= LOCAL_POLICY["resolved_nothing_forecasts"], nothing_calibration["resolved_count"], LOCAL_POLICY["resolved_nothing_forecasts"]),
        check("nothing_forecast_beats_climatology", nothing_calibration["beats_climatology"] is True, nothing_calibration["beats_climatology"], True),
        check("native_protection_complete", protection_complete, f"{len(protected)}/{len(trade_scores)}", "all completed trades"),
    ]
    explicit_costs = policy.get("round_trip_cost_usd_per_contract")
    traded_instruments = {row["instrument"] for row in trade_scores}
    verified_costs = bool(
        policy.get("verified") is True
        and isinstance(explicit_costs, dict)
        and traded_instruments
        and traded_instruments.issubset(set(explicit_costs))
    )
    distribution_checks = [
        check("local_continuation_gate", all(value["passed"] for value in local_checks), all(value["passed"] for value in local_checks), True),
        check("verified_all_in_costs", verified_costs, {"verified": policy.get("verified"), "covered": sorted(set(explicit_costs or {}).intersection(traded_instruments)), "traded": sorted(traded_instruments)}, "every traded instrument"),
        check("elapsed_time", elapsed_days >= DISTRIBUTION_POLICY["elapsed_days"], round(elapsed_days, 3), DISTRIBUTION_POLICY["elapsed_days"]),
        check("distinct_sessions", len(sessions) >= DISTRIBUTION_POLICY["sessions"], len(sessions), DISTRIBUTION_POLICY["sessions"]),
        check("distinct_weeks", len(weeks) >= DISTRIBUTION_POLICY["weeks"], len(weeks), DISTRIBUTION_POLICY["weeks"]),
        check("completed_trades", len(trade_scores) >= DISTRIBUTION_POLICY["completed_trades"], len(trade_scores), DISTRIBUTION_POLICY["completed_trades"]),
        check("resolved_entry_forecasts", entry_calibration["resolved_count"] >= DISTRIBUTION_POLICY["resolved_entry_forecasts"], entry_calibration["resolved_count"], DISTRIBUTION_POLICY["resolved_entry_forecasts"]),
        check("resolved_nothing_forecasts", nothing_calibration["resolved_count"] >= DISTRIBUTION_POLICY["resolved_nothing_forecasts"], nothing_calibration["resolved_count"], DISTRIBUTION_POLICY["resolved_nothing_forecasts"]),
        check("positive_weeks", positive_weeks >= DISTRIBUTION_POLICY["positive_weeks"], positive_weeks, DISTRIBUTION_POLICY["positive_weeks"]),
        check("cross_regime_coverage", qualifying_regimes >= DISTRIBUTION_POLICY["regime_buckets"], qualifying_regimes, DISTRIBUTION_POLICY["regime_buckets"]),
        check("positive_cross_regime_results", positive_qualifying_regimes >= DISTRIBUTION_POLICY["regime_buckets"], positive_qualifying_regimes, DISTRIBUTION_POLICY["regime_buckets"]),
        check("formal_entry_forecast_coverage", formal_trade_forecast_coverage == 1.0, round(formal_trade_forecast_coverage, 8), 1.0),
        check("nothing_forecast_coverage", nothing_forecast_coverage >= 0.95, round(nothing_forecast_coverage, 8), ">= 0.95"),
    ]
    classifications = Counter(str(row.get("review_classification") or "unreviewed") for row in independent_nothings)
    chronologies = Counter(str(row.get("counterfactual_chronology") or "unknown") for row in independent_nothings)
    positive_counterfactuals = [
        row for row in independent_nothings
        if row.get("expected_net_usd") is not None
        and float(row["expected_net_usd"]) > 0
        and row.get("counterfactual_chronology") == "target_before_stop"
        and row.get("counterfactual_chronology_source") == "original_prospective_selection_geometry"
    ]
    inside_range = sum(1 for row in trade_scores if row.get("entry_range_status") == "inside_declared_range")
    adverse = [float(row["signed_adverse_drift_ticks"]) for row in trade_scores if row.get("signed_adverse_drift_ticks") is not None]
    report = {
        "schema_version": REPORT_SCHEMA,
        "report_id": "",
        "recorded_utc": utc_now(),
        "experiment_id": manifest.get("experiment_id"),
        "candidate_id": manifest.get("candidate_id"),
        "experiment_started_utc": manifest.get("experiment_started_utc"),
        "expected_prompt_version": expected_prompt,
        "cognitive_bundle_hash": manifest.get("cognitive_bundle_hash"),
        "distribution_version": manifest.get("distribution_version"),
        "effect": "lesson_lifecycle_only_no_trade_or_execution_effect",
        "profile_integrity": {
            "current_base_prompt_version": direct.DIRECT_PROMPT_VERSION,
            "current_cognitive_bundle_hash": direct.cognitive_bundle_hash(),
            "prompt_unchanged": prompt_unchanged,
            "observed_drift_versions": dict(sorted(drift_versions.items())),
        },
        "cost_policy": policy,
        "sample": {
            "elapsed_days": round(elapsed_days, 6),
            "exact_decisions": len(exact_decisions),
            "exact_completed_trades": len(trade_scores),
            "exact_nothing_decisions": len(nothing_rows),
            "nothing_forecasts_available": len(nothing_scores),
            "formal_trade_forecasts_available": formal_trade_forecasts,
            "independent_nothing_groups": len(independent_nothings),
            "sessions": sessions,
            "weeks": weeks,
        },
        "performance": {
            "gross_pnl_usd": gross,
            "evaluation_cost_usd": costs,
            "net_pnl_usd": net,
            "always_flat_baseline_net_usd": 0.0,
            "beats_always_flat_after_costs": net > 0,
            "wins_after_costs": sum(1 for row in trade_scores if row["net_pnl_usd"] > 0),
            "losses_after_costs": sum(1 for row in trade_scores if row["net_pnl_usd"] < 0),
            "flat_after_costs": sum(1 for row in trade_scores if row["net_pnl_usd"] == 0),
            "by_instrument": by_instrument,
            "by_week": by_week,
            "by_observed_regime_quantile": by_regime,
            "regime_method": "sample-relative ATR/price and 15-minute path-efficiency terciles; evaluation only",
        },
        "calibration": {
            "entry_forecasts": entry_calibration,
            "nothing_forecasts": nothing_calibration,
            "combined": combined_calibration,
        },
        "nothing_accountability": {
            "forecast_coverage": round(nothing_forecast_coverage, 8),
            "classification_counts": dict(sorted(classifications.items())),
            "counterfactual_chronology_counts": dict(sorted(chronologies.items())),
            "positive_expected_net_target_first_count": len(positive_counterfactuals),
            "positive_expected_net_target_first_episode_ids": [row["episode_id"] for row in positive_counterfactuals],
            "limitation": "Counterfactual bar chronology is not an executable fill or realized PnL claim.",
        },
        "execution_quality": {
            "inside_declared_entry_range": inside_range,
            "entry_range_observed": sum(1 for row in trade_scores if row.get("entry_range_status")),
            "native_fully_protected": len(protected),
            "native_protection_observed": len(trade_scores),
            "average_signed_adverse_drift_ticks": round(sum(adverse) / len(adverse), 6) if adverse else None,
        },
        "promotion_gate": {
            "local_continuation": {
                "eligible": all(value["passed"] for value in local_checks),
                "checks": local_checks,
            },
            "distribution": {
                "eligible": all(value["passed"] for value in distribution_checks),
                "checks": distribution_checks,
            },
        },
        "covered_trade_episode_ids": [row["episode_id"] for row in trade_scores],
        "covered_decision_episode_ids": [evidence_id(row) for row in exact_decisions],
        "trade_scores": trade_scores,
        "nothing_scores": independent_nothings,
    }
    identity = {key: value for key, value in report.items() if key not in {"report_id", "recorded_utc"}}
    report["report_id"] = canonical_sha256(identity)
    return report


def resolve_experiment(glitch_data: Path, value: str) -> Path:
    root = (
        glitch_data.resolve() / "hermes-checkpoints" / "cognition-experiments"
    ).resolve()
    pointer = read_json(
        root / "latest.json"
    ) if value == "latest" else {}
    requested = Path(str(pointer.get("path") or "")) if value == "latest" else Path(value)
    candidate = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_dir():
        raise FileNotFoundError("cognition_experiment_unavailable_or_outside_checkpoint_root")
    return candidate


def verify_experiment_checkpoint(experiment: Path, manifest: dict[str, Any]) -> None:
    for section, prefix, key in (
        ("baseline_evidence", "baseline", "name"),
        ("profile_checkpoint_files", "", "checkpoint_path"),
    ):
        rows = manifest.get(section)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"cognition_experiment_{section}_missing")
        for row in rows:
            if not isinstance(row, dict) or not row.get(key) or not row.get("sha256"):
                raise ValueError(f"cognition_experiment_{section}_invalid")
            relative = Path(prefix) / str(row[key]) if prefix else Path(str(row[key]))
            path = (experiment / relative).resolve()
            if not path.is_relative_to(experiment.resolve()) or not path.is_file():
                raise ValueError(f"cognition_experiment_checkpoint_file_missing:{relative}")
            if sha256_file(path) != str(row["sha256"]):
                raise ValueError(f"cognition_experiment_checkpoint_hash_mismatch:{relative}")


def publish_report(supervisor: Path, report: dict[str, Any]) -> dict[str, Any]:
    row = {
        "schema_version": PUBLISHED_SCHEMA,
        "report_id": report["report_id"],
        "recorded_utc": report["recorded_utc"],
        "experiment_id": report.get("experiment_id"),
        "candidate_id": report.get("candidate_id"),
        "expected_prompt_version": report.get("expected_prompt_version"),
        "cognitive_bundle_hash": report.get("cognitive_bundle_hash"),
        "cost_policy": report.get("cost_policy"),
        "sample": report.get("sample"),
        "performance": report.get("performance"),
        "calibration": report.get("calibration"),
        "promotion_gate": report.get("promotion_gate"),
        "covered_trade_episode_ids": report.get("covered_trade_episode_ids"),
        "effect": "lesson_lifecycle_only_no_trade_or_execution_effect",
        "full_report_sha256": canonical_sha256(report),
    }
    row["publication_sha256"] = canonical_sha256(row)
    path = supervisor / REPORT_LEDGER
    rows = read_jsonl(path, strict=True)
    if not any(existing.get("report_id") == row["report_id"] for existing in rows):
        write_jsonl_atomic(path, rows + [row])
    return row


def evaluate_experiment(
    glitch_data: Path, profile_root: Path, experiment: Path, publish: bool
) -> tuple[Path, dict[str, Any]]:
    manifest = read_json(experiment / "freeze.json")
    if manifest.get("schema_version") != FREEZE_SCHEMA:
        raise ValueError("invalid_cognition_experiment")
    expected_hash = manifest.get("manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if expected_hash != canonical_sha256(unsigned):
        raise ValueError("cognition_experiment_manifest_hash_mismatch")
    verify_experiment_checkpoint(experiment, manifest)
    supervisor = supervisor_root(glitch_data)
    report = build_report(
        manifest,
        profile_root.resolve(),
        read_jsonl(supervisor / "decision-episodes.jsonl", strict=True),
        read_jsonl(supervisor / "trade-episodes.jsonl", strict=True),
        read_jsonl(supervisor / "observations.jsonl", strict=True),
    )
    report_path = experiment / "evaluation-report.json"
    write_json_atomic(report_path, report)
    if publish:
        publish_report(supervisor, report)
    return report_path, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glitch-data", type=Path, default=DEFAULT_GLITCH_DATA)
    parser.add_argument("--profile-root", type=Path, default=Path(__file__).resolve().parent.parent)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze", help="Create a verified prospective checkpoint while AI is paused.")
    freeze.add_argument("--experiment-id")
    freeze.add_argument("--round-trip-ticks", type=float, default=4.0)
    freeze.add_argument("--round-trip-cost-usd", action="append", default=[], metavar="INSTRUMENT=USD")
    freeze.add_argument("--verified-cost-source")
    evaluate = subparsers.add_parser("evaluate", help="Score evidence produced after a freeze.")
    evaluate.add_argument("--experiment", default="latest")
    evaluate.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        path = freeze_experiment(
            args.glitch_data,
            args.profile_root,
            args.experiment_id,
            build_cost_policy(args.round_trip_ticks, args.round_trip_cost_usd, args.verified_cost_source),
        )
        result = {"status": "frozen", "experiment": str(path), "freeze": str(path / "freeze.json")}
    else:
        experiment = resolve_experiment(args.glitch_data, args.experiment)
        path, report = evaluate_experiment(args.glitch_data, args.profile_root, experiment, args.publish)
        result = {
            "status": "evaluated",
            "report": str(path),
            "report_id": report["report_id"],
            "published": bool(args.publish),
            "local_continuation_eligible": report["promotion_gate"]["local_continuation"]["eligible"],
            "distribution_eligible": report["promotion_gate"]["distribution"]["eligible"],
        }
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
