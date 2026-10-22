"""Data-source adapters for P-1.

Adapters emit the normalized CSV contract used by the scanner. Network access
is intentionally opt-in; no credentials are stored in the repository.
"""
import csv
import io
import json
import os
import urllib.parse
import urllib.request
import zipfile
import gzip
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List, Dict, Optional


FIELDS = ["symbol", "date", "timeframe", "open", "high", "low", "close", "volume"]


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
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def write_rows(rows: Iterable[dict], path: str, mode: str = "w") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    exists = target.exists() and target.stat().st_size > 0 and mode == "a"
    with target.open(mode, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def upstox_candles(instrument_key: str, interval: str, to_date: str, from_date: Optional[str] = None) -> List[dict]:
    """Fetch Upstox V3 historical candles using UPSTOX_ACCESS_TOKEN.

    Upstox's response is newest-first and its API interval names vary by
    endpoint; callers pass values accepted by the current V3 API.
    """
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("UPSTOX_ACCESS_TOKEN is not set")
    encoded = urllib.parse.quote(instrument_key, safe="")
    interval_map = {
        "1day": ("days", "1"), "day": ("days", "1"),
        "1hour": ("hours", "1"), "4hour": ("hours", "4"),
        "1week": ("weeks", "1"), "1wk": ("weeks", "1"), "week": ("weeks", "1"),
    }
    unit, width = interval_map.get(interval, ("minutes", str(interval).removesuffix("minute")))
    path = f"/v3/historical-candle/{encoded}/{unit}/{width}/{to_date}"
    if from_date:
        path += f"/{from_date}"
    payload = json.loads(_request("https://api.upstox.com" + path, {"Accept": "application/json", "Authorization": f"Bearer {token}"}))
    candles = payload.get("data", {}).get("candles", [])
    rows = []
    for candle in reversed(candles):
        timestamp, op, hi, lo, close, volume = candle[:6]
        rows.append({"symbol": instrument_key, "date": timestamp, "timeframe": interval, "open": op, "high": hi, "low": lo, "close": close, "volume": volume})
    return rows


def upstox_equity_instruments() -> Dict[str, str]:
    """Return NSE cash-equity trading symbol -> Upstox instrument key."""
    raw = _request("https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz")
    payload = json.loads(gzip.decompress(raw).decode("utf-8"))
    result = {}
    for item in payload:
        if item.get("segment") != "NSE_EQ" or item.get("instrument_type") not in ("EQ", ""):
            continue
        symbol = (item.get("trading_symbol") or "").strip().upper()
        key = item.get("instrument_key")
        if symbol and key:
            result[symbol] = key
    return result


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
