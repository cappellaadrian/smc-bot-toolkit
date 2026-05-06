#!/usr/bin/env python3
"""Streamlit dashboard for the SMC paper bot.

Reads the bot's Supabase tables (positions, equity_snapshots, kill_switch_events)
and renders an equity curve, trade ledger, and per-symbol summary.

Run with:
  streamlit run scripts/dashboard.py
  # opens at http://localhost:8501

Requires SUPABASE_URL and SUPABASE_KEY in .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bot.config import load  # noqa: E402

st.set_page_config(page_title="SMC Paper Bot", layout="wide")
st.title("SMC Paper Bot")

settings = load()

if not settings.supabase_url or not settings.supabase_key:
    st.error("Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY in .env, then reload.")
    st.stop()

try:
    from supabase import create_client
except ImportError:
    st.error("supabase-py not installed. Run: pip install -e .[dev]")
    st.stop()


@st.cache_resource
def get_client():
    return create_client(settings.supabase_url, settings.supabase_key)


@st.cache_data(ttl=30)
def fetch_positions() -> pd.DataFrame:
    client = get_client()
    rows = client.table("positions").select("*").order("opened_at", desc=True).limit(2000).execute().data
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

# --- Top row: KPIs ---
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

# --- Equity curve ---
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

# --- Per-symbol breakdown ---
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

# --- Outcomes donut ---
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

# --- Trade ledger ---
st.subheader("Recent trades")
if positions.empty:
    st.info("No trades yet.")
else:
    show_cols = ["opened_at", "closed_at", "symbol", "side", "entry_price",
                 "exit_price", "size_usd", "outcome", "realized_pnl_usd"]
    show = positions[show_cols].copy()
    show["realized_pnl_usd"] = show["realized_pnl_usd"].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)

# --- Kill-switch events ---
if not kills.empty:
    st.subheader("Kill-switch events")
    st.dataframe(kills, use_container_width=True, hide_index=True)
