"""Launch the slow Hermes learning worker without occupying native cron."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from win_subprocess import detach_flags, resolve_python_invocation


DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"


def write_json_atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def worker_status(
    status: str,
    *,
    reason: str | None = None,
    worker_pid: int | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "glitch.hermes.learning_worker_status.v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
    }
    if reason:
        value["reason"] = reason
    if worker_pid is not None:
        value["worker_pid"] = worker_pid
    return value


def lock_is_active(path: Path, stale_seconds: int) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= stale_seconds
    except FileNotFoundError:
        return False


def worker_command(args) -> list[str]:
    python_executable, _ = resolve_python_invocation()
    command = [
        python_executable,
        str(Path(__file__).with_name("run-hermes-learning-cycle.py")),
        "--glitch-data", str(args.glitch_data.resolve()),
        "--profile", args.profile,
        "--timeout-seconds", str(args.timeout_seconds),
    ]
    if args.dry_run:
        command.append("--dry-run")
    return command


def launch(args) -> dict[str, object]:
    exchange = args.glitch_data.resolve() / "hermes" / "exchange"
    supervisor = exchange / "hermes" / "supervisor"
    supervisor.mkdir(parents=True, exist_ok=True)
    lock_path = exchange / "hermes" / "learning-cycle.lock"
    status_path = supervisor / "learning-worker-status.json"
    if lock_is_active(lock_path, max(args.timeout_seconds * 4, 1800)):
        write_json_atomic(
            status_path,
            worker_status("running", reason="learning_cycle_already_running"),
        )
        return {"launched": False, "reason": "learning_cycle_already_running"}

    log_path = supervisor / "learning-worker.log"
    _, env_overlay = resolve_python_invocation()
    env = os.environ.copy()
    env.update(env_overlay)
    with log_path.open("a", encoding="utf-8") as output:
        output.write(json.dumps({
            "event": "learning_worker_launched",
            "launched_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "profile": args.profile,
            "session_source": "trading",
        }, separators=(",", ":")) + "\n")
        output.flush()
        try:
            process = subprocess.Popen(
                worker_command(args),
                cwd=str(exchange),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                close_fds=True,
                env=env,
                creationflags=detach_flags(),
                start_new_session=sys.platform != "win32",
            )
        except Exception as error:
            write_json_atomic(
                status_path,
                worker_status("failed", reason=f"launcher_failed:{type(error).__name__}"),
            )
            raise
    write_json_atomic(status_path, worker_status("started", worker_pid=process.pid))
    return {
        "launched": True,
        "pid": process.pid,
        "worker": "run-hermes-learning-cycle.py",
        "session_source": "trading",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, default=DEFAULT_GLITCH_DATA)
    parser.add_argument("--profile", default="glitch")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(launch(args), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
