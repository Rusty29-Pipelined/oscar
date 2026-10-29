"""OSCAR: breakout-retest scanner and backtest on Kite Connect daily data. No orders are placed."""
import io
import csv
import os
from datetime import date, datetime, timedelta, timezone
import streamlit as st
from oscar.models import Candle
from oscar import retest
from oscar.sources import kite_equity_instruments, kite_candles, kite_login_url, kite_exchange_request_token

st.set_page_config(page_title="OSCAR · Research desk", page_icon="◈", layout="wide")
st.markdown("""<style>
.stApp{background:#0A0B0D;color:#F2F3F5}.block-container{max-width:1400px;padding-top:2rem}
[data-testid="stMetric"]{background:#131418;border:1px solid #23252B;border-radius:12px;padding:12px}
div.stButton>button{border:1px solid #2E3138;background:#1B1D22;color:#F2F3F5;border-radius:10px}
</style>""", unsafe_allow_html=True)

IST = timezone(timedelta(hours=5, minutes=30))
NIFTY_50_TOKEN = 256265  # Kite instrument token for the NIFTY 50 index
NIFTY_50 = ("ADANIENT,ADANIPORTS,APOLLOHOSP,ASIANPAINT,AXISBANK,BAJAJ-AUTO,BAJFINANCE,BAJAJFINSV,BEL,BHARTIARTL,"
            "CIPLA,COALINDIA,DRREDDY,EICHERMOT,GRASIM,HCLTECH,HDFCBANK,HDFCLIFE,HINDALCO,HINDUNILVR,"
            "ICICIBANK,INDIGO,INFY,ITC,JSWSTEEL,KOTAKBANK,LT,M&M,MARUTI,MAXHEALTH,"
            "NESTLEIND,NTPC,ONGC,POWERGRID,RELIANCE,SBILIFE,SHRIRAMFIN,SBIN,SUNPHARMA,TCS,"
            "TATACONSUM,TATASTEEL,TECHM,TITAN,TRENT,ULTRACEMCO,WIPRO,BRITANNIA,HEROMOTOCO,DIVISLAB")


@st.cache_data(ttl=3600, show_spinner=False)
def load_kite_instruments():
    return kite_equity_instruments()


@st.cache_resource
def kite_session():
    """Process-wide Kite login state; the token lives only in server memory."""
    return {}


def kite_expiry(login_at):
    """Kite access tokens expire at 06:00 IST the morning after login."""
    expiry = login_at.replace(hour=6, minute=0, second=0, microsecond=0)
    return expiry if login_at < expiry else expiry + timedelta(days=1)


