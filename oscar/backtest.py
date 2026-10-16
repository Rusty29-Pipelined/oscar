import csv
from pathlib import Path
from typing import Dict, List
from .config import Config
from .models import Candle, Candidate
from .setups import detect


TRADE_FIELDS = [
    "symbol", "setup_family", "timeframe", "signal_date", "entry_price",
    "stop_loss", "target_1", "target_2", "target_3", "exit_date",
    "exit_price", "exit_reason", "target_hit", "return_r", "bars_held",
    "data_source", "strategy_version",
]


def _evaluate(candidate: Candidate, future: List[Candle], commission_pct: float = 0.0, slippage_pct: float = 0.0) -> Dict[str, object]:
    """Conservative OHLC evaluation: if stop and target occur in one bar, stop wins."""
    levels = [("stop", candidate.stop_loss), ("T-1", candidate.target_1), ("T-2", candidate.target_2), ("T-3", candidate.target_3)]
    t1_hit = t2_hit = t3_hit = False
    exit_date = future[-1].timestamp if future else candidate.signal_date
    exit_price = future[-1].close if future else candidate.entry_price
    reason = "open"
    held = len(future)
    for i, bar in enumerate(future, 1):
        if bar.low <= candidate.stop_loss:
            exit_date, exit_price, reason, held = bar.timestamp, candidate.stop_loss, "stop_loss", i
            break
        # A single-bar move can pass several targets.  Record the furthest
        # target reached and exit there; the stop check above remains first so
        # an ambiguous OHLC bar is always handled conservatively.
        if bar.high >= candidate.target_3:
            t3_hit = True
            exit_date, exit_price, reason, held = bar.timestamp, candidate.target_3, "T-3", i
            break
        if bar.high >= candidate.target_2:
            t2_hit = True
            exit_date, exit_price, reason, held = bar.timestamp, candidate.target_2, "T-2", i
            break
        if bar.high >= candidate.target_1:
            t1_hit = True
            exit_date, exit_price, reason, held = bar.timestamp, candidate.target_1, "T-1", i
            break
    # Apply adverse slippage to both entry and exit, and round-trip commission.
    effective_entry = candidate.entry_price * (1.0 + slippage_pct / 100.0)
    effective_exit = exit_price * (1.0 - slippage_pct / 100.0)
    gross = effective_exit - effective_entry
    costs = (effective_entry + effective_exit) * commission_pct / 100.0
    net = gross - costs
    risk = effective_entry - candidate.stop_loss
    return {
        "symbol": candidate.symbol, "setup_family": candidate.setup_family,
        "timeframe": candidate.timeframe, "signal_date": candidate.signal_date,
        "entry_price": candidate.entry_price, "stop_loss": candidate.stop_loss,
        "target_1": candidate.target_1, "target_2": candidate.target_2,
        "target_3": candidate.target_3, "exit_date": exit_date,
        "exit_price": round(exit_price, 4), "exit_reason": reason,
        "target_hit": reason if reason in {"T-1", "T-2", "T-3"} else "none",
        "return_r": round(net / risk, 3) if risk else 0,
        "bars_held": held, "data_source": candidate.data_source,
        "strategy_version": candidate.strategy_version,
    }


def run(groups: Dict, cfg: Config, horizon: int = 20) -> List[Dict[str, object]]:
    trades = []
    for (_, _), candles in groups.items():
        next_available = {}
        for index in range(cfg.min_history_sessions, len(candles) - 1):
            prefix = candles[:index + 1]
            candidates = detect(prefix, cfg)
            for candidate in candidates:
                # Backtests enter only on confirmed signals. Watch candidates are
                # useful in the scan report but have no objective entry event.
                if candidate.status != "triggered":
                    continue
                key = candidate.setup_family
                if index < next_available.get(key, 0):
                    continue
                future = candles[index + 1:index + 1 + horizon]
                trades.append(_evaluate(candidate, future, cfg.commission_pct, cfg.slippage_pct))
                next_available[key] = index + horizon
    return trades


def write_trades(trades: List[Dict[str, object]], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
        writer.writeheader()
        writer.writerows(trades)


def summary(trades: List[Dict[str, object]]) -> List[Dict[str, object]]:
    groups = {}
    for trade in trades:
        key = (trade["setup_family"], trade["timeframe"])
        groups.setdefault(key, []).append(trade)
    output = []
    for (family, timeframe), rows in sorted(groups.items()):
        wins = [r for r in rows if r["target_hit"] != "none"]
        returns = [float(r["return_r"]) for r in rows]
        equity = peak = drawdown = 0.0
        for value in returns:
            equity += value
            peak = max(peak, equity)
            drawdown = min(drawdown, equity - peak)
        gross_profit = sum(v for v in returns if v > 0)
        gross_loss = abs(sum(v for v in returns if v < 0))
        output.append({
            "setup_family": family, "timeframe": timeframe,
            "trades": len(rows), "target_wins": len(wins),
            "win_pct": round(len(wins) / len(rows) * 100, 2),
            "avg_return_r": round(sum(float(r["return_r"]) for r in rows) / len(rows), 3),
            "stops": sum(r["exit_reason"] == "stop_loss" for r in rows),
            "t1_win_pct": round(sum(r["target_hit"] == "T-1" for r in rows) / len(rows) * 100, 2),
            "t2_win_pct": round(sum(r["target_hit"] == "T-2" for r in rows) / len(rows) * 100, 2),
            "t3_win_pct": round(sum(r["target_hit"] == "T-3" for r in rows) / len(rows) * 100, 2),
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
            "max_drawdown_r": round(drawdown, 3),
        })
    return output
