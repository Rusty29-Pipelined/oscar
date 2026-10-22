import argparse
from .config import Config
from .data import load_csv
from .report import write_csv
from .setups import detect
from .backtest import run, summary, write_trades
from .sources import nse_bhavcopy, nse_equity_symbols, upstox_equity_instruments, upstox_candles, public_chart_candles, fallback_candles, jugaad_candles, write_rows
import csv
from datetime import date, timedelta
from collections import defaultdict
from .paper import open_from_scan, close_trade
from .alerts import write_alerts


def main(argv=None):
    parser = argparse.ArgumentParser(prog="oscar")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="scan normalized OHLCV CSV data")
    scan.add_argument("--input", required=True, help="CSV with symbol,date/timeframe,OHLCV columns")
    scan.add_argument("--output", default="reports/scan.csv")
    scan.add_argument("--config")
    backtest = sub.add_parser("backtest", help="backtest setup families on normalized OHLCV CSV data")
    backtest.add_argument("--input", required=True)
    backtest.add_argument("--output", default="reports/trades.csv")
    backtest.add_argument("--summary", default="reports/backtest-summary.csv")
    backtest.add_argument("--horizon", type=int, default=20)
    backtest.add_argument("--config")
    nse = sub.add_parser("fetch-nse", help="fetch one NSE Bhavcopy day")
    nse.add_argument("--date", required=True, help="YYYY-MM-DD")
    nse.add_argument("--output", required=True)
    universe = sub.add_parser("nse-universe", help="write the current NSE equity symbol universe")
    universe.add_argument("--output", required=True)
    up = sub.add_parser("fetch-upstox", help="fetch Upstox historical candles")
    up.add_argument("--instrument-key", required=True)
    up.add_argument("--interval", required=True, help="Upstox V3 interval")
    up.add_argument("--to", required=True, dest="to_date")
    up.add_argument("--from", dest="from_date")
    up.add_argument("--output", required=True)
    upu = sub.add_parser("fetch-upstox-universe", help="fetch NSE EQ candles through Upstox")
    upu.add_argument("--output", required=True)
    upu.add_argument("--interval", default="1day")
    upu.add_argument("--from", dest="from_date", required=True)
    upu.add_argument("--to", dest="to_date", default=str(date.today()))
    upu.add_argument("--limit", type=int, default=0, help="optional symbol limit for testing")
    public = sub.add_parser("fetch-public", help="fetch public chart candles as a fallback")
    public.add_argument("--symbol", required=True, help="Yahoo-style symbol, e.g. RELIANCE.NS")
    public.add_argument("--interval", default="1d")
    public.add_argument("--period1", type=int, default=0)
    public.add_argument("--period2", type=int)
    public.add_argument("--output", required=True)
    fallback = sub.add_parser("fetch-fallback", help="fetch keyless public candles with automatic provider fallback")
    fallback.add_argument("--symbol", required=True)
    fallback.add_argument("--interval", default="1d")
    fallback.add_argument("--period1", type=int, default=0)
    fallback.add_argument("--period2", type=int)
    fallback.add_argument("--output", required=True)
    jugaad = sub.add_parser("fetch-jugaad", help="fetch NSE daily history using optional jugaad-data")
    jugaad.add_argument("--symbol", required=True); jugaad.add_argument("--from", dest="start", required=True); jugaad.add_argument("--to", dest="end", required=True); jugaad.add_argument("--output", required=True)
    screen = sub.add_parser("screen-universe", help="filter a normalized CSV to liquid symbols before scanning")
    screen.add_argument("--input", required=True); screen.add_argument("--output", required=True); screen.add_argument("--min-bars", type=int, default=250); screen.add_argument("--min-avg-volume", type=float, default=0)
    paper = sub.add_parser("paper-open", help="add scan candidates to paper ledger")
    paper.add_argument("--scan", required=True)
    paper.add_argument("--ledger", default="reports/paper-trades.csv")
    close = sub.add_parser("paper-close", help="close one paper trade")
    close.add_argument("--ledger", default="reports/paper-trades.csv")
    close.add_argument("--id", required=True)
    close.add_argument("--exit-price", required=True, type=float)
    close.add_argument("--reason", required=True)
    close.add_argument("--notes", default="")
    alert = sub.add_parser("alerts", help="write human-review alerts")
    alert.add_argument("--scan", required=True)
    alert.add_argument("--output", default="reports/alerts.txt")
    args = parser.parse_args(argv)
    if args.command == "scan":
        cfg = Config.load(args.config)
        groups = load_csv(args.input)
        candidates = []
        for (symbol, timeframe), candles in groups.items():
            candidates.extend(detect(candles, cfg))
        candidates.sort(key=lambda c: (c.status != "triggered", -c.risk_reward_t1, c.symbol, c.timeframe))
        write_csv(candidates, args.output)
        print(f"Scanned {len(groups)} symbol/timeframe groups; wrote {len(candidates)} candidates to {args.output}")
        for c in candidates[:20]:
            print(f"{c.symbol:12} {c.timeframe:4} {c.setup_family:22} {c.status:9} entry={c.entry_price:.2f} stop={c.stop_loss:.2f} T1={c.target_1:.2f}")
        return 0
    if args.command == "backtest":
        cfg = Config.load(args.config)
        groups = load_csv(args.input)
        trades = run(groups, cfg, args.horizon)
        write_trades(trades, args.output)
        rows = summary(trades)
        if rows:
            with open(args.summary, "w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
        print(f"Backtested {len(trades)} trades; wrote {args.output} and {args.summary}")
        for row in rows:
            print(row)
        return 0
    if args.command == "fetch-nse":
        rows = nse_bhavcopy(args.date)
        write_rows(rows, args.output)
        print(f"Fetched {len(rows)} NSE EQ rows to {args.output}")
        return 0
    if args.command == "nse-universe":
        symbols = nse_equity_symbols()
        with open(args.output, "w", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(["symbol"])
            writer.writerows([[symbol] for symbol in symbols])
        print(f"Loaded {len(symbols)} NSE EQ symbols to {args.output}")
        return 0
    if args.command == "fetch-upstox":
        rows = upstox_candles(args.instrument_key, args.interval, args.to_date, args.from_date)
        write_rows(rows, args.output)
        print(f"Fetched {len(rows)} Upstox candles to {args.output}")
        return 0
    if args.command == "fetch-upstox-universe":
        instruments = upstox_equity_instruments()
        selected = sorted(instruments)
        if args.limit:
            selected = selected[:args.limit]
        total = 0; failed = 0
        for symbol in selected:
            try:
                rows = upstox_candles(instruments[symbol], args.interval, args.to_date, args.from_date)
                normalized = [dict(row, symbol=symbol) for row in rows]
                write_rows(normalized, args.output, "a" if total else "w")
                total += len(normalized)
            except Exception as exc:
                failed += 1
                print(f"WARN {symbol}: {exc}")
        print(f"Fetched {total} candles for {len(selected) - failed}/{len(selected)} symbols to {args.output}")
        return 0
    if args.command == "fetch-public":
        rows = public_chart_candles(args.symbol, args.interval, args.period1, args.period2)
        write_rows(rows, args.output)
        print(f"Fetched {len(rows)} public candles to {args.output}")
        return 0
    if args.command == "fetch-fallback":
        rows = fallback_candles(args.symbol, args.interval, args.period1, args.period2)
        write_rows(rows, args.output)
        print(f"Fetched {len(rows)} fallback candles to {args.output}")
        return 0
    if args.command == "fetch-jugaad":
        rows = jugaad_candles(args.symbol, args.start, args.end); write_rows(rows, args.output)
        print(f"Fetched {len(rows)} jugaad-data rows to {args.output}"); return 0
    if args.command == "screen-universe":
        with open(args.input, newline="") as src:
            reader = csv.DictReader(src); fields = reader.fieldnames or []; groups = defaultdict(list)
            for row in reader: groups[(row.get("symbol","").strip().upper(), row.get("timeframe","1d"))].append(row)
        keep = {(s,t) for (s,t), values in groups.items() if len(values) >= args.min_bars and (sum(float(v.get("volume") or 0) for v in values)/len(values)) >= args.min_avg_volume}
        with open(args.output, "w", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=fields); writer.writeheader()
            for key, values in groups.items():
                if key in keep: writer.writerows(values)
        print(f"Kept {len(keep)} symbol/timeframe groups in {args.output}"); return 0
    if args.command == "paper-open":
        count = open_from_scan(args.scan, args.ledger)
        print(f"Paper ledger contains {count} trades: {args.ledger}")
        return 0
    if args.command == "paper-close":
        close_trade(args.ledger, args.id, args.exit_price, args.reason, args.notes)
        print(f"Closed paper trade {args.id}")
        return 0
    if args.command == "alerts":
        count = write_alerts(args.scan, args.output)
        print(f"Wrote {count} human-review alerts to {args.output}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
