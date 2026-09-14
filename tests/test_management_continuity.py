"""Isolated regression checks for management admission and advisory continuity."""
import copy
import ast
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_direct_cycle_contracts import DIRECT, fresh_model_admission_packet, write_model_admission_runtime
from test_learning_p0_repairs import LEARNING


def positioned_scope(*roots):
    return {"books": [{
        "master_account": f"master-{i}", "route_id": f"route-{i}", "followers": [],
        "instrument_contexts": {root: {"current_signed_quantity": 1}},
    } for i, root in enumerate(roots)]}


def unrelated_stale_packet():
    packet = fresh_model_admission_packet()
    for frame in packet["frames"]:
        market = frame["market_snapshot"]
        market["instrument_count"] = 3
        market["instruments"].append({"instrument": "M2K", "is_fresh": False})
        market["coverage"].append({"instrument_root": "M2K", "is_fresh": False})
    return packet


def test_only_position_management_can_exclude_unrelated_stale_market(tmp_path):
    write_model_admission_runtime(tmp_path)
    packet = unrelated_stale_packet()
    now = datetime(2026, 9, 14, 23, tzinfo=timezone.utc)
    for scenario in (None, {"books": []}, positioned_scope("M2K")):
        assert DIRECT.model_call_admission_reason(tmp_path, packet, now, scenario) == "stale_market_package"
    for roots in (("MES",), ("MNQ",), ("MES", "MNQ")):
        assert DIRECT.model_call_admission_reason(tmp_path, packet, now, positioned_scope(*roots)) is None
    mixed = positioned_scope("MES", "MNQ")
    mixed["books"][1]["instrument_contexts"]["MNQ"]["current_signed_quantity"] = 0
    assert DIRECT.model_call_admission_reason(tmp_path, packet, now, mixed) == "stale_market_package"


@pytest.mark.parametrize("frame_index", range(5))
@pytest.mark.parametrize("field", ("instruments", "coverage"))
@pytest.mark.parametrize("damage", ("stale", "missing", "duplicate"))
def test_every_held_root_must_be_present_once_and_fresh_in_every_frame(frame_index, field, damage):
    packet = unrelated_stale_packet()
    market = packet["frames"][frame_index]["market_snapshot"]
    rows = market[field]
    if damage == "stale":
        rows[0]["is_fresh"] = False
    elif damage == "missing":
        rows[0] = {"instrument": "M2K", "is_fresh": True}
    else:
        rows[1] = copy.deepcopy(rows[0])
    assert not DIRECT.model_market_package_is_fresh(packet, {"MES", "MNQ"})


def test_unrelated_fresh_timestamp_does_not_mask_stale_held_timestamp():
    packet = unrelated_stale_packet()
    packet["frames"][-1]["market_snapshot"]["instruments"][0]["timestamp_utc"] = "2020-01-01T00:00:00Z"
    assert not DIRECT.model_market_package_is_fresh(packet, {"MES", "MNQ"})
    assert DIRECT.model_market_package_is_fresh(packet, {"MNQ"})


def test_management_scope_does_not_bypass_ai_session_window_or_feed_gates(tmp_path):
    write_model_admission_runtime(tmp_path)
    packet = unrelated_stale_packet()
    scenario = positioned_scope("MES")
    now = datetime(2026, 9, 14, 23, tzinfo=timezone.utc)
    check = lambda: DIRECT.model_call_admission_reason(tmp_path, packet, now, scenario)
    assert check() is None
    packet["is_contiguous"] = False
    assert check() == "stale_market_package"
    packet["is_contiguous"] = True
    packet["frames"][-1]["portfolio_snapshot"]["accounts"][0]["trading_session_open"] = False
    assert check() == "market_session_closed"
    packet["frames"][-1]["portfolio_snapshot"]["accounts"][0]["trading_session_open"] = True
    weekend = datetime(2026, 9, 13, 14, tzinfo=timezone.utc)
    assert DIRECT.model_call_admission_reason(tmp_path, packet, weekend, scenario) == "weekend"
    (tmp_path / "hermes" / "control-state.json").write_text('{"trading_paused":true}')
    assert check() == "ai_auto_off_or_scope_invalid"
    (tmp_path / "hermes" / "control-state.json").write_text('{"trading_paused":false}')
    (tmp_path / "selfcheck" / "rail.json").write_text('{}')
    assert check() == "stale_feed_observation"


def test_management_model_payload_counts_only_held_instrument_and_preserves_source():
    packet = unrelated_stale_packet()
    original = copy.deepcopy(packet)
    compact = DIRECT.packet_for_model(packet, positioned_scope("MNQ"), positioned_only=True)
    market = compact["frames"][-1]["market_snapshot"]
    assert market["instrument_count"] == market["fresh_instrument_count"] == 1
    assert [row["instrument"] for row in market["instruments"]] == ["MNQ"]
    assert [row["instrument_root"] for row in market["coverage"]] == ["MNQ"]
    assert packet == original


