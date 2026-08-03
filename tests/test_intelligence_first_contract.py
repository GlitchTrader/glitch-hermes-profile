from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOT_PATHS = (
    ROOT / "SOUL.md",
    ROOT / "skills" / "glitch-trade-mnq" / "SKILL.md",
    ROOT / "skills" / "glitch-build-intent" / "SKILL.md",
)
REFERENCE_PATH = ROOT / "skills" / "glitch-market-structure" / "SKILL.md"


class IntelligenceFirstContractTests(unittest.TestCase):
    def test_hot_path_contains_no_encoded_strategy_recipe(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in HOT_PATHS).lower()
        forbidden = (
            "0.4%-2%",
            "25k master",
            "250k master",
            "40-point",
            "20 points",
            "3+3+3",
            "ruthless profit",
            "half or more of the way",
            "daily monetary objective",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, text)
        self.assertIn("current packet", text)
        self.assertIn("no setup class is preferred", text)
        self.assertIn("there is no fixed distance", text)

    def test_reference_vocabulary_contains_no_playbook_or_unverified_base_rates(self) -> None:
        text = REFERENCE_PATH.read_text(encoding="utf-8").lower()
        forbidden = (
            "inside-bar continuation",
            "ascending triangle",
            "descending triangle",
            "initial-balance breakout",
            "trend days punish",
            "fade edges",
            "three stops in the same zone",
            "1× atr",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, text)
        self.assertIn("competing hypotheses", text)
        self.assertIn("no unverified numeric base rate", text)

    def test_intent_builder_preserves_user_configured_authority(self) -> None:
        text = (ROOT / "skills" / "glitch-build-intent" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()
        self.assertIn("user-configured constraint", text)
        self.assertIn("must not replace", text)
        self.assertNotIn("arbitrary compliance", text)


if __name__ == "__main__":
    unittest.main()
