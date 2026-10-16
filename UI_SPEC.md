# OSCAR UI — P-3/P-4 first screen

The first interface is intentionally one workflow, not a full trading terminal.

## Screen 1: Stock Selection

Filters: setup family, timeframe, status, minimum score and search symbol.

Table columns: symbol, setup, timeframe, entry, stop, T-1, T-2, T-3, R:R, score and status.

## Screen 2: Candidate Detail

Show the selected chart with resistance, support, entry, stop and three targets. Beside it show setup reason codes and the trade plan. Include a `Watch` action that writes to the paper ledger; no order action exists in this version.

All visible values must come from the scan ledger. Sample/mock values must be clearly marked and never mixed with real data.