def copy_cognition(tmp_path):
    source = Path(DIRECT.__file__).resolve().parents[1]
    for relative in DIRECT.COGNITIVE_BUNDLE_RELATIVE_PATHS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    return tmp_path / "scripts" / "run-direct-glitch-cycle.py"


@pytest.mark.parametrize("function", ("normalize_batch", "invoke_hermes"))
def test_advisory_identity_survives_parser_transport_change_but_full_provenance_does_not(tmp_path, monkeypatch, function):
    worker = copy_cognition(tmp_path)
    monkeypatch.setattr(DIRECT, "__file__", str(worker))
    before = DIRECT.guidance_cognition_hash(tmp_path)
    full_before = DIRECT.cognitive_bundle_hash()
    source = worker.read_text(encoding="utf-8")
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == function)
    lines = source.splitlines(keepends=True)
    lines.insert(node.body[0].lineno - 1, "    serialization_transport_test_marker = 1\n")
    worker.write_text("".join(lines), encoding="utf-8")
    assert DIRECT.guidance_cognition_hash(tmp_path) == before
    assert DIRECT.cognitive_bundle_hash() != full_before


@pytest.mark.parametrize("file", (
    "SOUL.md", "skills/glitch-position-management/SKILL.md", "scripts/market_structure.py",
    "scripts/native_risk.py", "scripts/run-direct-glitch-cycle.py",
))
def test_advisory_identity_changes_with_cognition_or_input_contract(tmp_path, file):
    copy_cognition(tmp_path)
    before = DIRECT.guidance_cognition_hash(tmp_path)
    target = tmp_path / file
    text = target.read_text(encoding="utf-8")
    if file == "scripts/run-direct-glitch-cycle.py":
        assert '"This is a fast position-management pass.' in text
        text = text.replace('"This is a fast position-management pass.', '"Changed cognition. This is a fast position-management pass.', 1)
    else:
        text += "\n# changed cognition or context contract\n"
    target.write_text(text, encoding="utf-8")
    assert DIRECT.guidance_cognition_hash(tmp_path) != before


