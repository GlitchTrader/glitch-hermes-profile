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
    guarded = "if not args.dry_run:\n            persist_wake_triggers(exchange, batch, packet_id)\n            persist_outbox(exchange, outbox_path, packet_id, batch, directive, packet)"
    assert guarded in source
