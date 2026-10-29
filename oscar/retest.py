"""Breakout-retest swing strategy on daily candles.

  Breakout day: close above a rising 200-DMA (200-DMA higher than 21 sessions ago), close above the prior 59-session high (R)
  on >= 1.5x the prior 20-session average volume, and no more than ~10% above R.
  Trend is checked on the stock itself. No index filter.
  Liquidity: price >= Rs 50, 50-session average traded value >= Rs 10 Cr, no zero-volume days.
  Entry: first close within 10 sessions that retests R (low <= R+2%, close >= R-2%); buy next open.
  Stop: 0.5% under the 59-session base low before the breakout, never more than 10% below entry.
  Targets (chart-based): the next prior swing highs above entry; when there is no overhead
  resistance, measured moves of the base height (0.5x, 1x, 1.618x) above R. Each target is
  at least 1x risk away.
  Exits: one third at each target, stop to entry after T-1, rest closed after 40 sessions.
"""
from typing import Dict, List, Optional, Tuple

COST_PER_SIDE = 0.002  # ~0.15% charges + 0.05% slippage
LOOKBACK, VOL_MULT, MAX_CHASE, TOL, WINDOW, MAX_HOLD = 59, 1.5, 1.102, 0.02, 10, 40
MAX_STOP = 0.10
NEAR_HIGH = 0.05  # ready list: close within 5% of the 60-session high
SWING_SPAN, RESISTANCE_YEARS = 5, 500  # swing high = highest of +/-5 sessions, looked for over ~2 years
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
        self.s50, self.s200 = _sma(self.cl, 50), _sma(self.cl, 200)
        self.atv50 = _sma([a * b for a, b in zip(self.cl, self.v)], 50)
        self.regime = regime

    def breakout(self, b: int) -> Optional[float]:
        """R (the breakout level) if bar b is a qualifying breakout day."""
        if b < 250:
            return None
        cl, v = self.cl[b], self.v[b]
        R = max(self.h[b - LOOKBACK:b])
        avg_v = sum(self.v[b - 20:b]) / 20
        if not (self.s200[b] and self.s200[b - 21] and cl > self.s200[b] > self.s200[b - 21] and cl > R and avg_v > 0
                and v >= VOL_MULT * avg_v and cl <= R * MAX_CHASE):
            return None
        if cl < MIN_PRICE or (self.atv50[b] or 0) < MIN_TRADED_VALUE or min(self.v[b - 49:b + 1]) <= 0:
            return None
        return R

    def retest(self, k: int, R: float) -> bool:
        return self.l[k] <= R * (1 + TOL) and self.cl[k] >= R * (1 - TOL)

    def stop(self, b: int, k: int, entry: float) -> float:
        return max(min(self.l[b - LOOKBACK:b]) * 0.995, entry * (1 - MAX_STOP))

    def targets(self, b: int, R: float, entry: float, stop: float) -> List[float]:
        """Next three chart levels above entry: prior swing highs, then measured moves."""
        risk = entry - stop
        floor = entry + risk
        swings = [self.h[j] for j in range(max(SWING_SPAN, b - RESISTANCE_YEARS), b - SWING_SPAN)
                  if self.h[j] == max(self.h[j - SWING_SPAN:j + SWING_SPAN + 1]) and self.h[j] >= floor]
        height = R - min(self.l[b - LOOKBACK:b])
        moves = [R + m * height for m in (0.5, 1.0, 1.618)]
        levels = []
        for x in sorted(swings) + sorted(m for m in moves if m >= floor):
            if not levels or x > levels[-1] * 1.02:
                levels.append(x)
            if len(levels) == 3:
                break
        while len(levels) < 3:  # always three targets: extend by 1x risk past the last level
            levels.append((levels[-1] if levels else entry) + risk)
        return levels


def levels(entry: float, stop: float, targets: List[float]) -> Dict[str, float]:
    return {"entry": round(entry, 2), "stop_loss": round(stop, 2), "stop_pct": round((entry - stop) / entry * 100, 1),
            "target_1": round(targets[0], 2), "target_2": round(targets[1], 2), "target_3": round(targets[2], 2),
            "t1_pct": round((targets[0] / entry - 1) * 100, 1)}


def scan(symbol: str, candles: List, regime: Dict[str, bool]) -> Optional[Dict[str, object]]:
    """Today's action for one stock: BUY (retest happened today) or WATCH (broke out, awaiting retest)."""
    s = _Series(candles, regime)
    last = len(candles) - 1
    for b in range(last, max(last - WINDOW, 250) - 1, -1):
        R = s.breakout(b)
        if not R:
            continue
        retests = [k for k in range(b + 1, last + 1) if s.retest(k, R)]
        if retests and retests[0] < last:
            return None  # already triggered earlier; entry has passed
        base = {"symbol": symbol, "breakout_date": day(candles[b]), "breakout_level": round(R, 2), "last_close": round(s.cl[last], 2)}
        if retests:
            entry = s.cl[last]
            stop = s.stop(b, last, entry)
            return dict(base, action="BUY at next open", **levels(entry, stop, s.targets(b, R, entry, stop)))
        stop = s.stop(b, last, R)
        if s.cl[last] <= stop:
            return None
        return dict(base, action="WATCH", buy_zone=f"{R * (1 - TOL):.2f} - {R * (1 + TOL):.2f}", **levels(R, stop, s.targets(b, R, R, stop)))
    return None


