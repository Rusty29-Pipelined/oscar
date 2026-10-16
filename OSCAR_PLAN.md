# OSCAR — Source-of-Truth Plan

## Objective

OSCAR is a general swing-trade discovery, research and learning system. It will discover repeatable combinations of price, volume, trend, volatility, relative strength and market context across NSE stocks, explain each signal, backtest setup families, learn from outcomes and feedback, paper-trade them, and only then support human-approved live execution.

Sahasra is one reference example used to seed and validate the system. It is not the permanent strategy or product boundary.

## Confirmed P-1 requirements

- Universe: all NSE equities, subject to a documented liquidity/data-quality exclusion list.
- Timeframes: 1-hour, 4-hour, daily and weekly.
- Data layers: NSE public/Bhavcopy data, Upstox market data, and importable CSV files. The system will use source priority and record the source used for every candle.
- Output: a spreadsheet/CSV ledger containing entry, stop-loss, T-1, T-2, T-3, outcome and backtest statistics.
- Setup scope: multiple setup families. The first family is breakout/pre-breakout, but P-1 interfaces must also support continuation, pullback/retest, volatility contraction, support bounce and other discovered families.

OSCAR is not an automatic trading product in the first version.

## Initial strategy scope

Keep the first experiment limited and price/volume focused. These rules define the initial reference setup; they must not be treated as the only setup OSCAR can discover:

1. Price above 50-DMA and 200-DMA.
2. 50-DMA above 200-DMA.
3. A clear 3–12 week consolidation/base.
4. Price within approximately 0–5% of meaningful resistance.
5. Volume contracts or stabilises during the base.
6. Breakout volume is at least 1.5–2.0x recent average.
7. RSI is approximately 50–68; avoid overextended readings.
8. Closing price breaks the defined resistance.
9. Reject a chase when price is more than 8–10% above the trigger.
10. Stop below the base/structural support; target the next resistance with minimum 2:1 reward/risk.

Optional quality gates, tested separately rather than blindly added:

- Nifty/market regime.
- Relative strength versus Nifty and sector.
- Breakout hold/retest confirmation.

Future setup families may include continuation, pullback/retest, volatility contraction, support bounce, unusual-volume and 52-week-high setups. They will share the same feature, outcome and backtest infrastructure.

## Product boundary

### Build now

- End-of-day NSE scanner.
- Exact, versioned setup definitions and feature calculations.
- Candidate ranking and explanation.
- Historical backtest and trade ledger.
- Paper-trade tracking.
- Outcome dataset and human feedback labels.
- Local dashboard or CSV report.
- Email/push notification adapter.

### Defer

- Automatic order placement.
- Mobile application.
- Multi-user accounts.
- Subscription billing.
- Strategy marketplace.
- Cloud scaling.

The code must remain modular so these can be added later without rewriting strategy logic.

## Technical direction

- Python.
- Upstox read-only market data as the preferred source.
- NSE Bhavcopy/`jugaad-data` as fallback and research source.
- SQLite plus Parquet for local storage.
- pandas or Polars for calculations.
- VectorBT for broad batch research.
- A small OSCAR trade simulator for stops, targets, slippage and commissions.
- Streamlit only after the command-line/report flow works.

Existing projects may be used as references or adapters, especially PKScreener, Screeni-py, `jugaad-data`, VectorBT and Backtesting.py. OSCAR's strategy definition and trade ledger remain proprietary to this project.

## Delivery phases

### Phase 1 — General multi-timeframe feature and signal MVP

Create a reproducible scan for all NSE equities across 1-hour, 4-hour, daily and weekly data. Produce candidates across multiple initial setup families with entry, stop-loss, T-1, T-2, T-3, risk/reward, feature values and reason codes. Store the feature snapshot so later models can learn from outcomes.

### Phase 2 — Setup-family backtesting

Run the reference setup and additional controlled setup families across multiple years and stocks. Include slippage, brokerage, next-bar execution and no-look-ahead checks.

### Phase 3 — Paper trading and validation

Run signals live without real capital for 30–60 sessions. Record every signal, rejection, entry, exit, missed trade and data failure.

### Phase 4 — Human-approved live alerts

Add reliable notifications and a manual trade-confirmation workflow. Keep broker order placement disabled by default.

### Phase 5 — Productisation decision

Only after evidence supports the strategy: hosted dashboard, user accounts, broker integrations, permissions, monitoring and commercial product design.

## P-1 design

### P-1 goal

Answer two questions reproducibly: “Which NSE stocks today show a defined, repeatable setup?” and “What measurable features and price levels explain the candidate?” The initial pre-breakout setup is Sahasra-derived, but the interfaces must support additional setup families.

### P-1 inputs

- NSE equity universe, initially liquid stocks only.
- Daily OHLCV history, minimum 250 sessions per stock.
- Optional Nifty 50 and sector benchmark data.
- Versioned configuration file containing all thresholds.

### P-1 processing

1. Download/update daily candles with caching.
2. Normalise symbols, dates, corporate-action fields and missing values.
3. Calculate 50-DMA, 200-DMA, RSI(14), average volume, range and relative strength.
4. Detect a recent consolidation and derive support/resistance.
5. Classify each stock as `watch`, `triggered`, `extended` or `invalid`.
6. Calculate entry zone, stop, target, risk/reward and reason codes.
7. Rank candidates by setup quality; do not predict a price.
8. Save the full scan and configuration version for later audit.

### P-1 output

Each candidate must contain:

```text
symbol
as_of_date
status
last_close
resistance
breakout_trigger
entry_zone
support_or_stop
target_1
target_2
risk_reward
volume_ratio
rsi
base_length
trend_state
relative_strength (if available)
reason_codes
data_timestamp
strategy_version
```

### P-1 acceptance criteria

- Same input data and configuration produce the same output.
- No future candle is used in a signal.
- Every candidate explains which rules passed or failed.
- The scanner can process the initial universe locally without paid hosting.
- A scan can be exported to CSV and opened without the dashboard.
- Failed downloads are logged and do not silently become trading signals.

### P-1 deliberately excludes

- Machine learning.
- News sentiment.
- Options data.
- Intraday execution.
- Automatic orders.
- Large indicator collections.

## Budget and time target

P-1 target: 5–8 working days for a usable local version, assuming credentials and data access are available.

Expected cash cost: ₹0–₹3,000. Do not add a VPS, managed database or paid broker API until the local scan and data quality are proven.

## Decision rule after P-1

Do not expand the product because one stock worked. Proceed to Phase 2 only when the scan is reproducible, auditable and produces enough historical candidates to test properly.
