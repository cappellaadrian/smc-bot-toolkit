"""Trade Analytics — aggregate stats and charts on reviewed trades.

Run via the multi-page Streamlit app:
  streamlit run streamlit_app.py
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

st.set_page_config(page_title="Trade Analytics", layout="wide")
st.title("Trade Analytics")
st.caption(
    "Aggregate stats on the trades you saved in the journal. The first "
    "question this page is built to answer: when Claude said VALID, what "
    "was your actual win rate?"
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


@st.cache_data(ttl=15)
def fetch_joined() -> pd.DataFrame:
    client = get_client()
    trades = client.table("reviewed_trades").select("*").execute().data or []
    outcomes = client.table("trade_outcomes").select("*").execute().data or []
    if not trades:
        return pd.DataFrame()
    t = pd.DataFrame(trades)
    o = pd.DataFrame(outcomes) if outcomes else pd.DataFrame(
        columns=["trade_id", "exit_price", "outcome", "pnl_pips", "r_multiple", "closed_at"]
    )
    t["created_at"] = pd.to_datetime(t["created_at"])
    if "closed_at" in o:
        o["closed_at"] = pd.to_datetime(o["closed_at"])
    if "r_multiple" in o:
        o["r_multiple"] = pd.to_numeric(o["r_multiple"], errors="coerce")
    if "pnl_pips" in o:
        o["pnl_pips"] = pd.to_numeric(o["pnl_pips"], errors="coerce")
    df = t.merge(o.rename(columns={"trade_id": "id"}), how="left", on="id")
    return df


df = fetch_joined()

if df.empty:
    st.info("No trades saved yet.")
    st.stop()

closed = df[df["status"] == "closed"].copy()
total = len(df)
taken = (df["status"].isin(["taken", "closed"])).sum()
skipped = (df["status"] == "skipped").sum()

# --- Top-line KPIs ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total reviewed", total)
c2.metric("Taken", int(taken))
c3.metric("Closed", len(closed))
if not closed.empty and "r_multiple" in closed:
    avg_r = closed["r_multiple"].mean()
    wins = (closed["r_multiple"] > 0).sum()
    losses = (closed["r_multiple"] <= 0).sum()
    win_rate = wins / max(1, wins + losses) * 100
    c4.metric("Win rate", f"{win_rate:.1f}%", f"avg R {avg_r:+.2f}")
else:
    c4.metric("Win rate", "—")

if closed.empty:
    st.info("No closed trades yet — close some trades in the **Trade Journal** "
            "to populate the analytics below.")
    st.stop()

# --- Per-verdict win rate / R ---
st.subheader("Win rate vs Claude's verdict")

per_verdict = (closed.groupby(closed["verdict"].fillna("UNKNOWN"))
               .agg(trades=("id", "count"),
                    wins=("r_multiple", lambda s: int((s > 0).sum())),
                    losses=("r_multiple", lambda s: int((s <= 0).sum())),
                    avg_r=("r_multiple", "mean"),
                    total_r=("r_multiple", "sum"))
               .reset_index().rename(columns={"verdict": "verdict"}))
per_verdict["win_rate_pct"] = (per_verdict["wins"] /
                                (per_verdict["wins"] + per_verdict["losses"]).clip(lower=1) * 100).round(1)
per_verdict["avg_r"] = per_verdict["avg_r"].round(2)
per_verdict["total_r"] = per_verdict["total_r"].round(2)
st.dataframe(per_verdict, use_container_width=True, hide_index=True)

if len(per_verdict) >= 1:
    chart = alt.Chart(per_verdict).mark_bar().encode(
        x=alt.X("verdict:N", title="Claude verdict"),
        y=alt.Y("win_rate_pct:Q", title="Win rate (%)"),
        tooltip=["verdict", "trades", "wins", "losses", "win_rate_pct", "avg_r"],
    ).properties(height=260)
    st.altair_chart(chart, use_container_width=True)

# --- Equity (cumulative R) curve ---
st.subheader("Cumulative R")
curve = closed.sort_values("closed_at").copy()
curve["cum_r"] = curve["r_multiple"].cumsum()
chart = alt.Chart(curve).mark_line(point=True).encode(
    x=alt.X("closed_at:T", title="Closed at"),
    y=alt.Y("cum_r:Q", title="Cumulative R"),
    tooltip=["closed_at:T", "symbol:N", "verdict:N", "r_multiple:Q", "cum_r:Q"],
).properties(height=320)
st.altair_chart(chart, use_container_width=True)

# --- Distribution of R-multiples ---
st.subheader("Distribution of R outcomes")
dist = alt.Chart(closed).mark_bar().encode(
    x=alt.X("r_multiple:Q", bin=alt.Bin(maxbins=20), title="R multiple"),
    y=alt.Y("count()", title="Trades"),
    color=alt.condition(alt.datum.r_multiple > 0,
                         alt.value("#2ecc71"), alt.value("#e74c3c")),
).properties(height=260)
st.altair_chart(dist, use_container_width=True)

# --- Per-symbol breakdown ---
st.subheader("Per-symbol")
per_sym = (closed.groupby(closed["symbol"].fillna("(none)"))
           .agg(trades=("id", "count"),
                avg_r=("r_multiple", "mean"),
                total_r=("r_multiple", "sum"),
                wins=("r_multiple", lambda s: int((s > 0).sum())),
                losses=("r_multiple", lambda s: int((s <= 0).sum())))
           .reset_index())
per_sym["win_rate_pct"] = (per_sym["wins"] /
                            (per_sym["wins"] + per_sym["losses"]).clip(lower=1) * 100).round(1)
per_sym["avg_r"] = per_sym["avg_r"].round(2)
per_sym["total_r"] = per_sym["total_r"].round(2)
st.dataframe(per_sym.sort_values("total_r", ascending=False),
             use_container_width=True, hide_index=True)
