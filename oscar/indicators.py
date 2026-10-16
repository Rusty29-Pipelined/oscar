from typing import List, Optional
from .models import Candle


def sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = sum(max(x, 0.0) for x in recent) / period
    losses = sum(max(-x, 0.0) for x in recent) / period
    if losses == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def avg_volume(candles: List[Candle], period: int = 20) -> Optional[float]:
    if len(candles) < period:
        return None
    return sum(c.volume for c in candles[-period:]) / period