def ready(symbol: str, candles: List) -> Optional[Dict[str, object]]:
    """Heads-up list: healthy, liquid stock within NEAR_HIGH of its 60-session high, not yet broken out."""
    s = _Series(candles, {})
    i = len(candles) - 1
    if i < 250 or not (s.s200[i] and s.s200[i - 21] and s.cl[i] > s.s200[i] > s.s200[i - 21]):
        return None
    if s.cl[i] < MIN_PRICE or (s.atv50[i] or 0) < MIN_TRADED_VALUE or min(s.v[i - 49:i + 1]) <= 0:
        return None
    level = max(s.h[i - LOOKBACK:i + 1])
    if s.cl[i] < level * (1 - NEAR_HIGH):
        return None
    entry = level * 1.002
    stop = max(min(s.l[i - LOOKBACK:i + 1]) * 0.995, entry * (1 - MAX_STOP))
    return dict(symbol=symbol, last_close=round(s.cl[i], 2), buy_above=round(entry, 2),
                pct_away=round((entry / s.cl[i] - 1) * 100, 1),
                **{k: v for k, v in levels(entry, stop, s.targets(i + 1, level, entry, stop)).items() if k != "entry"})


def backtest(symbol: str, candles: List, regime: Dict[str, bool]) -> List[Dict[str, object]]:
    s = _Series(candles, regime)
    n, trades, b = len(candles), [], 250
    while b < n - 2:
        R = s.breakout(b)
        k = next((k for k in range(b + 1, min(b + 1 + WINDOW, n - 1)) if R and s.retest(k, R)), None)
        if not R or k is None:
            b += 1
            continue
        e = s.o[k + 1]
        stop = s.stop(b, k, e)
        if e <= stop:
            b += 1
            continue
        tg = s.targets(b, R, e, stop)
        trade = _exit(s, k + 1, e, stop, tg)
        b = trade.pop("_exit_index") + 1
        trades.append(dict(symbol=symbol, signal_date=day(candles[k]), **levels(e, stop, tg), **trade))
    return trades


def _exit(s: _Series, start: int, e: float, stop: float, tg: List[float]) -> Dict[str, object]:
    """Sell a third at each target; after T-1 the stop moves to entry; close the rest after MAX_HOLD."""
    legs, hit, why = [], 0, "time limit"
    end = min(start + MAX_HOLD, len(s.c) - 1)
    j = start
    for j in range(start, end + 1):
        if s.l[j] <= stop:
            legs.append(((3 - hit) / 3, min(s.o[j], stop) if j > start else stop))
            why = "stop loss" if hit == 0 else f"breakeven after T-{hit}"
            break
        while hit < 3 and s.h[j] >= tg[hit]:
            legs.append((1 / 3, tg[hit])); hit += 1
            stop = max(stop, e)
        if hit == 3:
            why = "T-3"
            break
    else:
        legs.append(((3 - hit) / 3, s.cl[end])); j = end
    net = sum(w * (px * (1 - COST_PER_SIDE) - e * (1 + COST_PER_SIDE)) for w, px in legs)
    return {"exit_date": day(s.c[j]), "exit_reason": why, "targets_hit": hit,
            "return_pct": round(net / e * 100, 2), "days_held": j - start + 1, "_exit_index": j}


def summarize(trades: List[Dict[str, object]]) -> Dict[str, object]:
    if not trades:
        return {}
    rets = [t["return_pct"] for t in trades]
    wins, losses = [x for x in rets if x > 0], [x for x in rets if x <= 0]
    streak = run = 0
    for t in sorted(trades, key=lambda t: t["exit_date"]):
        run = run + 1 if t["return_pct"] <= 0 else 0
        streak = max(streak, run)
    hits = [t.get("targets_hit", 0) for t in trades]
    return {"trades": len(rets), "win_rate": round(len(wins) / len(rets) * 100, 1), "avg_return": round(sum(rets) / len(rets), 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0, "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) else None,
            "worst": round(min(rets), 2), "best": round(max(rets), 2), "max_losing_streak": streak,
            "t1_hit_pct": round(sum(h >= 1 for h in hits) / len(hits) * 100, 1),
            "t2_hit_pct": round(sum(h >= 2 for h in hits) / len(hits) * 100, 1),
            "t3_hit_pct": round(sum(h >= 3 for h in hits) / len(hits) * 100, 1),
            "avg_days": round(sum(t.get("days_held", 0) for t in trades) / len(trades), 1)}
