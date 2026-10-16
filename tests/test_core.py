import csv
import tempfile
import unittest
from pathlib import Path

from oscar.config import Config
from oscar.data import load_csv
from oscar.models import Candle
from oscar.setups import detect
from oscar.backtest import _evaluate, summary
from oscar.paper import open_from_scan, close_trade
from oscar.alerts import write_alerts


class CoreTests(unittest.TestCase):
    def test_invalid_ohlc_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("symbol,date,timeframe,open,high,low,close,volume\nX,2026-01-01,1d,10,5,9,10,100\n")
            with self.assertRaises(ValueError):
                load_csv(str(path))

    def test_insufficient_history_has_no_signal(self):
        candles = [Candle("X", str(i), "1d", 10, 11, 9, 10, 100) for i in range(50)]
        self.assertEqual(detect(candles, Config()), [])

    def test_stop_wins_when_same_bar_hits_stop_and_target(self):
        candidate = type("Candidate", (), dict(symbol="X", setup_family="breakout", timeframe="1d", signal_date="1", entry_price=100.0, stop_loss=95.0, target_1=110.0, target_2=115.0, target_3=120.0, data_source="test", strategy_version="test"))()
        bar = Candle("X", "2", "1d", 100, 111, 94, 109, 1000)
        trade = _evaluate(candidate, [bar])
        self.assertEqual(trade["exit_reason"], "stop_loss")

    def test_furthest_target_is_recorded_when_one_bar_crosses_multiple(self):
        candidate = type("Candidate", (), dict(symbol="X", setup_family="breakout", timeframe="1d", signal_date="1", entry_price=100.0, stop_loss=95.0, target_1=110.0, target_2=115.0, target_3=120.0, data_source="test", strategy_version="test"))()
        bar = Candle("X", "2", "1d", 100, 121, 99, 120, 1000)
        trade = _evaluate(candidate, [bar])
        self.assertEqual(trade["exit_reason"], "T-3")
        self.assertEqual(trade["target_hit"], "T-3")

    def test_summary_win_percentage(self):
        rows = [{"setup_family": "breakout", "timeframe": "1d", "target_hit": "T-1", "return_r": 2, "exit_reason": "T-1"}, {"setup_family": "breakout", "timeframe": "1d", "target_hit": "none", "return_r": -1, "exit_reason": "stop_loss"}]
        self.assertEqual(summary(rows)[0]["win_pct"], 50.0)

    def test_paper_and_alert_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            scan = Path(directory) / "scan.csv"
            ledger = Path(directory) / "paper.csv"
            alerts = Path(directory) / "alerts.txt"
            fields = ["symbol", "setup_family", "timeframe", "signal_date", "status", "entry_price", "stop_loss", "target_1", "target_2", "target_3", "risk_reward_t1", "reason_codes", "strategy_version"]
            with scan.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerow({"symbol":"X", "setup_family":"breakout", "timeframe":"1d", "signal_date":"2026-01-01", "status":"triggered", "entry_price":"100", "stop_loss":"95", "target_1":"110", "target_2":"115", "target_3":"120", "risk_reward_t1":"2", "reason_codes":"test", "strategy_version":"test"})
            self.assertEqual(open_from_scan(str(scan), str(ledger)), 1)
            write_alerts(str(scan), str(alerts))
            self.assertIn("X", alerts.read_text())
            close_trade(str(ledger), "X|1d|breakout|2026-01-01", 110, "T-1")
            self.assertIn("CLOSED", ledger.read_text())


if __name__ == "__main__":
    unittest.main()
