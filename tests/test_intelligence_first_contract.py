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
            "pursue approximately",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, text)
        self.assertIn("current market packet", text)
        self.assertIn("no setup class is preferred", text)
        self.assertIn("no default instrument, fixed strategy, dollar stop, atr multiple, reward/risk floor", text)
        self.assertIn("daily monetary objective", text)

    def test_reference_vocabulary_contains_no_playbook_or_unverified_base_rates(self) -> None:
        text = REFERENCE_PATH.read_text(encoding="utf-8").lower()
        normalized = " ".join(text.split())
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
        self.assertIn("competing hypotheses", normalized)
        self.assertIn("unverified numeric base rate", normalized)
        self.assertIn("do not impose a fixed atr threshold", normalized)

    def test_intent_builder_preserves_user_configured_authority(self) -> None:
        text = (ROOT / "skills" / "glitch-build-intent" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()
        self.assertIn("user-configured constraint", text)
        self.assertIn("must not replace", text)
        self.assertNotIn("arbitrary compliance", text)

    def test_entry_cognition_prices_latency_once_without_independent_gates(self) -> None:
        soul = (ROOT / "SOUL.md").read_text(encoding="utf-8").lower()
        scan = (ROOT / "skills" / "glitch-market-scan" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()
        intent = (ROOT / "skills" / "glitch-build-intent" / "SKILL.md").read_text(
            encoding="utf-8"
        ).lower()

        self.assertNotIn("independently support the trade", soul)
        self.assertIn("never back-solve probability from a desired trade, repeat uncertainty as a second veto", soul)
        self.assertIn("future destination need not have traded already", scan)
        self.assertNotIn("until price accepts through the nearer objective", scan)
        self.assertIn("price plausible decision-to-delivery drift once", intent)
        self.assertIn("deterministic latest-price revalidation", intent)
        self.assertNotIn("across multiple one-minute packets", intent)


if __name__ == "__main__":
    unittest.main()
