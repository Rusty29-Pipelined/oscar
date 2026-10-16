from dataclasses import dataclass
from pathlib import Path
import json
from typing import Optional


@dataclass
class Config:
    min_history_sessions: int = 250
    base_min_bars: int = 15
    base_max_bars: int = 60
    lookback_resistance: int = 60
    near_resistance_pct: float = 5.0
    breakout_volume_multiple: float = 1.5
    max_chase_pct: float = 10.0
    rsi_min: float = 50.0
    rsi_max: float = 68.0
    minimum_reward_risk: float = 2.0
    stop_buffer_pct: float = 0.5
    source: str = "csv"
    strategy_version: str = "p1-baseline"
    commission_pct: float = 0.03
    slippage_pct: float = 0.05
    backtest_horizon_bars: int = 20

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        if not path:
            return cls()
        values = json.loads(Path(path).read_text())
        allowed = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in values.items() if k in allowed})
