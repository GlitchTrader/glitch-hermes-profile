"""Causal regressions from the 2026-09-04 audit; no market/order side effects."""
import copy
import json
import sys
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

from test_direct_cycle_contracts import DIRECT, position_management_evidence
from test_outcome_attribution import LEARNING, RECONCILER
from test_control_safety import PLUGIN
import win_subprocess as WIN


def receipt(intent="entry-a", stop=7725.25, account="Sim101", quantity=1, time="2026-09-04T19:37:07Z"):
    return {
        "intent_id": intent, "recorded_utc": time,
        "code": "group_structural_brackets_submitted",
        "message": f"account={account}|fill=7720.5|point_value_usd=5|leg1_qty={quantity}|sl1={stop}|tp1=7709.75",
    }


def test_original_native_risk_does_not_change_with_later_stop_or_giveback():
    first = receipt()
    later = receipt(stop=7721.5, time="2026-09-04T19:40:00Z")
    events = [later, receipt(account="Sim102", quantity=2), first, copy.deepcopy(first)]
    entries = [{"intent_id": "entry-a", "quantity": 1}]
    risk = DIRECT.initial_risk_for_entries(entries, events, "Sim101", 1)
    assert risk["status"] == "complete"
    assert risk["initial_native_risk_usd"] == 23.75
    assert risk["entries"][0]["initial_fill_price"] == 7720.5
    assert risk["entries"][0]["initial_protection_legs"][0]["initial_stop_price"] == 7725.25
    assert risk["position_quantity_matches_initial"] is True
    fields = DIRECT.execution_message_fields(first["message"])
    assert RECONCILER.initial_native_risk(7720.5, 1, fields, 5)[1] == risk["initial_native_risk_usd"]
    assert DIRECT.initial_risk_for_entries(entries, events, "Sim101", 2)["position_quantity_matches_initial"] is False


@pytest.mark.parametrize("entries,events", [([], [receipt()]), ([{"intent_id": "new", "quantity": 1}], [receipt()]),
    ([{"intent_id": "entry-a", "quantity": 2}], [receipt()])])
def test_missing_or_partial_original_protection_stays_unknown(entries, events):
    risk = DIRECT.initial_risk_for_entries(entries, events, "Sim101", 1)
    assert risk["status"] == "unavailable"
    assert risk["initial_native_risk_usd"] is None


def test_independent_reentry_uses_only_new_native_risk():
    risk = DIRECT.initial_risk_for_entries(
        [{"intent_id": "entry-b", "quantity": 1}],
        [receipt(), receipt(intent="entry-b", stop=7728.5)], "Sim101", 1,
    )
    assert risk["initial_native_risk_usd"] == 40
    assert [row["intent_id"] for row in risk["entries"]] == ["entry-b"]


@pytest.mark.parametrize("peak", [0, 10, 100])
@pytest.mark.parametrize("mark", [-12.5, 0, 20])
def test_management_validator_does_not_choose_action_from_pnl_or_mfe(peak, mark):
    DIRECT.validate_position_management(position_management_evidence("EXIT", "POSITIVE"), "M2K", "EXIT", 0, {
        "status": "complete", "current_unrealized_pnl_usd": mark,
        "peak_unrealized_pnl_usd": peak, "hold_target_before_stop_break_even_probability": 0.15789474,
    })


@pytest.mark.parametrize("estimate,verdict,expected", [
    ("35-50%", "UNCERTAIN", "POSITIVE"), ("5-10%", "POSITIVE", "NEGATIVE"),
    ("5-50%", "POSITIVE", "UNCERTAIN"), ("35-50%", "POSITIVE", "POSITIVE"),
    ("20.01-20.02%", "POSITIVE", "POSITIVE"),
])
def test_all_probability_verdicts_have_one_arithmetic_meaning(estimate, verdict, expected):
    value = (f"direction=LONG;entry=100;stop=99;target=104;risk_points=1;reward_points=4;"
             f"friction_points=0;breakeven_target_first=20%;estimated_target_first_range={estimate};now_ev={verdict}")
    result = DIRECT.deterministic_selection_math(value)
    assert result["computed_terminal_ev_verdict"] == expected
    assert ("verdict_range_mismatch" in result["calculation_issues"]) == (verdict != expected)


