"""Tests must never read/write the operator's real provider-usage hold."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import win_subprocess


@pytest.fixture(autouse=True)
def isolate_provider_usage_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        win_subprocess, "_provider_hold_path",
        lambda profile: tmp_path / "provider-state" / profile / "provider-usage-hold.json",
    )
