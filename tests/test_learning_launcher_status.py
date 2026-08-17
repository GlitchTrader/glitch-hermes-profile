import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "launch_learning_for_status",
    ROOT / "scripts" / "launch-hermes-learning-cycle.py",
)
LAUNCHER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LAUNCHER)


def args(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        glitch_data=tmp_path,
        profile="glitch",
        timeout_seconds=300,
        dry_run=True,
    )


def status_path(tmp_path: Path) -> Path:
    return (
        tmp_path
        / "hermes"
        / "exchange"
        / "hermes"
        / "supervisor"
        / "learning-worker-status.json"
    )


def test_launcher_records_started_before_returning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 4321

    monkeypatch.setattr(LAUNCHER, "resolve_python_invocation", lambda: ("python", {}))
    monkeypatch.setattr(LAUNCHER, "worker_command", lambda _args: ["python", "worker.py"])
    monkeypatch.setattr(LAUNCHER, "detach_flags", lambda: 0)
    monkeypatch.setattr(LAUNCHER.subprocess, "Popen", lambda *a, **k: FakeProcess())

    result = LAUNCHER.launch(args(tmp_path))

    status = json.loads(status_path(tmp_path).read_text(encoding="utf-8"))
    assert result["launched"] is True
    assert status["status"] == "started"
    assert status["worker_pid"] == 4321
    assert status["recorded_utc"].endswith("Z")


def test_launcher_refreshes_running_status_when_worker_owns_lock(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "hermes" / "exchange" / "hermes" / "learning-cycle.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("{}", encoding="utf-8")

    result = LAUNCHER.launch(args(tmp_path))

    status = json.loads(status_path(tmp_path).read_text(encoding="utf-8"))
    assert result == {"launched": False, "reason": "learning_cycle_already_running"}
    assert status["status"] == "running"
    assert status["reason"] == "learning_cycle_already_running"
