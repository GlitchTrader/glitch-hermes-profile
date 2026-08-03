import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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


class RailRepairTests(unittest.TestCase):
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

    def test_completed_entry_intent_survives_packet_rollover(self):
        source = DIRECT_WORKER.read_text(encoding="utf-8")
        self.assertNotIn("discard_stale_entry_batch", source)
        self.assertNotIn("intent_discarded_stale_packet", source)
        self.assertNotIn("stale_packet_discarded", source)
        self.assertIn(
            "persist_outbox(exchange, outbox_path, packet_id, batch, directive)",
            source,
        )

    def test_distribution_version_is_current(self):
        distribution = (ROOT / "distribution.yaml").read_text(encoding="utf-8")
        self.assertIn("version: 0.0.2.20", distribution)


if __name__ == "__main__":
    unittest.main()
