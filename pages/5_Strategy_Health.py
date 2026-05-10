"""Strategy Health — track encoded-strategy performance over time from
weekly backtest runs.

Every entry in `backtest_runs` is one (symbol, interval, mode) snapshot of
the strategy against the last N days of fresh data. Watching this trend
tells you whether the strategy is degrading or holding up as markets shift.
"""
from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent

try:
    for k, v in st.secrets.items():
        if isinstance(v, (str, int, float)):
            os.environ.setdefault(k, str(v))
except Exception:
    pass

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(ROOT / ".env", override=False)

st.set_page_config(page_title="Strategy Health", layout="wide")
st.title("Strategy Health")
st.caption(
    "Weekly backtest runs against fresh BingX data. Tracks whether the "
    "encoded strategy is degrading or holding up as markets evolve."
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not (SUPABASE_URL and SUPABASE_KEY):
    st.warning("Supabase isn't configured.")
    st.stop()

try:
    from supabase import create_client
except ImportError:
    st.error("supabase-py not installed.")
    st.stop()


@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@st.cache_data(ttl=60)
def fetch_runs() -> pd.DataFrame:
    client = get_client()
    rows = (client.table("backtest_runs").select("*")
            .order("run_at", desc=True).limit(500).execute().data) or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["run_at"] = pd.to_datetime(df["run_at"])
    for col in ("win_rate_pct", "return_pct", "max_drawdown_pct", "n_trades", "n_signals"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


df = fetch_runs()

if df.empty:
    st.info(
        "No backtest runs yet. The weekly cron on your VPS writes a row each "
        "Monday at 03:00 UTC. To trigger an immediate run for testing, ssh "
        "into the VPS and:\n\n"
        "```bash\ncd /opt/smc-bot-toolkit\n.venv/bin/python -m scripts.run_backtest\n```"
    )
    st.stop()

# --- Filters ---
fcol1, fcol2, fcol3 = st.columns(3)
symbols_avail = sorted(df["symbol"].dropna().unique())
intervals_avail = sorted(df["interval"].dropna().unique())
modes_avail = ["strict", "no-bias", "no-pd", "loose"]
sel_symbols = fcol1.multiselect("Symbol", symbols_avail, default=symbols_avail)
sel_interval = fcol2.selectbox("Interval", intervals_avail, index=0)
sel_modes = fcol3.multiselect("Mode", modes_avail, default=["no-bias"])

mask = (df["symbol"].isin(sel_symbols) & (df["interval"] == sel_interval) &
        df["mode"].isin(sel_modes))
filt = df[mask].copy()
if filt.empty:
    st.info("No runs match the filters.")
    st.stop()

# --- Latest snapshot KPIs (most recent run per symbol+mode) ---
latest = (filt.sort_values("run_at", ascending=False)
          .groupby(["symbol", "mode"]).head(1).reset_index(drop=True))

st.subheader("Latest snapshot")
st.dataframe(
    latest[["run_at", "symbol", "mode", "n_trades", "win_rate_pct",
            "return_pct", "max_drawdown_pct", "git_sha"]]
        .round({"win_rate_pct": 1, "return_pct": 2, "max_drawdown_pct": 2}),
    use_container_width=True, hide_index=True,
)

# --- Trend lines ---
st.subheader("Return % over time")
ret_chart = alt.Chart(filt).mark_line(point=True).encode(
    x=alt.X("run_at:T", title="Run timestamp"),
    y=alt.Y("return_pct:Q", title="Return %"),
    color=alt.Color("symbol:N"),
    strokeDash="mode:N",
    tooltip=["run_at:T", "symbol", "mode", "n_trades",
             "win_rate_pct", "return_pct", "max_drawdown_pct"],
).properties(height=300)
st.altair_chart(ret_chart, use_container_width=True)

st.subheader("Win rate % over time")
wr_chart = alt.Chart(filt).mark_line(point=True).encode(
    x=alt.X("run_at:T", title="Run timestamp"),
    y=alt.Y("win_rate_pct:Q", title="Win rate %"),
    color=alt.Color("symbol:N"),
    strokeDash="mode:N",
    tooltip=["run_at:T", "symbol", "mode", "n_trades",
             "win_rate_pct", "return_pct"],
).properties(height=260)
st.altair_chart(wr_chart, use_container_width=True)

st.subheader("Trade count over time")
ct_chart = alt.Chart(filt).mark_bar().encode(
    x=alt.X("run_at:T", title="Run timestamp"),
    y=alt.Y("n_trades:Q", title="Closed trades in window"),
    color=alt.Color("symbol:N"),
    column="mode:N",
).properties(height=240)
st.altair_chart(ct_chart, use_container_width=True)

with st.expander("Raw runs"):
    st.dataframe(
        filt[["run_at", "symbol", "interval", "mode", "bars",
              "n_trades", "wins", "losses", "win_rate_pct",
              "return_pct", "max_drawdown_pct", "git_sha"]],
        use_container_width=True, hide_index=True,
    )