def prepare_invocation(monkeypatch):
    executable = WIN._provider_hold_path("fixture").parent / "python.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("mock child; never executed", encoding="utf-8")
    for module in (DIRECT, LEARNING):
        monkeypatch.setattr(module.shutil, "which", lambda _name: str(executable))
        monkeypatch.setattr(module, "resolve_python_invocation", lambda path=None: (sys.executable, {}))
        monkeypatch.setattr(module, "hermes_profile_lock", lambda *_args, **_kwargs: nullcontext())


def test_provider_exhaustion_is_shared_until_explicit_resume(monkeypatch):
    prepare_invocation(monkeypatch)
    calls = []
    def exhausted(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="API call failed: HTTP 429: The usage limit has been reached", stderr="")
    monkeypatch.setattr(DIRECT.subprocess, "run", exhausted)
    with pytest.raises(DIRECT.ModelCallDeferred, match="provider_usage_limit"):
        DIRECT.invoke_hermes("glitch", "prompt", 30)
    with pytest.raises(DIRECT.ModelCallDeferred, match="provider_usage_limit"):
        DIRECT.invoke_hermes("glitch", "prompt", 30)
    with pytest.raises(LEARNING.LearningNotAdmitted, match="provider_usage_limit"):
        LEARNING.invoke_hermes("glitch", "prompt", "skill", 30)
    assert len(calls) == 1
    assert WIN.provider_usage_hold_reason("another-profile") is None
    assert WIN.provider_usage_hold_reason("glitch") == "provider_usage_limit_requires_explicit_resume"


@pytest.mark.parametrize("error", ["HTTP 429: rate limit", "HTTP 503", "connection timed out", "HTTP 401"])
def test_transient_or_other_provider_errors_do_not_latch_usage(error):
    assert WIN.record_provider_usage_failure("glitch", error) is False
    assert WIN.provider_usage_hold_reason("glitch") is None


@pytest.mark.parametrize("reason", ["ai_auto_off_or_scope_invalid", "market_session_closed", "stale_market_package", "stale_feed_observation"])
def test_both_workers_recheck_admission_after_lock_before_process_start(monkeypatch, reason):
    prepare_invocation(monkeypatch)
    locked = False
    @contextmanager
    def lock(*args, **kwargs):
        nonlocal locked
        locked = True
        yield
    def admission():
        assert locked
        return reason
    def forbidden(*args, **kwargs):
        raise AssertionError("No process may start after admission is lost while waiting")
    for module in (DIRECT, LEARNING):
        monkeypatch.setattr(module, "hermes_profile_lock", lock)
        monkeypatch.setattr(module.subprocess, "Popen", forbidden)
        monkeypatch.setattr(module.subprocess, "run", forbidden)
    with pytest.raises(DIRECT.ModelCallDeferred, match=reason):
        DIRECT.invoke_hermes("glitch", "prompt", 30, model_call_admission=admission)
    locked = False
    with pytest.raises(LEARNING.LearningNotAdmitted, match=reason):
        LEARNING.invoke_hermes("glitch", "prompt", "skill", 30, model_call_admission=admission)


def test_control_scopes_every_cron_operation_without_changing_ambient_store(monkeypatch, tmp_path):
    original, root = tmp_path / "other", tmp_path / "glitch"
    current = original
    @contextmanager
    def scope(home):
        nonlocal current
        previous, current = current, home
        try:
            yield
        finally:
            current = previous
    def operation(*args, **kwargs):
        assert current == root
        return [{"name": PLUGIN.JOB_NAMES[0], "id": "scoped"}]
    jobs = SimpleNamespace(use_cron_store=scope, list_jobs=operation, pause_job=operation, resume_job=operation)
    monkeypatch.setitem(sys.modules, "cron", SimpleNamespace(jobs=jobs))
    monkeypatch.setattr(PLUGIN, "PROFILE_ROOT", root)
    assert PLUGIN._job(PLUGIN.JOB_NAMES[0])["id"] == "scoped"
    for name in ("pause_job", "resume_job"):
        PLUGIN._cron_operation(name, "scoped")
    assert current == original


def test_missing_jobs_cannot_report_successful_pause_or_resume(monkeypatch):
    monkeypatch.setattr(PLUGIN, "_job", lambda _name: None)
    with pytest.raises(RuntimeError, match="missing"):
        PLUGIN._pause_jobs("test")
    with pytest.raises(RuntimeError, match="both be installed"):
        PLUGIN._trade("")


