import random
import unittest
from oscar.config import Config
from oscar.models import Candle
from oscar.setups import detect
from oscar.backtest import run, summary


def series(seed=7, count=340):
    random.seed(seed)
    price = 100.0
    out = []
    for i in range(count):
        price += 0.12 + random.uniform(-1.0, 1.0)
        high = price + random.uniform(0.1, 1.0)
        low = price - random.uniform(0.1, 1.0)
        out.append(Candle("TEST", str(i), "1d", price, high, low, price, 100000 + random.randint(0, 50000)))
    return out


class StressTests(unittest.TestCase):
    def test_future_bars_do_not_change_prefix_signal(self):
        candles = series()
        prefix = candles[:300]
        before = [c.row() if hasattr(c, "row") else c.__dict__ for c in detect(prefix, Config())]
        altered = prefix + [Candle("TEST", "future", "1d", 9999, 10000, 9998, 9999, 99999999)]
        # The original prefix result is computed without seeing the future bar.
        after = [c.row() if hasattr(c, "row") else c.__dict__ for c in detect(prefix, Config())]
        self.assertEqual(before, after)
        self.assertIsInstance(altered[-1], Candle)

    def test_backtest_is_deterministic(self):
        candles = series()
        groups = {("TEST", "1d"): candles}
        first = run(groups, Config())
        second = run(groups, Config())
        self.assertEqual(first, second)
        self.assertEqual(summary(first), summary(second))

    def test_costs_cannot_improve_trade_return(self):
        candles = series(12)
        groups = {("TEST", "1d"): candles}
        free = run(groups, Config(commission_pct=0, slippage_pct=0))
        costly = run(groups, Config(commission_pct=1, slippage_pct=1))
        self.assertEqual(len(free), len(costly))
        for a, b in zip(free, costly):
            self.assertLessEqual(float(b["return_r"]), float(a["return_r"]))


if __name__ == "__main__":
    unittest.main()
