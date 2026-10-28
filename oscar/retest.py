"""Breakout-retest strategy (v3), validated in the 2019-2026 sandbox.

Rules, all on daily candles:
  Breakout day: close > 50-DMA > 200-DMA, close above the prior 59-session high (R)
  on >= 1.5x the prior 20-session average volume, and no more than ~10% above R.
  Market filter: Nifty above its 200-DMA and Nifty 50-DMA rising over 10 sessions.
  Liquidity: price >= Rs 50, 50-session average traded value >= Rs 10 Cr, no zero-volume days.
  Entry: first close within 10 sessions that retests R (low <= R+2%, close >= R-2%); buy next open.
  Stop: 0.5% under the 59-session low before the breakout.
  Exits: half at T-1 (2R) and stop to breakeven; rest at T-3 (4R), a close below the
  20-DMA after T-1, or after 60 sessions.
"""
from typing import Dict, List, Optional, Tuple

COST_PER_SIDE = 0.002  # ~0.15% charges + 0.05% slippage
LOOKBACK, VOL_MULT, MAX_CHASE, TOL, WINDOW, MAX_HOLD = 59, 1.5, 1.102, 0.02, 10, 60
MIN_PRICE, MIN_TRADED_VALUE = 50.0, 1e8
SPLIT_GAP = 0.35  # an overnight move this large is treated as an unadjusted corporate action


def _sma(values: List[float], period: int) -> List[Optional[float]]:
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        out.append(total / period if i >= period - 1 else None)
    return out


def day(candle) -> str:
    return str(candle.timestamp)[:10]


def market_regime(nifty: List) -> Dict[str, bool]:
    """date -> True when Nifty > 200-DMA and its 50-DMA is above where it was 10 sessions ago."""
    closes = [c.close for c in nifty]
    s50, s200 = _sma(closes, 50), _sma(closes, 200)
    ok = {}
    for i, c in enumerate(nifty):
        ok[day(c)] = bool(i >= 10 and s200[i] and s50[i] and s50[i - 10] and closes[i] > s200[i] and s50[i] > s50[i - 10])
    return ok


def data_problem(candles: List) -> Optional[str]:
    for prev, cur in zip(candles, candles[1:]):
        if prev.close > 0 and abs(cur.open / prev.close - 1) > SPLIT_GAP:
            return f"{day(cur)} gap of {(cur.open / prev.close - 1) * 100:.0f}% (likely split/bonus not adjusted)"
    return None


class _Series:
    def __init__(self, candles: List, regime: Dict[str, bool]):
        self.c = candles
        self.o = [x.open for x in candles]; self.h = [x.high for x in candles]
        self.l = [x.low for x in candles]; self.cl = [x.close for x in candles]; self.v = [x.volume for x in candles]
        self.s20, self.s50, self.s200 = _sma(self.cl, 20), _sma(self.cl, 50), _sma(self.cl, 200)
        self.atv50 = _sma([a * b for a, b in zip(self.cl, self.v)], 50)
        self.regime = regime

    def breakout(self, b: int) -> Optional[Tuple[float, float]]:
        """(R, stop) if bar b is a qualifying breakout day."""
        if b < 250:
            return None
        cl, v = self.cl[b], self.v[b]
        R = max(self.h[b - LOOKBACK:b])
        avg_v = sum(self.v[b - 20:b]) / 20
        if not (self.s200[b] and cl > self.s50[b] > self.s200[b] and cl > R and avg_v > 0
                and v >= VOL_MULT * avg_v and cl <= R * MAX_CHASE):
            return None
        if not self.regime.get(day(self.c[b]), False):
            return None
        if cl < MIN_PRICE or (self.atv50[b] or 0) < MIN_TRADED_VALUE or min(self.v[b - 49:b + 1]) <= 0:
            return None
        return R, min(self.l[b - LOOKBACK:b]) * 0.995

    def retest(self, k: int, R: float) -> bool:
        return self.l[k] <= R * (1 + TOL) and self.cl[k] >= R * (1 - TOL)


