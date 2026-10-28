import unittest

from oscar.models import Candle
from oscar import retest


def series(closes, volume=1e6):
    return [Candle("X", f"2020-01-{i:04d}", "1d", c, c * 1.01, c * 0.99, c, volume) for i, c in enumerate(closes)]


class RetestTests(unittest.TestCase):
    def test_regime_requires_nifty_above_200dma_and_rising_50dma(self):
        up = retest.market_regime(series([100 + i for i in range(260)]))
        down = retest.market_regime(series([400 - i for i in range(260)]))
        self.assertTrue(list(up.values())[-1])
        self.assertFalse(list(down.values())[-1])

    def test_data_problem_flags_unadjusted_split(self):
        self.assertIsNone(retest.data_problem(series([100, 101, 102])))
        self.assertIn("split", retest.data_problem(series([100, 101, 50])))

    def test_stop_never_more_than_ten_percent(self):
        s = retest._Series(series([100.0] * 300), {})
        self.assertEqual(s.stop(260, 270, 200.0), 180.0)

    def test_targets_use_overhead_swing_high_then_measured_moves(self):
        closes = [100.0] * 300
        closes[150] = 150.0  # a lone swing high well above entry
        s = retest._Series(series(closes), {})
        t = s.targets(290, 101.0, 101.0, 95.0)
        self.assertAlmostEqual(t[0], 151.5)
        self.assertEqual(len(t), 3)
        self.assertTrue(t[0] < t[1] < t[2])

    def test_summarize_counts_wins_and_losing_streak(self):
        trades = [{"return_pct": x, "exit_date": f"2020-01-0{i}"} for i, x in enumerate([5.0, -2.0, -3.0, 4.0], 1)]
        s = retest.summarize(trades)
        self.assertEqual((s["trades"], s["win_rate"], s["max_losing_streak"], s["profit_factor"]), (4, 50.0, 2, 1.8))


if __name__ == "__main__":
    unittest.main()
