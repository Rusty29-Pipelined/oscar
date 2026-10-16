from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class Candle:
    symbol: str
    timestamp: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Candidate:
    symbol: str
    setup_family: str
    timeframe: str
    signal_date: str
    status: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    risk_reward_t1: float
    last_close: float
    resistance: float
    base_length: int
    volume_ratio: float
    rsi: float
    trend_state: str
    reason_codes: str
    data_source: str
    strategy_version: str = "p1-baseline"

    def row(self) -> Dict[str, object]:
        return asdict(self)
