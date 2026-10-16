import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
from .models import Candle


def _num(value: str) -> float:
    return float(value.strip().replace(",", ""))


def load_csv(path: str) -> Dict[Tuple[str, str], List[Candle]]:
    """Load a normalized CSV with symbol,date,timeframe,OHLCV columns.

    `date` may be an ISO date or timestamp. `timeframe` defaults to 1d.
    """
    groups = defaultdict(list)
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"symbol", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV missing columns: " + ", ".join(sorted(missing)))
        for row in reader:
            symbol = row["symbol"].strip().upper()
            timestamp = (row.get("timestamp") or row.get("date") or "").strip()
            timeframe = (row.get("timeframe") or "1d").strip().lower()
            if not symbol or not timestamp:
                continue
            candle = Candle(symbol, timestamp, timeframe, _num(row["open"]), _num(row["high"]), _num(row["low"]), _num(row["close"]), _num(row["volume"]))
            values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
            if not all(math.isfinite(v) for v in values) or min(values) < 0:
                raise ValueError(f"Invalid numeric OHLCV row for {symbol} at {timestamp}")
            if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
                raise ValueError(f"Inconsistent OHLC row for {symbol} at {timestamp}")
            groups[(symbol, timeframe)].append(candle)
    for candles in groups.values():
        candles.sort(key=lambda c: c.timestamp)
    return dict(groups)
