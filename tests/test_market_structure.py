"""Deterministic tests for the market-structure observation layer."""

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import market_structure as ms  # noqa: E402


def bar(minute: int, o, h, l, c, atr=4.0):
    return {"id": f"20260731T{minute // 60:02d}{minute % 60:02d}Z",
            "o": float(o), "h": float(h), "l": float(l), "c": float(c), "atr": atr}


def packet_with_bars(bars, current_price, session=None, atr_60=20.0, adx_60=15.0):
    frames = []
    for record in bars[-5:]:
        frames.append({
            "minute_id": record["id"],
            "market_snapshot": {
                "instruments": [{
                    "instrument": "MNQ",
                    "current_price": current_price,
                    "session": session or {"name": "Asia", "high": 28580.0, "low": 28304.25,
                                           "previous_high": 28410.0, "previous_low": 28147.75},
                    "timeframe_bars": [
                        {"minutes": 1, "open": record["o"], "high": record["h"],
                         "low": record["l"], "close": record["c"],
                         "indicators": {"atr": record["atr"]}},
                        {"minutes": 60, "open": 0, "high": 0, "low": 0, "close": 0,
                         "indicators": {"atr": atr_60, "adx": adx_60}},
                    ],
                }],
            },
        })
    return {"frames": frames}


def uptrend_bars(count=80, start=28400.0, step=1.5):
    bars = []
    price = start
    for minute in range(count):
        swing = 6.0 if (minute // 10) % 2 == 0 else -3.0
        price += step if swing > 0 else -0.5
        bars.append(bar(minute, price - 1, price + 2, price - 2, price))
    return bars


def range_bars(count=80, low=28400.0, high=28440.0):
    bars = []
    for minute in range(count):
        phase = (minute % 20) / 20.0
        mid = low + (high - low) * (0.5 + 0.45 * (1 if phase < 0.5 else -1) * (phase % 0.5) * 2)
        bars.append(bar(minute, mid - 1, min(high, mid + 3), max(low, mid - 3), mid))
    return bars


class SwingTests(unittest.TestCase):
    def test_uptrend_labels_higher_highs_and_lows(self):
        pivots = ms.swing_pivots(uptrend_bars(), atr_1m=3.0)
        labels = [p["label"] for p in pivots]
        self.assertTrue(labels, "uptrend must produce pivots")
        self.assertIn("HH", labels)
        bias = ms.structure_bias(labels)
        self.assertIn(bias, ("up", "mixed"))

    def test_flat_ledger_produces_no_false_trend(self):
        flat = [bar(i, 28400, 28401, 28399, 28400) for i in range(40)]
        pivots = ms.swing_pivots(flat, atr_1m=4.0)
        self.assertEqual(pivots, [])
        self.assertEqual(ms.structure_bias([]), "mixed")

    def test_determinism(self):
        bars = uptrend_bars()
        self.assertEqual(ms.swing_pivots(bars, 3.0), ms.swing_pivots(bars, 3.0))


class RangeAndBreakoutTests(unittest.TestCase):
    def test_range_box_bounds(self):
        box = ms.range_box(range_bars())
        self.assertIsNotNone(box)
        self.assertLessEqual(box["low"], box["mid"])
        self.assertLessEqual(box["mid"], box["high"])

    def test_accepted_breakout_above(self):
        bars = range_bars()
        top = max(b["h"] for b in bars[-60:])
        for i in range(3):
            price = top + 5 + i
            bars.append(bar(100 + i, price - 1, price + 1, price - 2, price))
        state = ms.breakout_state(bars, ms.range_box(bars))
        self.assertEqual(state, "accepted_above")

    def test_failed_break_high(self):
        bars = range_bars()
        top = max(b["h"] for b in bars[-60:])
        bars.append(bar(100, top - 1, top + 4, top - 2, top - 1.5))  # poke and close back
        bars.append(bar(101, top - 2, top - 1, top - 6, top - 5))
        bars.append(bar(102, top - 5, top - 4, top - 9, top - 8))
        state = ms.breakout_state(bars, ms.range_box(bars))
        self.assertEqual(state, "failed_break_high")

    def test_inside_range(self):
        bars = range_bars()
        state = ms.breakout_state(bars, ms.range_box(bars))
        self.assertIn(state, ("inside", "testing_high", "testing_low"))


class RegimeHysteresisTests(unittest.TestCase):
    def test_label_flips_only_after_repeated_agreement(self):
        state = {"regime": {"label": "range", "stable_cycles": 10}}
        box = {"high": 28440.0, "low": 28400.0, "mid": 28420.0, "width": 40.0}
        first = ms.regime_hypothesis(state, adx_60m=30.0, box=box, atr_60m=20.0, bias="up")
        self.assertEqual(first["label"], "range")  # not yet flipped
        self.assertEqual(first["raw"], "directional_up")
        ms.regime_hypothesis(state, 30.0, box, 20.0, "up")
        third = ms.regime_hypothesis(state, 30.0, box, 20.0, "up")
        self.assertEqual(third["label"], "directional_up")

    def test_disagreeing_raw_resets_pending(self):
        state = {"regime": {"label": "range", "stable_cycles": 5}}
        box = {"high": 28440.0, "low": 28400.0, "mid": 28420.0, "width": 40.0}
        ms.regime_hypothesis(state, 30.0, box, 20.0, "up")
        ms.regime_hypothesis(state, 10.0, box, 20.0, "mixed")  # back to range agreement
        result = ms.regime_hypothesis(state, 30.0, box, 20.0, "up")
        self.assertEqual(result["label"], "range")


class FvgTests(unittest.TestCase):
    def test_bullish_gap_detected_until_filled(self):
        bars = [bar(0, 28400, 28402, 28398, 28401),
                bar(1, 28401, 28410, 28400, 28409),
                bar(2, 28409, 28415, 28406, 28414)]  # low 28406 > first high 28402
        zones = ms.fvg_zones(bars, current_price=28414.0)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0]["side"], "bullish")
        bars.append(bar(3, 28414, 28414, 28401, 28402))  # trades through the gap bottom
        self.assertEqual(ms.fvg_zones(bars, 28402.0), [])