def test_explicit_resume_clears_only_this_profiles_hold(monkeypatch, tmp_path):
    monkeypatch.setattr(PLUGIN, "PROFILE_ROOT", tmp_path / "glitch")
    hold = PLUGIN.PROFILE_ROOT / "runtime" / "provider-usage-hold.json"
    hold.parent.mkdir(parents=True)
    hold.write_text('{"blocked":true}', encoding="utf-8")
    monkeypatch.setattr(PLUGIN, "_job", lambda name: {"name": name, "id": name, "enabled": False})
    operations = []
    monkeypatch.setattr(PLUGIN, "_cron_operation", lambda *args, **kwargs: operations.append(args) or {})
    monkeypatch.setattr(PLUGIN, "_start_gateway", lambda: None)
    monkeypatch.setattr(PLUGIN, "_request", lambda *args, **kwargs: {})
    monkeypatch.setattr(PLUGIN, "_mark_learning_waiting_after_resume", lambda: None)
    monkeypatch.setattr(PLUGIN, "_status_text", lambda: "test")
    assert PLUGIN._trade("").startswith("Trading is ON")
    assert not hold.exists()
    assert [row[0] for row in operations] == ["resume_job", "resume_job"]


@pytest.mark.parametrize("key,replacement", [
    ("entry", "101"), ("stop", "98"), ("target", "105"),
    ("friction_points", "0.1"), ("direction", "SHORT"),
    ("estimated_target_first_range", "70-80%"),
])
def test_consistency_repair_cannot_change_authored_market_assumptions(key, replacement):
    fields = dict(direction="LONG", entry="100", stop="99", target="104",
                  friction_points="0", estimated_target_first_range="35-50%", now_ev="NEGATIVE")
    def batch(values):
        return {"decisions": [{"instrument": "MES", "action": "NOTHING", "decision_audit": {
            "decisive_evidence": "SELECTION_EV=" + ";".join(f"{k}={v}" for k, v in values.items())
        }}]}
    previous = batch(fields)
    fields["now_ev"] = "POSITIVE"
    error = ValueError("selection_ev_verdict_range_mismatch:0:candidate_comparison")
    DIRECT.enforce_selection_repair_boundary(previous, batch(fields), error)
    fields[key] = replacement
    with pytest.raises(ValueError, match=f"selection_ev_repair_evidence_changed:0:{key}"):
        DIRECT.enforce_selection_repair_boundary(previous, batch(fields), error)


def test_instrument_switch_and_preentry_samples_cannot_inherit_old_excursion(tmp_path):
    data, exchange = tmp_path / "data", tmp_path / "exchange"
    intents = data / "intents"
    supervisor = exchange / "hermes" / "supervisor"
    intents.mkdir(parents=True)
    supervisor.mkdir(parents=True)
    entry = dict(intent_id="entry-a", created_utc="2026-09-04T19:37:07Z",
                 action="ENTER_SHORT", instrument="MES", account="Sim101", quantity=1)
    (intents / "decisions.jsonl").write_text(json.dumps({"intent": entry}) + "\n", encoding="utf-8")
    events = [dict(intent_id="entry-a", code="master_entry_submitted", recorded_utc=entry["created_utc"]), receipt()]
    (intents / "executions.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n", encoding="utf-8")
    (supervisor / "active-trades.json").write_text(json.dumps({"trades": [{
        "master_account": "Sim101", "instrument": "MNQ", "side": "short",
        "entry_decision_utc": "2026-09-04T18:00:00Z", "peak_unrealized_pnl_usd": 300,
        "trough_unrealized_pnl_usd": -200,
    }]}), encoding="utf-8")
    def frame(stamp, pnl):
        return {"created_utc": stamp, "portfolio_snapshot": {"accounts": [{
            "account": "Sim101", "positions": [{"instrument_root": "MES", "market_position": "Short",
            "quantity": 1, "average_price": 7720.5, "unrealized_pnl": pnl}],
            "working_order_details": [],
        }]}}
    packet = {"frames": [frame("2026-09-04T19:35:00Z", 100), frame("2026-09-04T19:38:00Z", -5)]}
    trade = DIRECT.active_trade_state(packet, {"books": [{"master_account": "Sim101"}]}, data, exchange)["trades"][0]
    assert trade["peak_unrealized_pnl_usd"] == -5
    assert trade["trough_unrealized_pnl_usd"] == -5
    assert trade["entry_decision_utc"] == entry["created_utc"]
    assert trade["deterministic_management_math"]["initial_risk"]["initial_native_risk_usd"] == 23.75
    assert "not_tick_exact" in trade["deterministic_management_math"]["excursion_basis"]
