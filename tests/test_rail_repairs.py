import importlib.util
import hashlib
import json
import re
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "reconcile_hermes_outcomes",
    ROOT / "scripts" / "reconcile-hermes-outcomes.py",
)
RECONCILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RECONCILER)

LEARNING_SPEC = importlib.util.spec_from_file_location(
    "run_hermes_learning_cycle",
    ROOT / "scripts" / "run-hermes-learning-cycle.py",
)
LEARNING = importlib.util.module_from_spec(LEARNING_SPEC)
assert LEARNING_SPEC.loader is not None
LEARNING_SPEC.loader.exec_module(LEARNING)
DIRECT_WORKER = ROOT / "scripts" / "run-direct-glitch-cycle.py"
import win_subprocess as WIN_SUBPROCESS


class RailRepairTests(unittest.TestCase):
    def test_setup_supports_current_hermes_agent_python_layout(self):
        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn("hermes\\hermes-agent\\venv\\Scripts\\python.exe", setup)

    def test_distribution_checksum_manifest_matches_every_owned_file(self):
        manifest = (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertTrue(manifest)
        for line in manifest:
            if not line.strip():
                continue
            expected, relative = re.split(r"\s{2,}", line, maxsplit=1)
            path = ROOT / relative
            with self.subTest(path=relative):
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), expected)

    def test_durable_decision_log_survives_outbox_consumption(self):
        with tempfile.TemporaryDirectory() as directory:
            decision_log = Path(directory) / "decisions.jsonl"
            decision_log.write_text(
                json.dumps({
                    "schema_version": "glitch.intent.decision.v1",
                    "cycle_id": "cycle-1",
                    "intent": {
                        "schema_version": "glitch.intent.v3",
                        "intent_id": "durable-intent",
                        "action": "ENTER_LONG",
                    },
                }) + "\n",
                encoding="utf-8",
            )
            intents = RECONCILER.find_intents(decision_log=decision_log)
            self.assertEqual(intents["durable-intent"]["action"], "ENTER_LONG")
            self.assertEqual(intents["durable-intent"]["_cycle_id"], "cycle-1")

    def test_learning_output_uses_system_owned_hourly_identity(self):
        expected_id = "hourly-review-system-id"
        value = LEARNING.output_template("hourly", ["model-echoed-id"])
        value["records"][0]["review_id"] = "model-echoed-id"

        records = LEARNING.validate_output(value, "hourly", [expected_id])

        self.assertEqual(records[0]["review_id"], expected_id)

    def test_learning_process_text_handles_missing_output(self):
        self.assertEqual(LEARNING.process_text(None), "")
        self.assertEqual(LEARNING.process_text("valid utf-8 output"), "valid utf-8 output")

    def test_learning_yields_to_a_waiting_trading_decision(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            WIN_SUBPROCESS.Path, "home", return_value=Path(directory)
        ):
            runtime = (
                Path(directory) / "AppData" / "Local" / "hermes" / "profiles"
                / "glitch" / "runtime"
            )
            runtime.mkdir(parents=True)
            (runtime / "hermes-cli.operator-waiting.123").write_text("pid=123\n")
            self.assertTrue(WIN_SUBPROCESS.hermes_operator_waiting("glitch"))

        source = (ROOT / "scripts" / "run-hermes-learning-cycle.py").read_text(encoding="utf-8")
        self.assertIn("if hermes_operator_waiting(profile):", source)
        self.assertIn('raise LearningDeferred("trading_decision_waiting")', source)
        self.assertIn('"status": "deferred"', source)
        popen_call = source.split("process = subprocess.Popen(", 1)[1].split(")\n", 1)[0]
        self.assertNotIn("timeout=", popen_call)
        self.assertNotIn("check=", popen_call)

    def test_learning_invokes_hermes_through_popen(self):
        process = mock.Mock()
        process.stdin = object()
        process.args = ["python", "-c", "wrapper"]
        process.returncode = 0
        process.communicate.return_value = ("{}", "")
        process.poll.return_value = 0
        expected = {"schema_version": "glitch.hermes.learning_output.v1"}
        with mock.patch.object(LEARNING.shutil, "which", return_value="C:/hermes/hermes.exe"), \
             mock.patch.object(LEARNING.Path, "is_file", return_value=True), \
             mock.patch.object(LEARNING, "resolve_python_invocation", return_value=("python", {})), \
             mock.patch.object(LEARNING, "hermes_profile_lock", return_value=nullcontext()), \
             mock.patch.object(LEARNING.subprocess, "Popen", return_value=process) as popen, \
             mock.patch.object(LEARNING.DIRECT, "extract_json", return_value=expected):
            self.assertEqual(LEARNING.invoke_hermes("glitch", "prompt", "skill", 10), expected)
        self.assertNotIn("timeout", popen.call_args.kwargs)
        self.assertNotIn("check", popen.call_args.kwargs)

    def test_completed_entry_intent_survives_packet_rollover(self):
        source = DIRECT_WORKER.read_text(encoding="utf-8")
        self.assertNotIn("discard_stale_entry_batch", source)
        self.assertNotIn("intent_discarded_stale_packet", source)
        self.assertNotIn("stale_packet_discarded", source)
        self.assertIn(
            "persist_outbox(exchange, outbox_path, packet_id, batch, directive, packet)",
            source,
        )

    def test_distribution_version_is_consistent(self):
        distribution = (ROOT / "distribution.yaml").read_text(encoding="utf-8")
        match = re.search(r"(?m)^version:\s*([^\s]+)\s*$", distribution)
        self.assertIsNotNone(match)
        version = match.group(1)
        self.assertRegex(version, r"^\d+\.\d+\.\d+\.\d+$")

        readme = (ROOT / "README.md").read_text(encoding="utf-8-sig")
        self.assertIn(f"v{version}", readme.splitlines()[0])

        setup = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn(f"distribution_version = '{version}'", setup)

        ledger = json.loads((ROOT / "docs" / "ledger" / "ledger.json").read_text(encoding="utf-8"))
        rail = next(item for item in ledger["items"] if item["id"] == "GHP-003")
        self.assertIn(version, "\n".join(rail.get("evidence") or []))

    def test_epoch_reset_clears_derived_peak_state_only(self):
        reset = (ROOT / "scripts" / "reset-hermes-trading-epoch.ps1").read_text(encoding="utf-8")
        backend_targets = reset.split("$backendTargets = @(", 1)[1].split(")", 1)[0]
        self.assertIn("'AccountPeaks.tsv'", backend_targets)
        self.assertNotIn("'Journal.tsv'", backend_targets)
        self.assertIn("Reload the Glitch AddOn before re-enabling AI", reset)

    def test_epoch_reset_verifies_learning_checkpoint_before_deletion(self):
        reset = (ROOT / "scripts" / "reset-hermes-trading-epoch.ps1").read_text(encoding="utf-8")
        checkpoint_call = reset.index("$checkpoint = New-VerifiedCheckpoint")
        first_removal = reset.index("Remove-ResetTarget -Path $target", checkpoint_call)
        self.assertLess(checkpoint_call, first_removal)
        self.assertIn("Get-FileHash -LiteralPath $checkpointFile -Algorithm SHA256", reset)
        self.assertIn("hermes\\exchange\\hermes\\supervisor", reset)
        self.assertIn("$checkpointBytes += [long]$entry.bytes", reset)
        self.assertIn("backup_created = $true", reset)
        self.assertNotIn("AllowUnbackedReset", reset)


if __name__ == "__main__":
    unittest.main()
