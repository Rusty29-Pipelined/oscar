# OSCAR P-1

Local, source-agnostic, multi-timeframe swing setup discovery. P-1 accepts normalized OHLCV CSV data and produces a ranked candidate ledger. Sahasra-derived breakout logic is only one setup family.

## CSV input

Required columns:

```text
symbol,date,timeframe,open,high,low,close,volume
```

`timeframe` values are `1h`, `4h`, `1d` or `1w`. A `timestamp` column may be used instead of `date`.

## Run

```bash
PYTHONPATH=. python3 -m oscar.cli scan --input data/ohlcv.csv --output reports/scan.csv
```

The output contains entry, stop-loss, T-1, T-2 and T-3 for each candidate, together with setup family, timeframe, status, features, reason codes and strategy version.

## Backtest

```bash
PYTHONPATH=. python3 -m oscar.cli backtest \
  --input data/ohlcv.csv \
  --output reports/trades.csv \
  --summary reports/backtest-summary.csv
```

The trade ledger records target/stop outcomes and the summary reports trade count, target win percentage, stop count and average return in R by setup family and timeframe.

P-2 also reports T-1/T-2/T-3 hit percentages, profit factor and maximum drawdown in R. Costs are controlled by `commission_pct` and `slippage_pct` in the configuration.

## Data adapters

NSE daily EQ data:

```bash
PYTHONPATH=. python3 -m oscar.cli fetch-nse --date 2026-09-25 --output data/nse.csv
```

Upstox historical candles (keep the token in the environment):

```bash
export UPSTOX_ACCESS_TOKEN="..."
PYTHONPATH=. python3 -m oscar.cli fetch-upstox \
  --instrument-key 'NSE_EQ|INE848E01016' \
  --interval hours/1 --from 2025-01-01 --to 2026-09-25 \
  --output data/upstox.csv
```

The exact Upstox interval/path available to an account should be confirmed against its current V3 documentation. Source failures are explicit; they never become trading signals.

## Public fallback

Upstox is optional. For research and initial stock selection, OSCAR can use public chart candles where the interval history is available:

```bash
PYTHONPATH=. python3 -m oscar.cli fetch-public \
  --symbol RELIANCE.NS --interval 1d --output data/reliance-public.csv
```

Public data must be cross-checked against NSE before real-money use. Daily/weekly selection can proceed with NSE/public data; intraday history is subject to the public provider's retention limits.

Automatic keyless fallback (Yahoo first, Stooq for daily data) is available through `fetch-fallback`. It keeps research scans usable when one public endpoint is unavailable. Example: `PYTHONPATH=. python3 -m oscar.cli fetch-fallback --symbol RELIANCE.NS --interval 1d --output data/reliance-fallback.csv`.

## P-3 and P-4

Create a paper ledger from a scan:

```bash
PYTHONPATH=. python3 -m oscar.cli paper-open --scan reports/scan.csv
```

Create human-review alerts without placing orders:

```bash
PYTHONPATH=. python3 -m oscar.cli alerts --scan reports/scan.csv
```

## Important limitation

The P-1 core does not download data or place orders. Data adapters for NSE and Upstox plug into the normalized CSV contract next. Backtesting consumes the same signal/level contract so scanner and backtester do not silently diverge.
