import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

DIRECT_SPEC = importlib.util.spec_from_file_location(
    "run_direct_glitch_cycle_for_control_safety",
    ROOT / "scripts" / "run-direct-glitch-cycle.py",
)
DIRECT = importlib.util.module_from_spec(DIRECT_SPEC)
assert DIRECT_SPEC.loader is not None
DIRECT_SPEC.loader.exec_module(DIRECT)

PLUGIN_SPEC = importlib.util.spec_from_file_location(
    "glitch_control_for_control_safety",
    ROOT / "plugins" / "glitch-control" / "__init__.py",
)
PLUGIN = importlib.util.module_from_spec(PLUGIN_SPEC)
assert PLUGIN_SPEC.loader is not None
PLUGIN_SPEC.loader.exec_module(PLUGIN)


def scenario(cycle_id: str, *bindings: tuple[str, str]) -> dict:
    return {
        "cycle_id": cycle_id,
        "market": {
            "snapshot_hash": "snapshot-1",
            "candidates": [{"instrument": "MNQ", "current_price": 105}],
        },
        "books": [
            {"route_id": route, "master_account": account}
            for route, account in bindings
        ],
    }


def pending_fixture(
    tmp_path: Path,
    old_binding: tuple[str, str],
    current_binding: tuple[str, str],
) -> tuple[Path, Path, dict[str, dict]]:
    exchange = tmp_path / "exchange"
    glitch_data = tmp_path / "GlitchData"
    packet_directory = exchange / "glitch" / "decision-packets"
    outbox_directory = exchange / "hermes" / "outbox"
    attempt_directory = exchange / "hermes" / "model-attempts"
    packet_directory.mkdir(parents=True)
    outbox_directory.mkdir(parents=True)
    attempt_directory.mkdir(parents=True)
    current_packet = {"packet_id": "current"}
    old_packet = {"packet_id": "old"}
    (exchange / "glitch" / "latest-decision-packet.json").write_text(
        json.dumps(current_packet), encoding="utf-8"
    )
    (packet_directory / "old.json").write_text(json.dumps(old_packet), encoding="utf-8")
    (outbox_directory / "old.json").write_text(json.dumps({
        "cycle_id": "old",
        "decisions": [{
            "intent_id": "11111111-1111-4111-8111-111111111111",
            "operator_profile": old_binding[0],
            "account": old_binding[1],
        }],
    }), encoding="utf-8")
    (attempt_directory / "old.json").write_text(json.dumps({
        "schema_version": "glitch.hermes.model_attempt.v1",
        "cycle_id": "old",
        "status": "delivery_incomplete",
    }), encoding="utf-8")
    scenarios = {
        "old": scenario("old", old_binding),
        "current": scenario("current", current_binding),
    }
    return glitch_data, exchange, scenarios


def patch_pending_runtime(monkeypatch: pytest.MonkeyPatch, scenarios: dict[str, dict]) -> None:
    monkeypatch.setattr(DIRECT, "trading_runtime_enabled", lambda _path: True)
    monkeypatch.setattr(DIRECT, "packet_is_current", lambda _packet: True)
    monkeypatch.setattr(DIRECT, "build_scenario", lambda packet: scenarios[packet["packet_id"]])
    monkeypatch.setattr(DIRECT, "validate_batch", lambda *_args, **_kwargs: None)


