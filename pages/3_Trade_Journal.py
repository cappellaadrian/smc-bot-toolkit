"""Trade Journal — list reviewed trades, mark outcomes, track P&L.

Run via the multi-page Streamlit app:
  streamlit run streamlit_app.py
"""
from __future__ import annotations

import os
from pathlib import Path

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

st.set_page_config(page_title="Trade Journal", layout="wide")
st.title("Trade Journal")
st.caption(
    "Every trade you analyzed in the Reviewer that you saved here. Mark "
    "outcomes when trades close to feed the Analytics page."
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not (SUPABASE_URL and SUPABASE_KEY):
    st.warning("Supabase isn't configured. Set SUPABASE_URL + SUPABASE_KEY.")
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
def fetch_trades() -> pd.DataFrame:
    client = get_client()
    rows = (client.table("reviewed_trades").select("*")
            .order("created_at", desc=True).limit(500).execute().data) or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"])
    return df


@st.cache_data(ttl=15)
def fetch_outcomes() -> pd.DataFrame:
    client = get_client()
    rows = (client.table("trade_outcomes").select("*")
            .order("closed_at", desc=True).limit(500).execute().data) or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["closed_at"] = pd.to_datetime(df["closed_at"])
    return df


def is_forex_pair(symbol: str | None) -> bool:
    if not symbol:
        return False
    s = symbol.upper().replace("-", "").replace("/", "")
    return len(s) == 6 and s.isalpha() and any(s.endswith(q) for q in ("USD", "JPY", "EUR", "GBP", "AUD", "CHF", "NZD", "CAD"))


def pip_size(symbol: str | None) -> float:
    if not symbol:
        return 0.0
    s = symbol.upper()
    if "JPY" in s:
        return 0.01
    if is_forex_pair(s):
        return 0.0001
    return 0.0  # crypto/futures: pips not directly applicable


def compute_outcome_metrics(trade: dict, exit_price: float) -> dict:
    side = trade.get("side") or "long"
    entry = trade.get("planned_entry") or 0.0
    stop = trade.get("planned_stop") or 0.0
    if not (entry and stop):
        return {"pnl_pips": None, "r_multiple": None, "pnl_usd_pct": None}
    risk_per_unit = abs(entry - stop)
    pnl_per_unit = (exit_price - entry) if side == "long" else (entry - exit_price)
    r = pnl_per_unit / risk_per_unit if risk_per_unit else None
    pip = pip_size(trade.get("symbol"))
    pips = pnl_per_unit / pip if pip else None
    return {"pnl_pips": pips, "r_multiple": r, "pnl_usd_pct": None}


trades = fetch_trades()
outcomes = fetch_outcomes()

if trades.empty:
    st.info("No reviewed trades saved yet. Use the **Trade Reviewer** page, "
            "analyze a trade, then click *Save to journal*.")
    st.stop()

# --- KPIs ---
joined = trades.merge(outcomes.add_prefix("outcome_"), how="left",
                      left_on="id", right_on="outcome_trade_id")
closed = joined[joined["status"] == "closed"]
taken = joined[joined["status"].isin(["taken", "closed"])]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total reviewed", len(trades))
c2.metric("Taken", int((trades["status"].isin(["taken", "closed"])).sum()))
c3.metric("Closed", int((trades["status"] == "closed").sum()))
if not closed.empty and "outcome_r_multiple" in closed:
    avg_r = pd.to_numeric(closed["outcome_r_multiple"], errors="coerce").mean()
    wins = (pd.to_numeric(closed["outcome_r_multiple"], errors="coerce") > 0).sum()
    losses = (pd.to_numeric(closed["outcome_r_multiple"], errors="coerce") <= 0).sum()
    win_rate = wins / max(1, wins + losses) * 100
    c4.metric("Win rate", f"{win_rate:.0f}%", f"avg R {avg_r:+.2f}" if pd.notna(avg_r) else "")
else:
    c4.metric("Win rate", "—")

st.divider()

# --- Filters ---
fcol1, fcol2, fcol3 = st.columns(3)
status_filter = fcol1.multiselect(
    "Status", ["planned", "taken", "skipped", "closed"],
    default=["planned", "taken", "closed"],
)
verdict_filter = fcol2.multiselect(
    "Verdict", ["VALID", "PARTIAL", "NOT", "INSUFFICIENT"],
    default=["VALID", "PARTIAL"],
)
symbols_avail = sorted([s for s in trades["symbol"].dropna().unique()])
symbol_filter = fcol3.multiselect("Symbol", symbols_avail, default=symbols_avail)

mask = trades["status"].isin(status_filter)
if verdict_filter:
    mask &= trades["verdict"].fillna("").isin(verdict_filter) | trades["verdict"].isna() & ("INSUFFICIENT" in verdict_filter)
if symbol_filter:
    mask &= trades["symbol"].isin(symbol_filter)
filtered = trades[mask].copy()

# --- Open / planned trades: collapsible cards with close-trade form ---
open_trades = filtered[filtered["status"].isin(["planned", "taken"])]
if not open_trades.empty:
    st.subheader(f"Open / planned ({len(open_trades)})")
    for _, t in open_trades.iterrows():
        title = f"{t['symbol'] or '—'} · {t['side'] or '—'} · {t['verdict'] or '?'} · " \
                f"{t['created_at'].strftime('%Y-%m-%d %H:%M')}"
        with st.expander(title):
            cc1, cc2 = st.columns([2, 1])
            with cc1:
                st.markdown(f"**Description:** {t.get('description') or '—'}")
                st.markdown(f"**Verdict:** {t.get('verdict') or '?'}")
                if t.get("claude_summary"):
                    st.markdown(f"**Summary:** {t['claude_summary']}")
                with st.expander("Full Claude analysis"):
                    st.markdown(t.get("claude_full") or "—")
            with cc2:
                st.markdown(f"**Entry:** {t.get('planned_entry') or '—'}")
                st.markdown(f"**Stop:** {t.get('planned_stop') or '—'}")
                st.markdown(f"**TP1:** {t.get('planned_tp1') or '—'}")
                st.markdown(f"**TP2:** {t.get('planned_tp2') or '—'}")
                st.markdown(f"**Risk %:** {t.get('risk_pct') or '—'}")

            with st.form(f"close_{t['id']}"):
                cc3, cc4, cc5 = st.columns(3)
                with cc3:
                    out_kind = st.selectbox(
                        "Outcome",
                        ["tp2", "tp1", "be", "sl", "manual_win", "manual_loss"],
                        key=f"out_{t['id']}",
                    )
                with cc4:
                    exit_price = st.number_input(
                        "Exit price", value=float(t.get("planned_tp1") or 0),
                        format="%.5f", key=f"px_{t['id']}",
                    )
                with cc5:
                    out_note = st.text_input("Note", key=f"note_{t['id']}")
                close_btn = st.form_submit_button("Mark closed")

            if close_btn:
                metrics = compute_outcome_metrics(t.to_dict(), exit_price)
                outcome_row = {
                    "trade_id": t["id"],
                    "exit_price": exit_price,
                    "outcome": out_kind,
                    "pnl_pips": metrics["pnl_pips"],
                    "r_multiple": metrics["r_multiple"],
                    "notes": out_note or None,
                }
                client = get_client()
                try:
                    client.table("trade_outcomes").insert(outcome_row).execute()
                    client.table("reviewed_trades").update({"status": "closed"}).eq("id", t["id"]).execute()
                    st.success(f"Closed. R={metrics['r_multiple']:.2f}" if metrics["r_multiple"] is not None else "Closed.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to close: {e}")
else:
    st.info("No open or planned trades match the filters.")

st.divider()

# --- Closed / skipped: tabular ---
closed_show = filtered[filtered["status"].isin(["closed", "skipped"])]
if not closed_show.empty:
    st.subheader(f"Closed / skipped ({len(closed_show)})")
    enriched = closed_show.merge(
        outcomes[["trade_id", "exit_price", "outcome", "r_multiple", "pnl_pips", "closed_at"]]
            .rename(columns={"trade_id": "id"}),
        how="left", on="id",
    )
    cols = ["created_at", "symbol", "timeframe", "side", "verdict", "status",
            "planned_entry", "planned_stop", "planned_tp1", "exit_price",
            "outcome", "r_multiple", "pnl_pips"]
    cols = [c for c in cols if c in enriched.columns]
    enriched = enriched[cols].copy()
    if "r_multiple" in enriched:
        enriched["r_multiple"] = pd.to_numeric(enriched["r_multiple"], errors="coerce").round(2)
    if "pnl_pips" in enriched:
        enriched["pnl_pips"] = pd.to_numeric(enriched["pnl_pips"], errors="coerce").round(1)
    st.dataframe(enriched, use_container_width=True, hide_index=True)
