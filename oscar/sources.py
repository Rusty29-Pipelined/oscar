"""Data-source adapters for P-1.

Adapters emit the normalized CSV contract used by the scanner. Network access
is intentionally opt-in; no credentials are stored in the repository.
"""
import csv
import hashlib
import io
import json
import os
import urllib.parse
import urllib.error
import urllib.request
import zipfile
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List, Dict, Optional


FIELDS = ["symbol", "date", "timeframe", "open", "high", "low", "close", "volume"]


def _kite_headers() -> Dict[str, str]:
    """Headers for Kite Connect v3 market-data requests."""
    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        raise RuntimeError("KITE_API_KEY and KITE_ACCESS_TOKEN are required")
    return {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}", "Accept": "application/json"}


def kite_equity_instruments() -> Dict[str, int]:
    """Return NSE EQ trading symbol -> Kite instrument token."""
    raw = _kite_get("https://api.kite.trade/instruments/NSE")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    result = {}
    for item in reader:
        if item.get("segment") != "NSE" or item.get("instrument_type") != "EQ":
            continue
        symbol = (item.get("tradingsymbol") or "").strip().upper()
        # Kite lists bonds, G-secs and non-EQ series (e.g. "-N0", "-SG", "-BE")
        # as instrument_type EQ, plus ETF iNAV feeds; plain symbols are EQ-series stocks.
        if "-" in symbol or symbol.endswith("INAV"):
            continue
        token = item.get("instrument_token")
        if symbol and token:
            result[symbol] = int(token)
    return result


# Kite caps each historical request by interval and allows ~3 requests/second.
KITE_MAX_DAYS = {"day": 2000, "60minute": 400}
KITE_MIN_GAP_SECONDS = 0.35
_last_kite_call = [0.0]


def kite_login_url() -> str:
    return "https://kite.zerodha.com/connect/login?v=3&api_key=" + urllib.parse.quote(os.environ.get("KITE_API_KEY", ""))