def test_changed_scope_supersedes_pending_outbox_without_post(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    glitch_data, exchange, scenarios = pending_fixture(
        tmp_path, ("glitch-2", "Sim201"), ("glitch", "Sim101")
    )
    patch_pending_runtime(monkeypatch, scenarios)
    post_calls: list[dict] = []

    def forbidden_submit(*args, **kwargs):
        post_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("stale outbox must not be posted")

    monkeypatch.setattr(DIRECT, "submit_batch", forbidden_submit)
    context_path = DIRECT.outbox_context_path(exchange, "old")
    context_path.parent.mkdir(parents=True)
    context_path.write_text(json.dumps({
        "schema_version": "glitch.hermes.outbox_context.v1",
        "cycle_id": "old",
        "directive_id": "directive-1",
    }), encoding="utf-8")
    directive_path = exchange / "hermes" / "operator-directive.json"
    directive_path.write_text(json.dumps({
        "schema_version": "glitch.operator.directive.v1",
        "directive_id": "directive-1",
        "status": "pending",
    }), encoding="utf-8")

    result = DIRECT.run_once(
        SimpleNamespace(dry_run=False, packet_rollover_wait_seconds=0),
        glitch_data,
        exchange,
    )

    assert result == 0
    assert post_calls == []
    receipt = DIRECT.read_json(exchange / "hermes" / "receipts" / "old.json")
    assert DIRECT.receipt_classification(receipt) == "superseded_no_op"
    assert receipt["results"][0]["result"]["delivery_status"] == "not_posted"
    assert receipt["results"][0]["result"]["body"]["pending_scope"] == [
        {"route_id": "glitch-2", "account": "Sim201"}
    ]
    attempt = DIRECT.read_json(DIRECT.model_attempt_path(exchange, "old"))
    assert attempt["status"] == "superseded"
    assert attempt["supersede_reason"] == "route_account_scope_changed"
    assert DIRECT.read_json(context_path)["status"] == "superseded"
    assert DIRECT.read_json(directive_path)["status"] == "superseded"
    assert DIRECT.pending_outbox(exchange) is None


def test_current_scope_retries_same_intent_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    glitch_data, exchange, scenarios = pending_fixture(
        tmp_path, ("glitch", "Sim101"), ("glitch", "Sim101")
    )
    patch_pending_runtime(monkeypatch, scenarios)
    submitted: list[dict] = []

    def capture_submit(batch: dict, _glitch_data: Path, _exchange: Path) -> dict:
        submitted.append(batch)
        return {
            "complete": True,
            "results": [{
                "intent_id": batch["decisions"][0]["intent_id"],
                "result": {"http_status": 200, "body": {"executor": "completed"}},
            }],
        }

    monkeypatch.setattr(DIRECT, "submit_batch", capture_submit)

    result = DIRECT.run_once(
        SimpleNamespace(dry_run=False, packet_rollover_wait_seconds=0),
        glitch_data,
        exchange,
    )

    assert result == 0
    assert len(submitted) == 1
    assert submitted[0]["decisions"][0]["intent_id"] == "11111111-1111-4111-8111-111111111111"


def configure_plugin_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    directive_directory = tmp_path / "directives"
    monkeypatch.setattr(PLUGIN, "DIRECTIVE_DIR", directive_directory)
    monkeypatch.setattr(PLUGIN, "DIRECTIVE_PATH", directive_directory / "operator-directive.json")
    monkeypatch.setattr(PLUGIN, "DIRECTIVE_LOG", directive_directory / "operator-directives.jsonl")
    monkeypatch.setattr(PLUGIN, "_require_flat_group", lambda: None)


def test_bare_forced_command_rejects_multiple_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_plugin_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        PLUGIN, "_route_account_bindings", lambda: {"route-a": "Sim101", "route-b": "Sim201"}
    )

    with pytest.raises(RuntimeError, match="Multiple routes are configured"):
        PLUGIN._long("")

    assert not PLUGIN.DIRECTIVE_PATH.exists()


def test_bare_forced_command_preserves_single_route_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_plugin_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(PLUGIN, "_route_account_bindings", lambda: {"glitch": "Sim101"})

    response = PLUGIN._long("")

    directive = json.loads(PLUGIN.DIRECTIVE_PATH.read_text(encoding="utf-8"))
    assert directive["scope"] == {
        "kind": "route",
        "bindings": [{"route_id": "glitch", "account": "Sim101"}],
    }
    assert "route glitch (Sim101)" in response


def test_explicit_all_and_exact_route_are_persisted_and_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_plugin_paths(monkeypatch, tmp_path)
    bindings = {"route-a": "Sim101", "route-b": "Sim201"}
    monkeypatch.setattr(PLUGIN, "_route_account_bindings", lambda: bindings)

    all_response = PLUGIN._short("all portfolio experiment")
    all_directive = json.loads(PLUGIN.DIRECTIVE_PATH.read_text(encoding="utf-8"))
    assert all_directive["scope"] == {
        "kind": "all",
        "bindings": [
            {"route_id": "route-a", "account": "Sim101"},
            {"route_id": "route-b", "account": "Sim201"},
        ],
    }
    assert all_directive["rationale"] == "portfolio experiment"
    assert "all route-bound books" in all_response

    route_response = PLUGIN._long("route-b targeted experiment")
    route_directive = json.loads(PLUGIN.DIRECTIVE_PATH.read_text(encoding="utf-8"))
    assert route_directive["scope"] == {
        "kind": "route",
        "bindings": [{"route_id": "route-b", "account": "Sim201"}],
    }
    assert route_directive["rationale"] == "targeted experiment"
    assert "route route-b (Sim201)" in route_response


