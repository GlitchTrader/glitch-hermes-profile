"""Quota failure must stay visible without consuming market wake conditions."""
import json
from types import SimpleNamespace

import pytest

from test_control_safety import DIRECT, PLUGIN, pending_fixture, patch_pending_runtime
import win_subprocess as WIN


@pytest.mark.parametrize("reason", ["provider_usage_limit_requires_explicit_resume", "provider_usage_hold_unreadable"])
def test_held_new_cognition_preserves_wakes_and_skips_briefing(tmp_path, monkeypatch, reason):
    exchange = tmp_path / "exchange"
    packet = {"packet_id": "20260922T1725Z"}
    DIRECT.write_json_atomic(exchange / "glitch/latest-decision-packet.json", packet)
    for name, value in {
        "trading_runtime_enabled": True, "packet_is_current": True,
        "pending_outbox": None, "scheduled_boundary_crossed": False,
        "build_scenario": {"books": []}, "active_trade_state": {},
        "scoped_native_position_transition_after_packet": None,
        "model_call_admission_reason": None, "repeated_packet_is_suppressed": False,
        "read_operator_directive": None, "native_capture_idle_reason": None,
        "invocation_reason": "condition_change", "all_scoped_books_positioned": False,
        "latest_prior_cognition": None, "provider_usage_hold_reason": reason,
        "fired_wake_triggers": [{"instrument": "MES", "price": 7764.125}],
        "trigger_invocation_context": {"fired_triggers": [{"instrument": "MES", "price": 7764.125}]},
    }.items():
        monkeypatch.setattr(DIRECT, name, lambda *a, _value=value, **k: _value)
    for name in ["consume_fired_wake_triggers", "clear_wake_triggers", "remember_packet_activation",
                 "journal_tail", "market_perception_context", "load_for_hermes", "build_prompt", "invoke_validated_batch"]:
        monkeypatch.setattr(DIRECT, name, lambda *a, **k: pytest.fail("held cognition consumed a wake or built a briefing"))
    args = SimpleNamespace(dry_run=False, profile="glitch")
    assert DIRECT.run_once(args, tmp_path, exchange) == 0
    attempt = DIRECT.read_json(DIRECT.model_attempt_path(exchange, packet["packet_id"]))
    assert attempt["status"] == "deferred" and attempt["reason"] == reason
    assert attempt["model_call_attempted"] is False
    assert "prompt_version" not in attempt  # No prompt was constructed.
    assert not (exchange / "hermes/outbox").exists()
    event_path = exchange / "hermes/events/cycles.jsonl"
    first = event_path.read_bytes()
    assert DIRECT.run_once(args, tmp_path, exchange) == 0
    assert event_path.read_bytes() == first


def test_provider_hold_does_not_block_existing_native_delivery(tmp_path, monkeypatch):
    glitch_data, exchange, scenarios = pending_fixture(tmp_path, ("glitch", "Sim101"), ("glitch", "Sim101"))
    patch_pending_runtime(monkeypatch, scenarios)
    assert WIN.record_provider_usage_failure("glitch", "usage_limit_reached")
    delivered = []
    def submit(batch, *args):
        delivered.append(batch["decisions"][0]["intent_id"])
        return {"complete": True, "results": [{"intent_id": delivered[-1],
            "result": {"http_status": 200, "body": {"executor": "completed"}}}]}
    monkeypatch.setattr(DIRECT, "submit_batch", submit)
    assert DIRECT.run_once(SimpleNamespace(dry_run=False, profile="glitch"), glitch_data, exchange) == 0
    assert delivered == ["11111111-1111-4111-8111-111111111111"]
    assert WIN.provider_usage_hold_reason("glitch") is not None


@pytest.mark.parametrize("reason,updated", [("provider_usage_limit_requires_explicit_resume", True),
    ("provider_usage_hold_unreadable", True), ("market_session_closed", False)])
def test_resume_replaces_only_stale_provider_warning_even_when_recent(tmp_path, monkeypatch, reason, updated):
    path = tmp_path / "learning-status.json"
    monkeypatch.setattr(PLUGIN, "LEARNING_STATUS_PATH", path)
    monkeypatch.setattr(PLUGIN, "LEARNING_LOCK_PATH", tmp_path / "absent.lock")
    original = {"status": "deferred", "reason": reason, "recorded_utc": DIRECT.utc_now()}
    path.write_text(json.dumps(original), encoding="utf-8")
    PLUGIN._mark_learning_waiting_after_resume()
    actual = json.loads(path.read_text())
    if updated:
        assert actual["status"] == "waiting" and actual["reason"] == "trading_resumed"
    else:
        assert actual == original


def test_status_distinguishes_enabled_jobs_from_available_cognition(tmp_path, monkeypatch):
    monkeypatch.setattr(PLUGIN, "PROFILE_ROOT", tmp_path)
    monkeypatch.setattr(PLUGIN, "_request", lambda _: {"trading_enabled": True, "policy_valid": True})
    monkeypatch.setattr(PLUGIN, "_job", lambda _: {"enabled": True})
    monkeypatch.setattr(PLUGIN, "_gateway_running", lambda: True)
    assert "Glitch trading: ON;" in PLUGIN._status_text()
    DIRECT.write_json_atomic(tmp_path / "runtime/provider-usage-hold.json", {"blocked": True})
    assert "Glitch trading: HELD;" in PLUGIN._status_text()
    assert "check provider usage" in PLUGIN._status_text()
