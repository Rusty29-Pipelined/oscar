import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from oscar.sources import _request, fallback_candles, stooq_candles, nse_equity_symbols, kite_candles, kite_equity_instruments


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

    def test_kite_universe_skips_bonds_series_and_inav(self):
        payload = b"instrument_token,tradingsymbol,name,segment,instrument_type\n1,RELIANCE,RELIANCE INDUSTRIES,NSE,EQ\n6,BAJAJ-AUTO,BAJAJ AUTO,NSE,EQ\n7,NIFTYBEES,NIPPON INDIA ETF NIFTY 50 BEES,NSE,EQ\n8,SMALLGROWW,GROWWAMC - SMALLGROWW,NSE,EQ\n2,0HFL28-N0,,NSE,EQ\n3,OMFURN-SM,,NSE,EQ\n4,ABSLLQINAV,,NSE,EQ\n5,NIFTY 50,,INDICES,EQ\n"
        with patch("oscar.sources._kite_get", return_value=payload):
            self.assertEqual(kite_equity_instruments(), {"RELIANCE": 1, "BAJAJ-AUTO": 6})

    def test_kite_hourly_history_is_chunked_under_400_days(self):
        urls = []
        def fake(url):
            urls.append(url)
            return b'{"data":{"candles":[["2026-01-01T09:15:00+0530",1,2,0.5,1.5,10]]}}'
        with patch("oscar.sources._kite_get", side_effect=fake):
            rows = kite_candles(1, "1hour", "2026-10-24", "2025-01-01", "X")
        self.assertEqual(len(urls), 2)
        self.assertIn("from=2025-01-01&to=2026-02-04", urls[0])
        self.assertIn("from=2026-02-05&to=2026-10-24", urls[1])
        self.assertEqual(len(rows), 2)


class KiteRetryTest(unittest.TestCase):
    def test_timeout_is_retried_then_succeeds(self):
        from unittest import mock
        from oscar import sources
        calls = []
        def flaky(url, headers=None):
            calls.append(url)
            if len(calls) < 3:
                raise TimeoutError("The read operation timed out")
            return b"ok"
        with mock.patch.object(sources, "_request", flaky), mock.patch.object(sources.time, "sleep"), \
                mock.patch.object(sources, "_kite_headers", lambda: {}):
            self.assertEqual(sources._kite_get("u"), b"ok")
        self.assertEqual(len(calls), 3)

    def test_auth_error_is_not_retried(self):
        from unittest import mock
        from oscar import sources
        calls = []
        def denied(url, headers=None):
            calls.append(url)
            raise RuntimeError("HTTP Error 403: Incorrect api_key or access_token")
        with mock.patch.object(sources, "_request", denied), mock.patch.object(sources.time, "sleep"), \
                mock.patch.object(sources, "_kite_headers", lambda: {}):
            with self.assertRaises(RuntimeError):
                sources._kite_get("u")
        self.assertEqual(len(calls), 1)
