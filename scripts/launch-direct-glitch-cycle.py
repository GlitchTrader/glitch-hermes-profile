"""Launch the slow direct Hermes worker without occupying native cron."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from win_subprocess import detach_flags, resolve_python_invocation


DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"


def write_json_atomic(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def worker_command(args) -> list[str]:
    python_executable, _ = resolve_python_invocation()
    command = [
        python_executable,
        str(Path(__file__).with_name("run-direct-glitch-cycle.py")),
        "--glitch-data", str(args.glitch_data.resolve()),
        "--profile", args.profile,
        "--timeout-seconds", str(args.timeout_seconds),
        "--packet-rollover-wait-seconds", str(args.packet_rollover_wait_seconds),
    ]
    if args.dry_run:
        command.append("--dry-run")
    return command


def launch(args) -> dict[str, object]:
    exchange = args.glitch_data.resolve() / "hermes" / "exchange"
    events = exchange / "hermes" / "events"
    events.mkdir(parents=True, exist_ok=True)
    request_path = exchange / "hermes" / "direct-cycle-request.json"
    existing: dict[str, object] | None = None
    if request_path.is_file():
        try:
            candidate = json.loads(request_path.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                existing = candidate
        except (OSError, json.JSONDecodeError):
            existing = None
    if not existing or existing.get("kind") not in {
        "entry_range_supersession", "favorable_entry_supersession",
    }:
        write_json_atomic(request_path, {
            "schema_version": "glitch.hermes.direct_cycle_request.v1",
            "requested_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "kind": "scheduled",
        })
    log_path = events / "direct-worker.log"
    _, env_overlay = resolve_python_invocation()
    env = os.environ.copy()
    env.update(env_overlay)
    with log_path.open("a", encoding="utf-8") as output:
        output.write(json.dumps({
            "event": "direct_worker_launched",
            "launched_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "profile": args.profile,
            "session_source": "trading",
        }, separators=(",", ":")) + "\n")
        output.flush()
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
    return {
        "launched": True,
        "pid": process.pid,
        "worker": "run-direct-glitch-cycle.py",
        "session_source": "trading",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glitch-data", type=Path, default=DEFAULT_GLITCH_DATA)
    parser.add_argument("--profile", default="glitch")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--packet-rollover-wait-seconds", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(launch(args), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
