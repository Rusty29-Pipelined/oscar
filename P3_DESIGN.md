# OSCAR P-3 — Paper Trading

P-3 runs the same signals without sending orders. Every candidate is copied into a persistent paper ledger, then manually or automatically marked with an exit price and reason.

## Controls

- No broker credentials.
- No order endpoints.
- Duplicate signals are ignored by symbol, timeframe, setup family and signal date.
- Every close records return in R and notes.
- Paper results remain separate from historical backtests.

## Completion gate

Run for 30–60 trading sessions. Review signal count, target hit rates, average R, drawdown, missed data and manual overrides before any live decision.