def test_guidance_accepts_compatible_advice_without_relabeling_its_origin(tmp_path):
    path = tmp_path / "current-guidance.json"
    old_version = "earlier-parser-release"
    value = {
        "schema_version": DIRECT.CURRENT_GUIDANCE_SCHEMA,
        "decision_prompt_version": old_version,
        "guidance_cognition_hash": DIRECT.GUIDANCE_COGNITION_HASH,
        "trading_influence": "outcome_backed",
        "guidance": "Conditional, outcome-backed advice; current facts remain authoritative.",
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    before = path.read_bytes()
    assert DIRECT.read_trading_learning_artifact(path, DIRECT.CURRENT_GUIDANCE_SCHEMA) == value
    assert path.read_bytes() == before
    for changes in (
        {"guidance_cognition_hash": "different-cognition"},
        {"guidance_cognition_hash": ""},
        {"decision_prompt_version": ""},
        {"trading_influence": "observational"},
        {"schema_version": "wrong"},
    ):
        path.write_text(json.dumps({**value, **changes}), encoding="utf-8")
        assert DIRECT.read_trading_learning_artifact(path, DIRECT.CURRENT_GUIDANCE_SCHEMA) is None
    legacy = {key: item for key, item in value.items() if key != "guidance_cognition_hash"}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert DIRECT.read_trading_learning_artifact(path, DIRECT.CURRENT_GUIDANCE_SCHEMA) is None
    legacy["decision_prompt_version"] = DIRECT.DIRECT_PROMPT_VERSION
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert DIRECT.read_trading_learning_artifact(path, DIRECT.CURRENT_GUIDANCE_SCHEMA) == legacy
    # Advisory compatibility never activates an overlay from another release.
    overlay = {
        "status": "active", "gate_version": DIRECT.COGNITIVE_GATE_VERSION,
        "activation_evidence_kind": "completed_master_outcomes",
        "decision_prompt_version": DIRECT.DIRECT_PROMPT_VERSION,
        "replacement_text": "Conditional advice",
        "expires_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    assert DIRECT.cognitive_overlay_is_current(overlay)
    overlay.update(decision_prompt_version=old_version, guidance_cognition_hash=DIRECT.GUIDANCE_COGNITION_HASH)
    assert not DIRECT.cognitive_overlay_is_current(overlay)


def test_learner_persists_guidance_compatibility_and_exact_release_separately(tmp_path, monkeypatch):
    monkeypatch.setattr(LEARNING, "trade_evidence_ids", lambda *_: {"trade-1", "trade-2"})
    monkeypatch.setattr(LEARNING, "apply_cognitive_decision", lambda *_: None)
    monkeypatch.setattr(LEARNING, "activate_cognitive_candidate", lambda *_: None)
    record = {"review_id": "review-1", "guidance": {"management": "conditional advice"}}
    LEARNING.persist_hourly(record, tmp_path, ["trade-1", "trade-2"])
    value = json.loads((tmp_path / "current-guidance.json").read_text(encoding="utf-8"))
    assert value["guidance_cognition_hash"] == LEARNING.DIRECT.GUIDANCE_COGNITION_HASH
    assert value["decision_prompt_version"] == LEARNING.DIRECT.DIRECT_PROMPT_VERSION
    assert value["trading_influence"] == "outcome_backed"


def test_prompt_clarifies_fill_survival_and_uncertainty_without_an_action_gate():
    packet = fresh_model_admission_packet()
    scenario = positioned_scope("MES")
    scenario.update(cycle_id="cycle-1", market={"candidates": [{"instrument": "MES"}]})
    management = DIRECT.build_prompt(packet, scenario, {})
    assert "STRADDLES is uncertainty, not negative value or proof that EXIT wins" in management
    assert "small sampled MFE is not material earned profit" in management
    assert "NOT_REESTIMATED is not a numeric range" in management
    assert "EXIT need not await original invalidation" in management
    scenario["books"][0]["instrument_contexts"]["MES"]["current_signed_quantity"] = 0
    entry = DIRECT.build_prompt(packet, scenario, {})
    assert "shifted long stop stays below the chosen failure boundary" in entry
    assert "Preserved dollar risk does not prove structural survival" in entry
    assert "correct the authored offset or executable zone" in entry
    assert "Do not impose a stop floor or a preferred ratio" in entry


@pytest.mark.parametrize("latest_change,expected", (
    ("unrelated_stale", None),
    ("held_stale", "stale_market_package"),
    ("position_changed", "position_state_changed_since_prompt"),
    ("mixed_scope", "stale_market_package"),
))
def test_run_rechecks_current_scope_before_model_or_retry(tmp_path, monkeypatch, latest_change, expected):
    write_model_admission_runtime(tmp_path)
    exchange = tmp_path / "hermes" / "exchange"
    path = exchange / "glitch" / "latest-decision-packet.json"
    path.parent.mkdir(parents=True)
    packet = unrelated_stale_packet()
    path.write_text(json.dumps(packet), encoding="utf-8")
    scenario = positioned_scope("MES")
    scenario.update(cycle_id=packet["packet_id"], market={"candidates": [{"instrument": "MES"}]})
    def current_scenario(value):
        result = copy.deepcopy(scenario)
        if value.get("mixed_scope"):
            result["books"].append(positioned_scope("MNQ")["books"][0])
            result["books"][-1]["instrument_contexts"]["MNQ"]["current_signed_quantity"] = 0
        return result
    monkeypatch.setattr(DIRECT, "llm_maintenance_reason", lambda *_: None)
    monkeypatch.setattr(DIRECT, "scheduled_boundary_crossed", lambda *_: False)
    monkeypatch.setattr(DIRECT, "build_scenario", current_scenario)
    monkeypatch.setattr(DIRECT, "active_trade_state", lambda *_: {})
    monkeypatch.setattr(DIRECT, "scoped_native_position_transition_after_packet", lambda *_: None)
    monkeypatch.setattr(DIRECT, "scoped_master_position_change", lambda _a, b, _s: {"changed": True} if b.get("position_changed") else None)
    monkeypatch.setattr(DIRECT, "repeated_packet_is_suppressed", lambda *_: False)
    monkeypatch.setattr(DIRECT, "invocation_reason", lambda *_args, **_kwargs: "position_management")
    monkeypatch.setattr(DIRECT, "journal_tail", lambda *_: {})
    monkeypatch.setattr(DIRECT, "market_perception_context", lambda *_: ({}, None))
    calls = []
    def invoke(*args, **_kwargs):
        admission = args[8]
        assert admission() is None
        latest = copy.deepcopy(packet)
        if latest_change == "held_stale":
            latest["frames"][-1]["market_snapshot"]["coverage"][0]["is_fresh"] = False
        elif latest_change != "unrelated_stale":
            latest[latest_change] = True
        path.write_text(json.dumps(latest), encoding="utf-8")
        observed = admission()
        calls.append(observed)
        assert observed == expected
        raise DIRECT.ModelCallDeferred(observed or "test_no_live_model")
    monkeypatch.setattr(DIRECT, "invoke_validated_batch", invoke)
    assert DIRECT.run_once(SimpleNamespace(dry_run=False, profile="glitch", timeout_seconds=30), tmp_path, exchange) == 0
    assert calls == [expected]
    assert not (exchange / "hermes" / "outbox").exists()