def kite_exchange_request_token(request_token: str) -> dict:
    """Swap a login request_token for a session (access_token, user_id)."""
    api_key = os.environ.get("KITE_API_KEY")
    secret = os.environ.get("KITE_API_SECRET")
    if not api_key or not secret:
        raise RuntimeError("KITE_API_KEY and KITE_API_SECRET are required for Kite login")
    checksum = hashlib.sha256((api_key + request_token + secret).encode()).hexdigest()
    body = urllib.parse.urlencode({"api_key": api_key, "request_token": request_token, "checksum": checksum}).encode()
    request = urllib.request.Request("https://api.kite.trade/session/token", body, {"X-Kite-Version": "3"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))["data"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("message") or detail
        except ValueError:
            pass
        raise RuntimeError(f"Kite login failed (HTTP {exc.code}): {str(detail)[:300]}") from None


def _kite_get(url: str) -> bytes:
    """Throttled Kite GET with one retry on rate limiting."""
    for attempt in range(2):
        wait = KITE_MIN_GAP_SECONDS - (time.monotonic() - _last_kite_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_kite_call[0] = time.monotonic()
        try:
            return _request(url, _kite_headers())
        except RuntimeError as exc:
            if attempt == 0 and str(exc).startswith("HTTP Error 429"):
                time.sleep(1.0)
                continue
            raise


def kite_candles(instrument_token: int, interval: str, to_date: str, from_date: Optional[str] = None, symbol: str = "") -> List[dict]:
    """Fetch Kite historical candles and normalize them to OSCAR rows."""
    interval_map = {"1day": "day", "day": "day", "1hour": "60minute", "4hour": "60minute", "1week": "day", "1wk": "day"}
    kite_interval = interval_map.get(interval, interval)
    end = date.fromisoformat(to_date)
    start = date.fromisoformat(from_date or to_date)
    step = timedelta(days=KITE_MAX_DAYS.get(kite_interval, 60) - 1)
    path = f"https://api.kite.trade/instruments/historical/{int(instrument_token)}/{kite_interval}"
    candles = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + step, end)
        query = urllib.parse.urlencode({"from": str(chunk_start), "to": str(chunk_end)})
        payload = json.loads(_kite_get(path + "?" + query).decode("utf-8"))
        candles.extend(payload.get("data", {}).get("candles", []))
        chunk_start = chunk_end + timedelta(days=1)
    rows = []
    for candle in candles:
        timestamp, op, hi, lo, close, volume = candle[:6]
        rows.append({"symbol": symbol, "date": timestamp, "timeframe": interval, "open": op, "high": hi, "low": lo, "close": close, "volume": volume})
    # Kite has no native 4-hour or weekly candle endpoint; aggregate daily/hourly
    # data in the scanner later rather than silently labeling 60-minute candles.
    if interval == "4hour":
        rows = _aggregate_rows(rows, 4)
    elif interval in ("1week", "1wk"):
        rows = _aggregate_rows(rows, 5)
    return rows


def _aggregate_rows(rows: List[dict], bucket: int) -> List[dict]:
    """Small deterministic OHLCV aggregation helper for Kite intervals."""
    if not rows:
        return rows
    result = []
    for start in range(0, len(rows), bucket):
        group = rows[start:start + bucket]
        result.append({"symbol": group[0]["symbol"], "date": group[0]["date"], "timeframe": group[0]["timeframe"], "open": group[0]["open"], "high": max(r["high"] for r in group), "low": min(r["low"] for r in group), "close": group[-1]["close"], "volume": sum(float(r["volume"] or 0) for r in group)})
    return result


def nse_equity_symbols() -> List[str]:
    """Return the current NSE cash-equity symbol universe (EQ series only)."""
    urls = (
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
        "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    )
    errors = []
    for url in urls:
        try:
            raw = _request(url, {"User-Agent": "Mozilla/5.0 OSCAR research", "Accept": "text/csv,*/*"})
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            symbols = []
            for row in reader:
                symbol = (row.get("SYMBOL") or row.get("Symbol") or "").strip().upper()
                series = (row.get(" SERIES") or row.get("SERIES") or "EQ").strip().upper()
                if symbol and series == "EQ":
                    symbols.append(symbol)
            if symbols:
                return sorted(set(symbols))
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("Unable to load NSE equity universe: " + " | ".join(errors))


def _request(url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "OSCAR/0.1 research"})
    timeout = float(os.environ.get("OSCAR_HTTP_TIMEOUT", "15"))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail = ""
        try:
            payload = json.loads(body)
            detail = payload.get("message") or payload.get("error") or ""
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("error") or ""
        except (TypeError, ValueError):
            detail = ""
        detail = str(detail or body or exc.reason).strip()[:300]
        raise RuntimeError(f"HTTP Error {exc.code}: {detail}") from None


def write_rows(rows: Iterable[dict], path: str, mode: str = "w") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    exists = target.exists() and target.stat().st_size > 0 and mode == "a"
    with target.open(mode, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def nse_bhavcopy(day: str, url_template: Optional[str] = None) -> List[dict]:
    """Download an NSE CM Bhavcopy ZIP and emit daily EQ rows.

    NSE periodically changes archive naming; URL_TEMPLATE can be supplied to
    keep the adapter configurable without changing code.
    """
    compact = day.replace("-", "")
    template = url_template or os.environ.get("NSE_BHAVCOPY_URL_TEMPLATE", "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip")
    raw = _request(template.format(date=compact))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if not names:
            return []
        with archive.open(names[0]) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8-sig")
            reader = csv.DictReader(text)
            rows = []
            for row in reader:
                symbol = (row.get("TckrSymb") or row.get("SYMBOL") or "").strip()
                series = (row.get("SctySrs") or row.get("SERIES") or "EQ").strip()
                if not symbol or series != "EQ":
                    continue
                rows.append({"symbol": symbol, "date": day, "timeframe": "1d", "open": row.get("OpnPric") or row.get("OPEN_PRICE"), "high": row.get("HghPric") or row.get("HIGH_PRICE"), "low": row.get("LwPric") or row.get("LOW_PRICE"), "close": row.get("ClsPric") or row.get("CLOSE_PRICE"), "volume": row.get("TtlTrdVol") or row.get("TOTTRDQTY")})
            return [r for r in rows if all(r[k] not in (None, "") for k in FIELDS)]


def public_chart_candles(symbol: str, interval: str = "1d", period1: int = 0, period2: Optional[int] = None) -> List[dict]:
    """Fallback public chart-data adapter for research, not execution.

    Uses the public chart endpoint for symbols such as RELIANCE.NS. Coverage
    and retention vary by interval, so every row is marked `public-chart` and
    should be cross-checked against NSE data before live use.
    """
    period2 = period2 or int(time.time())
    query = urllib.parse.urlencode({"period1": period1, "period2": period2, "interval": interval, "events": "history", "includeAdjustedClose": "true"})
    payload = json.loads(_request("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?" + query))
    result = payload.get("chart", {}).get("result", [None])[0]
    if not result:
        raise RuntimeError("Public chart source returned no data for " + symbol)
    timestamps = result.get("timestamp", [])
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    rows = []
    for i, stamp in enumerate(timestamps):
        values = [quote.get(k, [None] * len(timestamps))[i] for k in ("open", "high", "low", "close", "volume")]
        if any(v is None for v in values):
            continue
        rows.append({"symbol": symbol.removesuffix(".NS"), "date": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(stamp)), "timeframe": interval, "open": values[0], "high": values[1], "low": values[2], "close": values[3], "volume": values[4]})
    return rows


def stooq_candles(symbol: str) -> List[dict]:
    """Fetch daily candles from Stooq's public CSV endpoint."""
    code = symbol.lower().replace(".ns", ".in")
    raw = _request("https://stooq.com/q/d/l/?s=" + urllib.parse.quote(code, safe="._") + "&i=d")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows = []
    for row in reader:
        if not row.get("Date") or row.get("Close") in (None, "", "N/D"):
            continue
        rows.append({"symbol": symbol.removesuffix(".NS"), "date": row["Date"], "timeframe": "1d", "open": row.get("Open"), "high": row.get("High"), "low": row.get("Low"), "close": row.get("Close"), "volume": row.get("Volume") or 0})
    return [r for r in rows if all(r[k] not in (None, "") for k in FIELDS)]


def fallback_candles(symbol: str, interval: str = "1d", period1: int = 0, period2: Optional[int] = None) -> List[dict]:
    """Try keyless public providers: Yahoo first, Stooq for daily data."""
    errors = []
    try:
        rows = public_chart_candles(symbol, interval, period1, period2)
        if rows:
            return rows
    except Exception as exc:
        errors.append("yahoo: " + str(exc))
    if interval not in ("1d", "1wk", "1w"):
        raise RuntimeError("No keyless fallback supports interval " + interval)
    try:
        rows = stooq_candles(symbol)
        if rows:
            return rows
    except Exception as exc:
        errors.append("stooq: " + str(exc))
    raise RuntimeError("All public data providers failed for " + symbol + (": " + "; ".join(errors) if errors else ""))


def jugaad_candles(symbol: str, start: str, end: str) -> List[dict]:
    """Optional NSE fallback through jugaad-data when installed."""
    try:
        from jugaad_data.nse import stock_df
    except ImportError as exc:
        raise RuntimeError("Install the optional jugaad-data package to use this adapter") from exc
    frame = stock_df(symbol=symbol, from_date=start, to_date=end, series="EQ")
    rows = []
    for _, row in frame.iterrows():
        rows.append({"symbol": symbol, "date": str(row.get("DATE")), "timeframe": "1d", "open": row.get("OPEN"), "high": row.get("HIGH"), "low": row.get("LOW"), "close": row.get("CLOSE"), "volume": row.get("TOTTRDQTY")})
    return [r for r in rows if all(r[k] not in (None, "") for k in FIELDS)]
