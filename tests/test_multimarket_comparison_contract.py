import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "run_direct_glitch_cycle_multimarket_contract",
    ROOT / "scripts" / "run-direct-glitch-cycle.py",
)
DIRECT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DIRECT)


INSTRUMENTS = ["MNQ", "MES", "M2K"]


def comparison(action="NOTHING", selected="MNQ"):
    lines = [DIRECT.CANDIDATE_COMPARISON_MARKER]
    for instrument in INSTRUMENTS:
        lines.append(f"INSTRUMENT {instrument}:")
        for field in DIRECT.CANDIDATE_COMPARISON_FIELDS:
            lines.append(f"{field}=supported {instrument} evidence")
    lines.extend([
        "RANKING=MNQ > MES > M2K",
        f"SELECTION_INSTRUMENT={selected}",
        f"SELECTION_ACTION={action}",
        f"SELECTION_EV=direction=LONG;entry=5000;stop=4988;target=5012;risk_points=12;reward_points=12;friction_points=0;breakeven_target_first=0.5;estimated_target_first_range=55-65%;now_ev={'POSITIVE' if action == 'ENTER_LONG' else 'NEGATIVE'};wait_price=5008;wait_ev=NEGATIVE;decisive_reason=fixture",
        "SELECTION_REASON=the complete comparison supports this bounded choice",
    ])
    return "\n".join(lines)


def test_complete_comparison_requires_both_paths_for_every_instrument():
    DIRECT.validate_candidate_comparison(comparison(), INSTRUMENTS, "MNQ", "NOTHING", 0)


def test_missing_instrument_is_rejected():
    text = comparison().replace("INSTRUMENT MES:\n", "")
    with pytest.raises(ValueError, match="candidate_comparison_instruments"):
        DIRECT.validate_candidate_comparison(text, INSTRUMENTS, "MNQ", "NOTHING", 0)


def test_missing_bearish_setup_is_rejected():
    text = comparison().replace("BEARISH_PATH=supported MES evidence", "BEARISH_PATH=REPLACE_WITH_CURRENT_PACKET_EVIDENCE")
    with pytest.raises(ValueError, match="candidate_comparison_field_placeholder"):
        DIRECT.validate_candidate_comparison(text, INSTRUMENTS, "MNQ", "NOTHING", 0)


def test_template_contains_every_supplied_instrument_and_required_states():
    text = DIRECT.candidate_comparison_template([{"instrument": value} for value in INSTRUMENTS])
    assert DIRECT.CANDIDATE_COMPARISON_MARKER in text
    for instrument in INSTRUMENTS:
        assert f"INSTRUMENT {instrument}:" in text
    for field in DIRECT.CANDIDATE_COMPARISON_FIELDS:
        assert f"{field}=REPLACE_WITH_CURRENT_PACKET_EVIDENCE" in text
    assert "SELECTION_INSTRUMENT=" in text
    assert "SELECTION_ACTION=" in text


def test_dry_run_does_not_persist_executable_outbox():
    source = (ROOT / "scripts" / "run-direct-glitch-cycle.py").read_text(encoding="utf-8")
    assert "if decision_mode == \"trigger_review\":\n            consume_fired_wake_triggers" in source
    assert "elif decision_mode == \"position_management\":\n            clear_wake_triggers" in source
    assert "if decision_mode == \"flat_scan\":\n                persist_wake_triggers" in source
    assert "persist_outbox(exchange, outbox_path, packet_id, batch, directive, packet)" in source