def candles(token, symbol, days):
    end = date.today()
    rows = kite_candles(token, "1day", str(end), str(end - timedelta(days=days)), symbol)
    return [Candle(symbol, str(r["date"]), "1d", float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"])) for r in rows]


def fetch_all(symbols, instruments, days, label, handle):
    """Fetch and process one symbol at a time so candles are not all held in memory.
    Any provider failure stops the run (no partial results)."""
    failures = []
    bar = st.progress(0, text=f"{label}: 0/{len(symbols)}")
    for i, symbol in enumerate(symbols, 1):
        try:
            series = candles(instruments[symbol], symbol, days)
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")
        else:
            handle(symbol, series)
        bar.progress(i / len(symbols), text=f"{label}: {i}/{len(symbols)}")
    bar.empty()
    retry = [] if any("HTTP Error 403" in f for f in failures) else [f.split(": ", 1)[0] for f in failures]
    if retry:  # second pass for symbols that still failed after the per-request retries
        failures = []
    for symbol in retry:
        try:
            series = candles(instruments[symbol], symbol, days)
        except Exception as exc:
            failures.append(f"{symbol}: {exc}")
        else:
            handle(symbol, series)
    if failures:
        hint = " Kite session looks expired: click Login with Kite." if any("403" in f for f in failures) else ""
        raise RuntimeError(f"{len(failures)} of {len(symbols)} symbols failed, so no results are shown.{hint} " + " | ".join(failures[:5]))


def csv_bytes(rows):
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue()


def require_kite():
    if not (os.environ.get("KITE_API_KEY") and os.environ.get("KITE_ACCESS_TOKEN")):
        raise RuntimeError("Kite is not connected: click Login with Kite first")


session = kite_session()
request_token = st.query_params.get("request_token")
if request_token:
    try:
        data = kite_exchange_request_token(request_token)
        os.environ["KITE_ACCESS_TOKEN"] = data["access_token"]
        session.update(user_id=data.get("user_id", ""), login_at=datetime.now(IST))
        st.query_params.clear()
        st.rerun()
    except Exception as exc:
        st.query_params.clear()
        st.error(str(exc))

st.title("OSCAR")
st.caption("Breakout-retest swing scanner · NSE daily · research only, no orders")
login_col, status_col = st.columns([1, 4])
login_col.link_button("Login with Kite", kite_login_url())
if session.get("login_at") and datetime.now(IST) < kite_expiry(session["login_at"]):
    status_col.success(f"Kite connected · {session['user_id']} · valid until {kite_expiry(session['login_at']):%d %b, %H:%M} IST")
elif session.get("login_at"):
    status_col.warning("Kite session expired at 06:00 IST. Click Login with Kite.")
else:
    status_col.info("Not logged in. Click Login with Kite (the login resets when the server restarts or sleeps).")

scan_tab, backtest_tab = st.tabs(["Scan", "Backtest"])

with scan_tab:
    limit = st.number_input("Stocks to scan (0 = all NSE stocks, ~15 min)", min_value=0, max_value=3000, value=0, step=100)
    if st.button("Run scan", type="primary"):
        try:
            require_kite()
            instruments = load_kite_instruments()
            symbols = sorted(instruments)[:int(limit)] if limit else sorted(instruments)
            nifty = candles(NIFTY_50_TOKEN, "NIFTY 50", 500)
            regime = retest.market_regime(nifty)
            rows, ready, skipped = [], [], []

            def check(symbol, series):
                problem = retest.data_problem(series[-300:])
                if problem:
                    skipped.append(f"{symbol}: {problem}")
                elif len(series) >= 251:
                    hit = retest.scan(symbol, series, regime)
                    if hit:
                        rows.append(hit)
                    else:
                        near = retest.ready(symbol, series)
                        if near:
                            ready.append(near)
            fetch_all(symbols, instruments, 500, "Scanning", check)
            st.session_state["scan"] = {"rows": rows, "ready": sorted(ready, key=lambda r: r["pct_away"]), "skipped": skipped, "market_ok": regime.get(retest.day(nifty[-1]), False),
                                        "as_of": retest.day(nifty[-1]), "count": len(symbols)}
        except Exception as exc:
            st.session_state.pop("scan", None)
            st.error(f"Scan failed: {exc}")

    result = st.session_state.get("scan")
    if result:
        st.caption(f"Data as of {result['as_of']} · {result['count']} stocks scanned")
        buys = [r for r in result["rows"] if r["action"].startswith("BUY")]
        watch = [r for r in result["rows"] if r["action"] == "WATCH"]
        cols = ["symbol", "entry", "stop_loss", "stop_pct", "target_1", "target_2", "target_3", "t1_pct", "breakout_date"]
        st.subheader(f"Buy at next open · {len(buys)}")
        if buys:
            st.dataframe([{k: r[k] for k in cols} for r in buys], use_container_width=True, hide_index=True)
            st.caption("Entry shown at today's close. Stop is the base low, max 10%. Targets are the next chart resistance levels (prior swing highs, else measured moves). Sell a third at each target, move the stop to entry after T-1, close the rest after 40 sessions.")
        else:
            st.write("None today.")
        st.subheader(f"Watchlist (broke out, waiting for retest) · {len(watch)}")
        if watch:
            st.dataframe([{"symbol": r["symbol"], "buy_zone": r["buy_zone"], "stop_loss": r["stop_loss"], "target_1": r["target_1"], "target_2": r["target_2"], "target_3": r["target_3"], "last_close": r["last_close"], "breakout_date": r["breakout_date"]} for r in watch],
                         use_container_width=True, hide_index=True)
        else:
            st.write("None today.")
        near = result.get("ready", [])
        st.subheader(f"Ready to break out (within 5% of the 60-day high) · {len(near)}")
        if near:
            st.dataframe([{k: r[k] for k in ("symbol", "last_close", "buy_above", "pct_away", "stop_loss", "stop_pct", "target_1", "target_2", "target_3")} for r in near],
                         use_container_width=True, hide_index=True)
            st.caption("Heads-up list, not a buy signal. A stock moves to the Watchlist when it closes above buy_above on 1.5x volume, then to Buy on the retest.")
        else:
            st.write("None today.")
        if result["rows"]:
            st.download_button("Download scan CSV", csv_bytes(result["rows"]), "oscar-scan.csv", "text/csv")
        if result["skipped"]:
            with st.expander(f"Skipped for data problems · {len(result['skipped'])}"):
                st.write("\n".join(result["skipped"]))

with backtest_tab:
    bt_symbols = st.text_area("Stocks (comma-separated)", value=NIFTY_50, height=90)
    bt_years = st.slider("Years of history", 3, 7, 7)
    if st.button("Run backtest", type="primary"):
        try:
            require_kite()
            symbols = [s.strip().upper() for s in bt_symbols.split(",") if s.strip()]
            instruments = load_kite_instruments()
            missing = [s for s in symbols if s not in instruments]
            if missing:
                raise ValueError("Not found in Kite NSE equities: " + ", ".join(missing))
            days = int(bt_years * 365.25)
            regime = retest.market_regime(candles(NIFTY_50_TOKEN, "NIFTY 50", days))
            trades, skipped = [], []

            def test(symbol, series):
                problem = retest.data_problem(series)
                if problem:
                    skipped.append(f"{symbol}: {problem}")
                else:
                    trades.extend(retest.backtest(symbol, series, regime))
            fetch_all(symbols, instruments, days, "Backtesting", test)
            st.session_state["backtest"] = {"trades": trades, "summary": retest.summarize(trades), "skipped": skipped,
                                            "count": len(symbols) - len(skipped), "years": bt_years}
        except Exception as exc:
            st.session_state.pop("backtest", None)
            st.error(f"Backtest failed: {exc}")

    result = st.session_state.get("backtest")
    if result:
        s = result["summary"]
        if not s:
            st.warning("No trades for these stocks and period.")
        else:
            st.caption(f"{result['count']} stocks · last {result['years']} years · costs 0.2% per side included")
            a, b, c, d = st.columns(4)
            a.metric("Win rate", f"{s['win_rate']}%", f"{s['trades']} trades", delta_color="off")
            b.metric("Average per trade", f"{s['avg_return']:+.2f}%")
            c.metric("Profit factor", s["profit_factor"] if s["profit_factor"] is not None else "n/a")
            d.metric("Worst trade", f"{s['worst']:.1f}%", f"max losing streak {s['max_losing_streak']}", delta_color="off")
            st.caption(f"Average win {s['avg_win']:+.2f}% · average loss {s['avg_loss']:.2f}% · targets hit: T-1 {s['t1_hit_pct']}%, T-2 {s['t2_hit_pct']}%, T-3 {s['t3_hit_pct']}% · average {s['avg_days']} days per trade")
            st.download_button("Download trade ledger", csv_bytes(result["trades"]), "oscar-backtest.csv", "text/csv")
        if result["skipped"]:
            with st.expander(f"Skipped for data problems · {len(result['skipped'])}"):
                st.write("\n".join(result["skipped"]))
