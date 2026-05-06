"""Live Performance — read the bot's Supabase tables and render KPIs.

Run via the multi-page Streamlit app:
  streamlit run streamlit_app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

# Promote st.secrets to env (works on Streamlit Cloud + local).
try:
    for k, v in st.secrets.items():
        if isinstance(v, (str, int, float)):
            os.environ.setdefault(k, str(v))
except Exception:
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(ROOT / ".env", override=False)

st.set_page_config(page_title="Live Performance", layout="wide")
st.title("Live Performance")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.warning(
        "Supabase isn't configured yet. Once you set `SUPABASE_URL` and "
        "`SUPABASE_KEY` (in Streamlit secrets or `.env`), this page will "
        "show your bot's equity curve and trade history."
    )
    st.markdown(
        """
**To set up:**
1. Create a Supabase project at https://supabase.com (free tier is fine).
2. Run `supabase/migrations/20260506_init.sql` in the SQL editor.
3. Copy the project URL and anon key into your secrets.
4. Reload this page.

See `docs/PAPER_TRADE_SETUP.md` for the full walkthrough.
"""
    )
    st.stop()

try:
    from supabase import create_client
except ImportError:
    st.error("supabase-py not installed. `pip install supabase`")
    st.stop()


@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


@st.cache_data(ttl=30)
def fetch_positions() -> pd.DataFrame:
    client = get_client()
    rows = (client.table("positions").select("*")
            .order("opened_at", desc=True).limit(2000).execute().data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["opened_at"] = pd.to_datetime(df["opened_at"])
    df["closed_at"] = pd.to_datetime(df["closed_at"], errors="coerce")
    for col in ["entry_price", "exit_price", "size_usd", "stop_loss",
                "take_profit_1", "take_profit_2", "realized_pnl_usd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=30)
def fetch_equity() -> pd.DataFrame:
    client = get_client()
    rows = (client.table("equity_snapshots").select("*")
            .order("ts", desc=False).limit(5000).execute().data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])
    for col in ["equity", "daily_pnl_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=30)
def fetch_kill_events() -> pd.DataFrame:
    client = get_client()
    rows = (client.table("kill_switch_events").select("*")
            .order("ts", desc=True).limit(50).execute().data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


positions = fetch_positions()
equity = fetch_equity()
kills = fetch_kill_events()

c1, c2, c3, c4 = st.columns(4)
if not equity.empty:
    latest_equity = float(equity.iloc[-1]["equity"])
    starting = float(equity.iloc[0]["equity"])
    pct = (latest_equity / starting - 1) * 100 if starting else 0
    c1.metric("Current equity", f"${latest_equity:,.2f}", f"{pct:+.2f}%")
else:
    c1.metric("Current equity", "—")

closed = positions[positions["closed_at"].notna()] if not positions.empty else pd.DataFrame()
open_count = len(positions) - len(closed) if not positions.empty else 0
c2.metric("Open positions", open_count)

if not closed.empty:
    wins = (closed["realized_pnl_usd"] > 0).sum()
    losses = (closed["realized_pnl_usd"] < 0).sum()
    win_rate = wins / max(1, wins + losses) * 100
    c3.metric("Win rate", f"{win_rate:.1f}%", f"{wins}W / {losses}L")
else:
    c3.metric("Win rate", "—")

if not closed.empty:
    total_pnl = closed["realized_pnl_usd"].sum()
    c4.metric("Realized PnL", f"${total_pnl:+,.2f}")
else:
    c4.metric("Realized PnL", "—")

st.subheader("Equity curve")
if equity.empty:
    st.info("No equity snapshots yet. Once the bot runs through a candle it will start logging.")
else:
    chart = alt.Chart(equity).mark_line().encode(
        x=alt.X("ts:T", title="time"),
        y=alt.Y("equity:Q", title="equity (USD)", scale=alt.Scale(zero=False)),
        tooltip=["ts", "equity", "daily_pnl_pct"],
    ).properties(height=320)
    st.altair_chart(chart, use_container_width=True)

st.subheader("Per-symbol summary")
if closed.empty:
    st.info("No closed trades yet.")
else:
    by_sym = (closed.groupby("symbol")
              .agg(trades=("id", "count"),
                   wins=("realized_pnl_usd", lambda s: (s > 0).sum()),
                   losses=("realized_pnl_usd", lambda s: (s < 0).sum()),
                   pnl=("realized_pnl_usd", "sum"))
              .reset_index())
    by_sym["win_rate_pct"] = (by_sym["wins"] / (by_sym["wins"] + by_sym["losses"]).clip(lower=1) * 100).round(1)
    by_sym = by_sym[["symbol", "trades", "wins", "losses", "win_rate_pct", "pnl"]]
    st.dataframe(by_sym, use_container_width=True, hide_index=True)

if not closed.empty:
    st.subheader("Outcomes")
    outcome = closed["outcome"].value_counts().reset_index()
    outcome.columns = ["outcome", "count"]
    chart = alt.Chart(outcome).mark_arc().encode(
        theta="count:Q",
        color="outcome:N",
        tooltip=["outcome", "count"],
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)

st.subheader("Recent trades")
if positions.empty:
    st.info("No trades yet.")
else:
    show_cols = ["opened_at", "closed_at", "symbol", "side", "entry_price",
                 "exit_price", "size_usd", "outcome", "realized_pnl_usd"]
    show = positions[show_cols].copy()
    show["realized_pnl_usd"] = show["realized_pnl_usd"].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)

if not kills.empty:
    st.subheader("Kill-switch events")
    st.dataframe(kills, use_container_width=True, hide_index=True)
