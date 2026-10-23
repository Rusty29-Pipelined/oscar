"""Zero-cost OSCAR deployment entrypoint for Streamlit Community Cloud."""
import io
import csv
from datetime import date, timedelta
import streamlit as st
from oscar.config import Config
from oscar.data import load_csv
from oscar.setups import detect
from oscar.sources import kite_equity_instruments, kite_candles, fallback_candles

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
