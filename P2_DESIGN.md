# OSCAR P-2 — Historical Backtesting

P-2 uses the exact P-1 detectors and level calculations. It must never contain a second implementation of the signal rules.

## P-2 objectives

- Test every setup family across all available symbols and timeframes.
- Use only information available at the signal candle.
- Enter on the next candle, not retroactively at the best price.
- Apply configurable slippage and commission.
- Prevent overlapping duplicate trades for the same setup family/symbol/timeframe.
- Report T-1, T-2 and T-3 hit percentages separately.
- Report expectancy, average R, profit factor, losing streak and maximum drawdown in R.

## P-2 outputs

- `reports/trades.csv`: one auditable row per trade.
- `reports/backtest-summary.csv`: grouped by setup family and timeframe.
- Strategy version and source data are stored on every row.

## P-2 controls

- Minimum history: 250 bars.
- Default holding horizon: 20 bars.
- Same-bar stop/target collision: stop wins conservatively.
- No watch-state entries; watch candidates remain informational until confirmed.
- No parameter optimization until an untouched out-of-sample period is reserved.

## P-2 completion gate

P-2 is not accepted based on win rate alone. A setup must have enough trades, positive net expectancy after costs, bounded drawdown, and stable results across separate time periods and market regimes before moving to paper trading.
