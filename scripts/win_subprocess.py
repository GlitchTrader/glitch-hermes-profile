"""Windows subprocess helpers for the installed Glitch Hermes profile."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path


_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000


def detach_flags() -> int:
    """Hide a background worker and isolate Ctrl+C without DETACHED_PROCESS."""
    if sys.platform != "win32":
        return 0
    return _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW


def hide_flags() -> int:
    """Hide a short-lived child while retaining synchronous stdio."""
    if sys.platform != "win32":
        return 0
    return _CREATE_NO_WINDOW


@contextmanager
def hermes_profile_lock(
    profile: str,
    timeout_seconds: int = 60,
    priority: str = "background",
):
    """Serialize profile mutation while allowing waiting live decisions to go first."""
    if priority not in {"operator", "background"}:
        raise ValueError(f"hermes_profile_lock_priority_invalid:{priority}")
    lock_dir = Path.home() / "AppData" / "Local" / "hermes" / "profiles" / profile / "runtime"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "hermes-cli.lock"
    waiter_path = (
        lock_dir / f"hermes-cli.operator-waiting.{os.getpid()}"
        if priority == "operator" else None
    )
    started = time.monotonic()
    stale_after = max(timeout_seconds * 3, 900)
    descriptor = None
    owner = False
    if waiter_path is not None:
        waiter_path.write_text(f"pid={os.getpid()}\n", encoding="ascii")
    try:
        while descriptor is None:
            if priority == "background":
                operator_waiting = False
                for path in lock_dir.glob("hermes-cli.operator-waiting.*"):
                    try:
                        age = time.time() - path.stat().st_mtime
                    except FileNotFoundError:
                        continue
                    if age > stale_after:
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                    else:
                        operator_waiting = True
                if operator_waiting:
                    if time.monotonic() - started >= timeout_seconds:
                        raise TimeoutError(f"hermes_profile_lock_timeout:{profile}")
                    time.sleep(0.1)
                    continue
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
                owner = True
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > stale_after:
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        continue
                elif time.monotonic() - started >= timeout_seconds:
                    raise TimeoutError(f"hermes_profile_lock_timeout:{profile}")
                else:
                    time.sleep(0.25)
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if owner:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
        if waiter_path is not None:
            try:
                waiter_path.unlink()
            except FileNotFoundError:
                pass


def _read_pyvenv_cfg(venv_dir: Path) -> dict[str, str]:
    try:
        lines = (venv_dir / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()
    return values


def resolve_python_invocation(
    python_executable: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Bypass a Windows uv venv launcher that can re-open a console window."""
    requested = python_executable or sys.executable
    if sys.platform != "win32":
        return requested, {}

    executable = Path(requested)
    if executable.name.lower() == "pythonw.exe":
        sibling = executable.with_name("python.exe")
        if sibling.is_file():
            executable = sibling

    venv_dir = executable.parent.parent
    config = _read_pyvenv_cfg(venv_dir)
    home = config.get("home", "")
    site_packages = venv_dir / "Lib" / "site-packages"
    if "uv" not in config or not home:
        return str(executable), {}

    base_python = Path(home) / "python.exe"
    if not base_python.is_file() or not site_packages.is_dir():
        return str(executable), {}

    pythonpath: list[str] = []
    agent_root = venv_dir.parent
    if (agent_root / "hermes_cli").is_dir():
        pythonpath.append(str(agent_root))
    pythonpath.append(str(site_packages))
    if os.environ.get("PYTHONPATH"):
        pythonpath.append(os.environ["PYTHONPATH"])
    return str(base_python), {
        "VIRTUAL_ENV": str(venv_dir),
        "PYTHONPATH": os.pathsep.join(pythonpath),
    }
