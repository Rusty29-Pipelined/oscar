"""Zero-cost OSCAR deployment entrypoint for Streamlit Community Cloud."""
import io
import csv
from datetime import date, timedelta
import streamlit as st
from oscar.config import Config
from oscar.data import load_csv
from oscar.setups import detect
from oscar.sources import kite_equity_instruments, kite_candles, fallback_candles
from oscar.backtest import run as run_backtest, summary as summarize_backtest

st.set_page_config(page_title="OSCAR · Research desk", page_icon="◈", layout="wide")
st.markdown("""<style>
.stApp{background:#0A0B0D;color:#F2F3F5}.block-container{max-width:1400px;padding-top:2rem}
[data-testid="stMetric"]{background:#131418;border:1px solid #23252B;border-radius:12px;padding:12px}
div.stButton>button{border:1px solid #2E3138;background:#1B1D22;color:#F2F3F5;border-radius:10px}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=3600, show_spinner=False)
def load_kite_instruments():
    return kite_equity_instruments()

st.title("OSCAR")
st.caption("Personal research desk · zero-cost mode · no broker orders")
with st.expander("Run automatic NSE scan", expanded=True):
    st.caption("Uses Kite Connect for NSE market data. No orders are placed.")
    left, right = st.columns(2)
    interval = left.selectbox("Timeframe", ["1day", "1hour", "4hour", "1week"], index=0)
    lookback = right.slider("Lookback (days)", 30, 730, 365)
    limit = st.number_input("Symbols (0 = all NSE equities)", min_value=0, max_value=2500, value=50, step=50)
    run_scan = st.button("Run NSE scan", type="primary")
    st.divider()
    st.caption("Historical backtest · daily candles · 20-session exit horizon · no orders")
    backtest_symbols = st.text_input(
        "10 NSE symbols",
        value="RELIANCE,TCS,HDFCBANK,ICICIBANK,INFY,SBIN,LT,ITC,BHARTIARTL,AXISBANK",
        help="Use exactly 10 comma-separated NSE trading symbols. Edit this liquid-stock basket if you prefer another 10.",
    )
    backtest_days = st.slider("Backtest history (calendar days)", 730, 1825, 1095, step=365)
    run_historical_backtest = st.button("Run 10-stock historical backtest")
    if run_scan:
        try:
            import os
            provider = "kite"
            if not (os.environ.get("KITE_API_KEY") and os.environ.get("KITE_ACCESS_TOKEN")):
                raise RuntimeError("Configure KITE_API_KEY and KITE_ACCESS_TOKEN before running a scan")
            st.info("Loading the NSE equity universe…")
            instruments = load_kite_instruments()
            if not instruments:
                raise RuntimeError("Kite returned an empty NSE equity universe")
            selected = sorted(instruments)
            if limit:
                selected = selected[:int(limit)]
            start = date.today() - timedelta(days=int(lookback))
            end = date.today()
            rows = []
            failures = []
            progress = st.progress(0, text=f"Fetching 0/{len(selected)} symbols")
            for index, symbol in enumerate(selected, 1):
                try:
                    candles = kite_candles(instruments[symbol], interval, str(end), str(start), symbol)
                    rows.extend(dict(row, symbol=symbol) for row in candles)
                except Exception as exc:
                    failures.append(f"{symbol}: {exc}")
                    # Keyless daily/weekly fallback keeps research scans usable
                    # when the primary Kite request is temporarily unavailable.
                    if interval == "1day":
                        try:
                            period1 = int((date.today() - timedelta(days=int(lookback))).strftime("%s"))
                            candles = fallback_candles(symbol + ".NS", "1d", period1)
                            rows.extend(dict(row, symbol=symbol, timeframe="1day") for row in candles)
                        except Exception as fallback_exc:
                            failures.append(f"{symbol} fallback: {fallback_exc}")
                finally:
                    # Always advance the progress bar, including failed/fallback requests.
                    progress.progress(index / len(selected), text=f"Fetching {index}/{len(selected)} symbols")
            progress.empty()
            if not rows:
                detail = " | ".join(failures[:3])
                raise RuntimeError(f"Kite returned no candles for the selected universe" + (f" ({detail})" if detail else ""))
            st.session_state["oscar_rows"] = rows
            st.success(f"Fetched {len(rows):,} candles for {len(selected)} symbols. Review the ranked results below.")
        except Exception as exc:
            st.error(f"Automatic scan failed: {exc}")

    if run_historical_backtest:
        try:
            import os
            if not (os.environ.get("KITE_API_KEY") and os.environ.get("KITE_ACCESS_TOKEN")):
                raise RuntimeError("Configure KITE_API_KEY and KITE_ACCESS_TOKEN before running a backtest")
            symbols = [part.strip().upper() for part in backtest_symbols.split(",") if part.strip()]
            if len(symbols) != 10 or len(set(symbols)) != 10:
                raise ValueError("Enter exactly 10 distinct comma-separated NSE symbols")
            st.info("Loading Kite’s NSE instrument list…")
            instruments = load_kite_instruments()
            missing = [symbol for symbol in symbols if symbol not in instruments]
            if missing:
                raise ValueError("Not found in Kite NSE equities: " + ", ".join(missing))

            cfg = Config(source="Kite Connect · historical daily", strategy_version="p1-baseline")
            start = date.today() - timedelta(days=int(backtest_days))
            end = date.today()
            grouped = {}
            failed = []
            progress = st.progress(0, text=f"Fetching 0/10 stocks · {start} to {end}")
            for index, symbol in enumerate(symbols, 1):
                try:
                    candles = kite_candles(instruments[symbol], "1day", str(end), str(start), symbol)
                    candles = [dict(row, symbol=symbol, timeframe="1d") for row in candles]
                    if len(candles) < cfg.min_history_sessions + cfg.backtest_horizon_bars + 1:
                        raise RuntimeError(f"only {len(candles)} daily candles; need at least {cfg.min_history_sessions + cfg.backtest_horizon_bars + 1}")
                    with __import__("tempfile").NamedTemporaryFile(mode="w", suffix=".csv", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=["symbol", "date", "timeframe", "open", "high", "low", "close", "volume"])
                        writer.writeheader(); writer.writerows(candles); handle.flush()
                        grouped.update(load_csv(handle.name))
                except Exception as exc:
                    failed.append(f"{symbol}: {exc}")
                finally:
                    progress.progress(index / 10, text=f"Fetched {index}/10 stocks")
            progress.empty()
            if failed:
                raise RuntimeError("Backtest needs usable Kite history for all 10 selected stocks. " + " | ".join(failed))
            trades = run_backtest(grouped, cfg, horizon=cfg.backtest_horizon_bars)
            st.session_state["oscar_backtest"] = {
                "trades": trades,
                "summary": summarize_backtest(trades),
                "symbols": symbols,
                "start": str(start),
                "end": str(end),
                "history": {symbol: len(grouped[(symbol, "1d")]) for symbol in symbols},
                "horizon": cfg.backtest_horizon_bars,
            }
            st.success(f"Backtest complete: {len(symbols)} stocks, {sum(st.session_state['oscar_backtest']['history'].values()):,} daily candles, {len(trades)} completed trades.")
        except Exception as exc:
            st.error(f"Historical backtest failed: {exc}")

if "oscar_backtest" in st.session_state:
    result = st.session_state["oscar_backtest"]
    st.subheader("Historical backtest results")
    st.caption(f"Kite Connect daily candles · {result['start']} to {result['end']} · {result['horizon']}-session horizon · {', '.join(result['symbols'])}")
    trades = result["trades"]
    if not trades:
        st.warning("The history loaded for all 10 stocks, but the current setup rules produced no completed triggered trades. There is no meaningful win rate to report for this run.")
    else:
        winners = sum(float(trade["return_r"]) > 0 for trade in trades)
        target_wins = sum(trade["target_hit"] != "none" for trade in trades)
        stops = sum(trade["exit_reason"] == "stop_loss" for trade in trades)
        avg_r = sum(float(trade["return_r"]) for trade in trades) / len(trades)
        gross_profit = sum(float(t["return_r"]) for t in trades if float(t["return_r"]) > 0)
        gross_loss = abs(sum(float(t["return_r"]) for t in trades if float(t["return_r"]) < 0))
        equity = peak = max_drawdown = 0.0
        for trade in trades:
            equity += float(trade["return_r"])
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        a, b, c, d, e = st.columns(5)
        a.metric("Completed trades", len(trades))
        b.metric("Profitable trades", f"{winners / len(trades) * 100:.1f}%", f"{winners}/{len(trades)}")
        c.metric("Target hit rate", f"{target_wins / len(trades) * 100:.1f}%", f"{target_wins}/{len(trades)}")
        d.metric("Average return", f"{avg_r:.2f} R")
        e.metric("Profit factor", f"{gross_profit / gross_loss:.2f}" if gross_loss else ("∞" if gross_profit else "—"))
        st.caption(f"Stop-loss exits: {stops} · Max drawdown: {max_drawdown:.2f} R · Friction included: 0.03% commission + 0.05% slippage each side.")
        st.dataframe(trades, use_container_width=True, hide_index=True)
        out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=list(trades[0]))
        writer.writeheader(); writer.writerows(trades)
        st.download_button("Download backtest trade ledger", out.getvalue(), "oscar-10-stock-backtest.csv", "text/csv")

uploaded = st.file_uploader("Or upload normalized OHLCV CSV", type=["csv"], help="Required columns: symbol,date/timeframe,open,high,low,close,volume")
if "oscar_rows" in st.session_state and uploaded is None:
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=["symbol", "date", "timeframe", "open", "high", "low", "close", "volume"])
    writer.writeheader(); writer.writerows(st.session_state["oscar_rows"])
    uploaded = io.BytesIO(output.getvalue().encode())
if uploaded is None:
    st.info("Run the automatic Kite scan above, or upload a normalized data file.")
    st.stop()
raw = uploaded.getvalue()
try:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv") as handle:
        handle.write(raw); handle.flush()
        groups = load_csv(handle.name)
except Exception as exc:
    st.error(f"Could not read this data file: {exc}")
    st.stop()
cfg = Config()
candidates = []
for (symbol, timeframe), candles in groups.items():
    candidates.extend(detect(candles, cfg))
candidates.sort(key=lambda c: (c.status != "triggered", -c.risk_reward_t1, c.symbol))
rows = [c.row() for c in candidates]
triggered = sum(c.status == "triggered" for c in candidates)
avg_rr = sum(c.risk_reward_t1 for c in candidates) / len(candidates) if candidates else 0
a, b, c, d = st.columns(4)
a.metric("Candidates", len(candidates)); b.metric("Triggered", triggered)
c.metric("Average R:R", f"{avg_rr:.1f}"); d.metric("Symbols", len(groups))
st.subheader("Ranked candidates")
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    st.download_button("Export scan CSV", output.getvalue(), "oscar-scan.csv", "text/csv")
else:
    st.warning("No candidates matched the configured setup rules.")