def levels(entry: float, stop: float) -> Dict[str, float]:
    r = entry - stop
    return {"entry": round(entry, 2), "stop_loss": round(stop, 2), "stop_pct": round(r / entry * 100, 1),
            "target_1": round(entry + 2 * r, 2), "target_2": round(entry + 3 * r, 2), "target_3": round(entry + 4 * r, 2)}


def scan(symbol: str, candles: List, regime: Dict[str, bool]) -> Optional[Dict[str, object]]:
    """Today's action for one stock: BUY (retest happened today) or WATCH (broke out, awaiting retest)."""
    s = _Series(candles, regime)
    last = len(candles) - 1
    for b in range(last, max(last - WINDOW, 250) - 1, -1):
        hit = s.breakout(b)
        if not hit:
            continue
        R, stop = hit
        retests = [k for k in range(b + 1, last + 1) if s.retest(k, R)]
        if retests and retests[0] < last:
            return None  # already triggered earlier; entry has passed
        base = {"symbol": symbol, "breakout_date": day(candles[b]), "breakout_level": round(R, 2), "last_close": round(s.cl[last], 2)}
        if retests:
            return dict(base, action="BUY at next open", **levels(s.cl[last], stop))
        if s.cl[last] <= stop:
            return None
        return dict(base, action="WATCH", buy_zone=f"{R * (1 - TOL):.2f} - {R * (1 + TOL):.2f}", **levels(R, stop))
    return None


def backtest(symbol: str, candles: List, regime: Dict[str, bool]) -> List[Dict[str, object]]:
    s = _Series(candles, regime)
    n, trades, b = len(candles), [], 250
    while b < n - 2:
        hit = s.breakout(b)
        k = next((k for k in range(b + 1, min(b + 1 + WINDOW, n - 1)) if hit and s.retest(k, hit[0])), None)
        if not hit or k is None:
            b += 1
            continue
        e, stop = s.o[k + 1], hit[1]
        if e <= stop:
            b += 1
            continue
        trade = _exit(s, k + 1, e, stop)
        b = trade.pop("_exit_index") + 1
        trades.append(dict(symbol=symbol, signal_date=day(candles[k]), **levels(e, stop), **trade))
    return trades


def _exit(s: _Series, start: int, e: float, stop: float) -> Dict[str, object]:
    r = e - stop
    t1, t3 = e + 2 * r, e + 4 * r
    legs, half, why = [], False, "time limit"
    end = min(start + MAX_HOLD, len(s.c) - 1)
    j = start
    for j in range(start, end + 1):
        if s.l[j] <= stop:
            legs.append((0.5 if half else 1.0, min(s.o[j], stop) if j > start else stop))
            why = "breakeven stop" if half else "stop loss"
            break
        if not half and s.h[j] >= t1:
            legs.append((0.5, t1)); half = True; stop = e
        if half and s.h[j] >= t3:
            legs.append((0.5, t3)); why = "T-3"; break
        if half and s.s20[j] and s.cl[j] < s.s20[j]:
            legs.append((0.5, s.cl[j])); why = "trail (close < 20-DMA)"; break
    else:
        legs.append((0.5 if half else 1.0, s.cl[end])); j = end
    net = sum(w * (px * (1 - COST_PER_SIDE) - e * (1 + COST_PER_SIDE)) for w, px in legs)
    return {"exit_date": day(s.c[j]), "exit_reason": why, "hit_target_1": half,
            "return_pct": round(net / e * 100, 2), "return_r": round(net / r, 2), "days_held": j - start + 1, "_exit_index": j}


def summarize(trades: List[Dict[str, object]]) -> Dict[str, object]:
    if not trades:
        return {}
    rets = [t["return_pct"] for t in trades]
    wins, losses = [x for x in rets if x > 0], [x for x in rets if x <= 0]
    streak = run = 0
    for t in sorted(trades, key=lambda t: t["exit_date"]):
        run = run + 1 if t["return_pct"] <= 0 else 0
        streak = max(streak, run)
    return {"trades": len(rets), "win_rate": round(len(wins) / len(rets) * 100, 1), "avg_return": round(sum(rets) / len(rets), 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0, "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) else None,
            "worst": round(min(rets), 2), "best": round(max(rets), 2), "max_losing_streak": streak}
