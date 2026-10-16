"""Zero-cost OSCAR deployment entrypoint for Streamlit Community Cloud."""
import io
import csv
import streamlit as st
from oscar.config import Config
from oscar.data import load_csv
from oscar.setups import detect

st.set_page_config(page_title="OSCAR · Research desk", page_icon="◈", layout="wide")
st.markdown("""<style>
.stApp{background:#0A0B0D;color:#F2F3F5}.block-container{max-width:1400px;padding-top:2rem}
[data-testid="stMetric"]{background:#131418;border:1px solid #23252B;border-radius:12px;padding:12px}
div.stButton>button{border:1px solid #2E3138;background:#1B1D22;color:#F2F3F5;border-radius:10px}
</style>""", unsafe_allow_html=True)
st.title("OSCAR")
st.caption("Personal research desk · zero-cost mode · no broker orders")
uploaded = st.file_uploader("Upload normalized OHLCV CSV", type=["csv"], help="Required columns: symbol,date/timeframe,open,high,low,close,volume")
if uploaded is None:
    st.info("Upload a normalized data file to run a scan. Use the CLI data adapters to create one.")
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