class LedgerTests(unittest.TestCase):
    def test_update_bars_dedupes_and_prunes(self):
        state = {"schema_version": ms.SCHEMA_VERSION, "bars": [], "regime": {}}
        bars = uptrend_bars(12)
        packet = packet_with_bars(bars, 28430.0)
        ms.update_bars(state, packet)
        count = len(state["bars"])
        ms.update_bars(state, packet)  # same frames again
        self.assertEqual(len(state["bars"]), count)
        state["bars"] = [bar(i, 28400, 28401, 28399, 28400) for i in range(ms.MAX_BARS + 30)]
        ms.update_bars(state, packet)
        self.assertLessEqual(len(state["bars"]), ms.MAX_BARS)

    def test_state_round_trip(self):
        import tempfile
        state = {"schema_version": ms.SCHEMA_VERSION, "bars": [bar(0, 1, 2, 0, 1)],
                 "regime": {"label": "range"}, "last_minute_id": "20260731T0000Z"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            ms.save_state(path, state)
            loaded = ms.load_state(path)
        self.assertEqual(loaded["regime"]["label"], "range")
        self.assertEqual(len(loaded["bars"]), 1)


class ObservationTests(unittest.TestCase):
    def _observe(self, bars, price, **kwargs):
        state = {"schema_version": ms.SCHEMA_VERSION, "bars": list(bars), "regime": {}}
        packet = packet_with_bars(bars, price, **kwargs)
        return ms.build_observations(packet, state, Path("Z:/definitely-missing"),
                                     now=datetime(2026, 7, 31, 5, 0, tzinfo=timezone.utc))

    def test_block_shape_and_budget(self):
        obs = self._observe(range_bars(), 28420.0)
        self.assertTrue(obs["available"])
        self.assertEqual(obs["schema_version"], ms.SCHEMA_VERSION)
        for key in ("regime_60m", "location", "swings_1m", "structure_bias",
                    "fvg_zones", "key_levels", "own_recent_attempts"):
            self.assertIn(key, obs)
        serialized = json.dumps(obs, separators=(",", ":"))
        self.assertLessEqual(len(serialized), ms.MAX_SERIALIZED_CHARS + 400)

    def test_warmup_is_neutral(self):
        obs = self._observe(range_bars()[:4], 28420.0)
        self.assertFalse(obs["available"])
        self.assertEqual(obs["reason"], "ledger_warming_up")

    def test_missing_outcome_files_do_not_break(self):
        obs = self._observe(range_bars(), 28420.0)
        self.assertEqual(obs["own_recent_attempts"]["last_trades"], [])
        self.assertEqual(obs["own_recent_attempts"]["recent_losses_near_price"], 0)

    def test_key_levels_include_session_and_touch_counts(self):
        obs = self._observe(range_bars(), 28420.0)
        kinds = {level["kind"] for level in obs["key_levels"]}
        self.assertTrue(kinds & {"range_high", "range_low", "range_mid",
                                 "session_high", "session_low"})
        for level in obs["key_levels"]:
            if "touches" in level:
                self.assertGreaterEqual(level["touches"], 0)


class AttemptTests(unittest.TestCase):
    def test_recent_losses_near_price_counted(self):
        import tempfile
        now = datetime(2026, 7, 31, 5, 0, tzinfo=timezone.utc)
        records = [
            {"action": "ENTER_LONG", "planned_stop": 28418.0, "planned_target": 28480.0,
             "master_realized_pnl_usd": -58.6, "exit_utc": "2026-07-31T04:40:00Z"},
            {"action": "ENTER_LONG", "planned_stop": 28419.5, "planned_target": 28500.0,
             "master_realized_pnl_usd": -42.0, "exit_utc": "2026-07-31T04:50:00Z"},
            {"action": "ENTER_SHORT", "planned_stop": 28600.0, "planned_target": 28500.0,
             "master_realized_pnl_usd": 140.0, "exit_utc": "2026-07-31T03:00:00Z"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            outcomes = Path(tmp) / "outcomes.jsonl"
            outcomes.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
            result = ms.recent_attempts(Path(tmp) / "missing.jsonl", outcomes,
                                        current_price=28420.0, now=now)
        self.assertEqual(result["recent_losses_near_price"], 2)
        self.assertEqual(len(result["last_trades"]), 3)


if __name__ == "__main__":
    unittest.main()
