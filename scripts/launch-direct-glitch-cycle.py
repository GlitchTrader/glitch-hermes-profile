"""Launch the slow direct Hermes worker without occupying native cron."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from win_subprocess import detach_flags, resolve_python_invocation


DEFAULT_GLITCH_DATA = Path.home() / "Documents" / "NinjaTrader 8" / "GlitchData"


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
