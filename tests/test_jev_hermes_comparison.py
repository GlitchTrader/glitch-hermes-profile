import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/jev"))
from compare_hermes import command, parse_response, decision_summary


def test_offline_runner_refuses_live_home_and_plugins(tmp_path):
    with pytest.raises(ValueError, match="isolated_research_home_required"):
        command(Path("python"), tmp_path, False)
    home = tmp_path / "offline-home"; home.mkdir()
    (home / "RESEARCH_ONLY").touch()
    cmd = command(Path("python"), home, True)
    assert "tools=[],includes=[]" in cmd[-1]
    assert "'--source', 'research'" in cmd[-1]
    assert "'--max-turns', '1'" in cmd[-1]
    (home / "plugins").mkdir()
    (home / "plugins" / "native.py").write_text("native control")
    with pytest.raises(ValueError, match="must_not_have_plugins_or_cron"):
        command(Path("python"), home, False)


def test_response_parser_does_not_accept_prose_or_another_schema():
    for value in ['nothing', '{"schema_version":"other"}', '{broken']:
        with pytest.raises(ValueError, match="batch_json_not_found"):
            parse_response(value)
    batch = {"schema_version":"glitch.intent.batch.v1", "decisions":[]}
    assert parse_response("warning\n```json\n" + json.dumps(batch) + "\n```") == batch


def test_report_reads_native_decisions_and_only_attributes_audit_text():
    batch = {"decisions":[{"action":"NOTHING", "prompt_version":"direct-v28-jev",
                           "decision_audit":{"reason":"Path lacks room"}},
                          {"action":"HOLD", "decision_audit":{"reason":"Jev agrees with continuation"}}]}
    assert decision_summary(batch) == {"actions":["NOTHING","HOLD"], "jev_named_in_audit":[False,True]}
