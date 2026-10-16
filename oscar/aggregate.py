from collections import defaultdict
from datetime import datetime
from typing import Iterable, List


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def aggregate(rows: Iterable[dict], target: str) -> List[dict]:
    """Aggregate normalized candles into 4h or 1w candles."""
    buckets = defaultdict(list)
    for row in rows:
        stamp = _dt(row["date"])
        if target == "4h":
            key = (row["symbol"], stamp.date().isoformat(), stamp.hour // 4)
        elif target == "1w":
            iso = stamp.isocalendar()
            key = (row["symbol"], f"{iso.year}-W{iso.week:02d}")
        else:
            raise ValueError("target must be 4h or 1w")
        buckets[key].append(row)
    output = []
    for key, values in sorted(buckets.items(), key=lambda item: item[0]):
        values.sort(key=lambda r: r["date"])
        output.append({"symbol": values[0]["symbol"], "date": values[-1]["date"], "timeframe": target, "open": values[0]["open"], "high": max(float(v["high"]) for v in values), "low": min(float(v["low"]) for v in values), "close": values[-1]["close"], "volume": sum(float(v["volume"]) for v in values)})
    return output
