import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from oscar.sources import _request, fallback_candles, stooq_candles, nse_equity_symbols


class SourceTests(unittest.TestCase):
    def test_nse_universe_filters_eq_symbols(self):
        payload = b"SYMBOL,SERIES\nRELIANCE,EQ\nNIFTY,INDEX\nTCS,EQ\n"
        with patch("oscar.sources._request", return_value=payload):
            self.assertEqual(nse_equity_symbols(), ["RELIANCE", "TCS"])

    def test_stooq_normalizes_daily_csv(self):
        payload = b"Symbol,Date,Open,High,Low,Close,Volume\nreliance.in,2026-01-02,100,110,95,108,1234\n"
        with patch("oscar.sources._request", return_value=payload):
            rows = stooq_candles("RELIANCE.NS")
        self.assertEqual(rows[0]["symbol"], "RELIANCE")
        self.assertEqual(rows[0]["timeframe"], "1d")
        self.assertEqual(rows[0]["close"], "108")

    def test_fallback_uses_stooq_when_yahoo_fails(self):
        with patch("oscar.sources.public_chart_candles", side_effect=RuntimeError("offline")), patch("oscar.sources.stooq_candles", return_value=[{"symbol":"X","date":"2026-01-01","timeframe":"1d","open":1,"high":2,"low":1,"close":2,"volume":10}]):
            rows = fallback_candles("X.NS")
        self.assertEqual(rows[0]["symbol"], "X")

    def test_fallback_rejects_intraday_without_yahoo(self):
        with patch("oscar.sources.public_chart_candles", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                fallback_candles("X.NS", "1h")

    def test_http_errors_include_provider_reason(self):
        error = HTTPError("https://example.test", 403, "Forbidden", {}, BytesIO(b'{"message":"Insufficient permission"}'))
        with patch("oscar.sources.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP Error 403: Insufficient permission"):
                _request("https://example.test")
