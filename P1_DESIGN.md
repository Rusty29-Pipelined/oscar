# OSCAR P-1 Implementation Design

P-1 is a general multi-timeframe setup-discovery foundation. Sahasra-derived breakout logic is one setup plugin, not the system identity.

## Runtime flow

```text
all NSE equities
    ↓
data adapters (NSE/Bhavcopy + Upstox + CSV import)
    ↓
cache/normaliser
    ↓
indicator calculator
    ↓
setup-family detectors
    ↓
price-level and risk calculator
    ↓
feature snapshot + ranker
    ↓
CSV report + SQLite scan ledger
```

## Proposed repository layout

```text
oscar/
  config/default.toml
  data/universe.csv
  src/oscar/
    cli.py
    config.py
    models.py
    data_sources.py
    normalise.py
    indicators.py
    setup_detector.py
    levels.py
    setup_families.py
    features.py
    ranker.py
    ledger.py
    report.py
  tests/
    test_indicators.py
    test_setup_detector.py
    test_levels.py
  reports/
  cache/
```

## Configuration principles

All thresholds belong in configuration, never scattered through code. The first configuration should contain only:

```toml
strategy_version = "p1-baseline"
min_history_sessions = 250
base_min_weeks = 3
base_max_weeks = 12
near_resistance_pct = 5.0
breakout_volume_multiple = 1.5
max_chase_pct = 10.0
rsi_min = 50
rsi_max = 68
minimum_reward_risk = 2.0
timeframes = ["1h", "4h", "1d", "1w"]
targets = ["T1", "T2", "T3"]
```

## Setup state machine

```text
INVALID       → trend/base/quality condition failed
WATCH         → base exists and price is near resistance
TRIGGERED     → close exceeded resistance with required volume
EXTENDED      → trigger occurred but price is beyond chase limit
FAILED        → post-breakout close returned below invalidation level
```

The state and transition date are stored, allowing later paper-trade and backtest comparisons.

Each detector must return a common setup record containing `setup_family`, `timeframe`, `features`, `state`, `levels`, `reason_codes` and `strategy_version`. This allows OSCAR to compare breakout, continuation, pullback and other setup families using one ledger.

## Resistance and support method

P-1 should use a transparent method rather than subjective chart drawing:

- Resistance: highest close/high in a configurable recent lookback, clustered within a small tolerance.
- Support: lowest low/close of the detected base.
- Breakout trigger: resistance plus a small configurable buffer.
- Entry zone: trigger through the chase limit.
- Stop: support, with a documented buffer.
- Targets: T-1, T-2 and T-3. T-1 is the nearest logical resistance, T-2 the next meaningful resistance and T-3 an extended objective. If levels are unavailable or the minimum risk/reward is not plausible, reject the candidate.

The method can be improved later, but every level must be reproducible from OHLCV.

## Ranking

Ranking is a quality score, not a probability claim. Suggested components:

- trend alignment: 25%
- base quality and tightness: 25%
- volume behaviour: 20%
- distance to trigger: 15%
- reward/risk: 15%

Market regime and relative strength should initially be reported as features and tested as separate variants, not silently mixed into the baseline score. Later, the outcome ledger can train a transparent probability/ranking model.

## Output ledger contract

Every row must include:

```text
symbol, setup_family, timeframe, signal_date, entry_price,
stop_loss, target_1, target_2, target_3, risk_reward,
status, exit_price, exit_date, exit_reason, return_r,
target_hit, stop_hit, data_source, strategy_version
```

The same ledger will be used for paper trading and historical backtesting, so winning percentage can be calculated consistently for T-1, T-2 and T-3.

## Daily command contract

```text
oscar scan --date YYYY-MM-DD --config config/default.toml
```

The command must:

1. Update or read cached data.
2. Run the scan.
3. Write `reports/scan-YYYY-MM-DD.csv`.
4. Write scan metadata and errors to SQLite.
5. Print a short ranked table.

## P-1 test fixtures

Use synthetic candles to prove:

- a valid base becomes `WATCH`;
- a close above resistance plus volume becomes `TRIGGERED`;
- an overextended price becomes `EXTENDED`;
- a support failure becomes `FAILED`;
- insufficient history is rejected;
- missing data never creates a candidate;
- calculated levels do not use future rows.

## Handoff to P-2

P-2 consumes only the saved feature/signal ledger and the same setup definitions. It must not re-implement signal rules inside the backtester. This prevents the scanner and backtest from disagreeing silently and creates the dataset required for OSCAR's learning layer.
