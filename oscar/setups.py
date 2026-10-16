from typing import List, Tuple
from .config import Config
from .indicators import avg_volume, rsi, sma
from .models import Candidate, Candle


def _levels(candles: List[Candle], cfg: Config):
    window = candles[-cfg.lookback_resistance:]
    resistance = max(c.high for c in window[:-1])
    base = candles[-min(cfg.base_max_bars, len(candles)):-1]
    support = min(c.low for c in base)
    entry = resistance * 1.002
    stop = support * (1.0 - cfg.stop_buffer_pct / 100.0)
    risk = entry - stop
    t1 = entry + risk * 2.0
    t2 = entry + risk * 3.0
    t3 = entry + risk * 4.0
    return resistance, support, entry, stop, t1, t2, t3


def detect(candles: List[Candle], cfg: Config) -> List[Candidate]:
    """Return multiple setup-family candidates from one symbol/timeframe.

    This deliberately uses transparent baseline detectors. Later detectors can be
    added without changing the output contract or ledger.
    """
    if len(candles) < cfg.min_history_sessions:
        return []
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    last = candles[-1]
    ma50, ma200, rsi14 = sma(closes, 50), sma(closes, 200), rsi(closes)
    v20 = avg_volume(candles[:-1], 20)
    if None in (ma50, ma200, rsi14, v20):
        return []
    resistance, support, entry, stop, t1, t2, t3 = _levels(candles, cfg)
    distance = (resistance - last.close) / resistance * 100.0
    volume_ratio = last.volume / v20 if v20 else 0.0
    trend = "uptrend" if last.close > ma50 > ma200 else "not_aligned"
    base = candles[-cfg.base_max_bars:-1]
    base_range = (max(c.high for c in base) - min(c.low for c in base)) / max(last.close, 0.01) * 100.0
    near = -cfg.max_chase_pct <= distance <= cfg.near_resistance_pct
    trend_ok = trend == "uptrend"
    reasons = []
    if trend_ok: reasons.append("trend_aligned")
    if near: reasons.append("near_resistance")
    if volume_ratio >= cfg.breakout_volume_multiple: reasons.append("volume_expansion")
    if cfg.rsi_min <= rsi14 <= cfg.rsi_max: reasons.append("rsi_range")
    result = []

    def add(family: str, status: str, extra: str):
        risk = entry - stop
        if risk <= 0 or risk / entry > 0.25:
            return
        rr = (t1 - entry) / risk
        if rr < cfg.minimum_reward_risk:
            return
        result.append(Candidate(last.symbol, family, last.timeframe, last.timestamp, status, round(entry, 4), round(stop, 4), round(t1, 4), round(t2, 4), round(t3, 4), round(rr, 2), round(last.close, 4), round(resistance, 4), len(base), round(volume_ratio, 2), round(rsi14, 2), trend, ";".join(reasons + [extra]), cfg.source, cfg.strategy_version))

    # Reference breakout family; not the system boundary.
    if trend_ok and near:
        status = "triggered" if last.close > resistance and volume_ratio >= cfg.breakout_volume_multiple else "watch"
        if last.close > entry * (1 + cfg.max_chase_pct / 100): status = "extended"
        add("breakout", status, "base_present")

    # Transparent continuation candidate for future comparison.
    if trend_ok and last.close > resistance and volume_ratio < cfg.breakout_volume_multiple:
        add("continuation", "watch", "trend_continuation")

    # Pullback/retest: price near 50-DMA while long-term trend remains aligned.
    if trend_ok and abs(last.close - ma50) / ma50 * 100 <= 3.0 and last.close >= support:
        add("pullback_retest", "watch", "near_50dma_support")

    # Volatility contraction proxy: a tight recent base relative to price.
    if trend_ok and base_range <= 12.0 and near:
        add("volatility_contraction", "watch", "tight_base")
    return result
