import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconcile_hermes_outcomes",
    ROOT / "scripts" / "reconcile-hermes-outcomes.py",
)
RECONCILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RECONCILER)


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


if __name__ == "__main__":
    unittest.main()