def valid_decision(route: str, account: str, action: str) -> dict:
    comparison = [DIRECT.CANDIDATE_COMPARISON_MARKER, "INSTRUMENT MNQ:"]
    for field in DIRECT.CANDIDATE_COMPARISON_FIELDS:
        value = "supported MNQ evidence"
        if field == "NOISE_AND_GEOMETRY":
            value = "12 points, 48 ticks, 1m ATR 5, 5m ATR 11, $24 USD risk after latency"
        comparison.append(f"{field}={value}")
    comparison.extend([
        "RANKING=MNQ",
        "SELECTION_INSTRUMENT=MNQ",
        f"SELECTION_ACTION={action}",
        f"SELECTION_EV=direction={'LONG' if action == 'ENTER_LONG' else 'SHORT'};entry=5000;stop={'4988' if action == 'ENTER_LONG' else '5012'};target={'5012' if action == 'ENTER_LONG' else '4988'};risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=55-65%;now_ev={'NEGATIVE' if action == 'NOTHING' else 'POSITIVE'};wait_price={'5008' if action == 'ENTER_LONG' else '4992'};wait_ev=NEGATIVE;decisive_reason=scoped fixture",
        "SELECTION_REASON=scoped fixture",
    ])
    decision = {
        "schema_version": "glitch.intent.v3",
        "intent_id": f"intent-{route}",
        "created_utc": "2026-08-03T12:00:00.0000000Z",
        "instrument": "MNQ",
        "account": account,
        "operator_profile": route,
        "action": action,
        "confidence": 0.7,
        "snapshot_hash": "snapshot-1",
        "model_version": "test-model",
        "prompt_version": "test-prompt",
        "reason": "Scoped fixture.",
        "decision_audit": {
            "bull_case": "Bull case.",
            "bear_case": "Bear case.",
            "flat_case": "Flat case.",
            "aggressive_case": "Aggressive case.",
            "conservative_case": "Conservative case.",
            "decisive_evidence": "\n".join(comparison),
            "disconfirming_evidence": "Disconfirming evidence.",
            "change_condition": "Review next packet.",
            "final_choice": action,
        },
        "wake_triggers": [],
    }
    if action in {"ENTER_LONG", "ENTER_SHORT"}:
        decision.update({
            "quantity": 1,
            "order_type": "MARKET",
            "stop_loss": 100 if action == "ENTER_LONG" else 110,
            "take_profit_1": 110 if action == "ENTER_LONG" else 100,
            "entry_range_low": 104,
            "entry_range_high": 106,
            "forecast": {
                "event": "STOP_BEFORE_PRIMARY_TARGET",
                "probability": 0.4,
                "method": "fixture",
                "confidence": 0.6,
            },
        })
    return decision


def test_forced_batch_validation_applies_only_to_scoped_book() -> None:
    current_scenario = scenario(
        "cycle-1", ("route-a", "Sim101"), ("route-b", "Sim201")
    )
    batch = {
        "schema_version": "glitch.intent.batch.v1",
        "cycle_id": "cycle-1",
        "next_review_seconds": 300,
        "decisions": [
            valid_decision("route-a", "Sim101", "ENTER_LONG"),
            valid_decision("route-b", "Sim201", "ENTER_SHORT"),
        ],
    }
    directive = {
        "directive_type": "forced_entry",
        "bias": "short",
        "scope": {
            "kind": "route",
            "bindings": [{"route_id": "route-b", "account": "Sim201"}],
        },
    }

    DIRECT.validate_batch(batch, current_scenario, directive)

    batch["decisions"][1] = valid_decision("route-b", "Sim201", "NOTHING")
    with pytest.raises(ValueError, match="operator_forced_entry_not_honored:route-b:ENTER_SHORT"):
        DIRECT.validate_batch(batch, current_scenario, directive)

    stale_directive = {
        **directive,
        "scope": {
            "kind": "route",
            "bindings": [{"route_id": "route-b", "account": "OldSim201"}],
        },
    }
    with pytest.raises(ValueError, match="operator_forced_entry_scope_stale"):
        DIRECT.validate_batch(batch, current_scenario, stale_directive)

    legacy_ambiguous = {
        "directive_type": "forced_entry",
        "bias": "short",
        "scope": "all_route_bound_groups",
    }
    with pytest.raises(ValueError, match="operator_forced_entry_scope_ambiguous"):
        DIRECT.validate_batch(batch, current_scenario, legacy_ambiguous)
