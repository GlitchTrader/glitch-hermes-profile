"""Windows subprocess helpers for the installed Glitch Hermes profile."""

from __future__ import annotations

import os
import sys
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
