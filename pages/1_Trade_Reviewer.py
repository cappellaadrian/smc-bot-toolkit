"""Trade Reviewer — Claude-powered methodology check, with optional save to journal.

Run via the multi-page Streamlit app:
  streamlit run streamlit_app.py
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]            # .../live_bot
PROJECT_ROOT = ROOT.parent                             # .../trading-project
SPEC_PATH = ROOT / "docs" / "daniel_ramirez_bot_strategy.md"

# Promote st.secrets to env (works on Streamlit Cloud + local).
try:
    for k, v in st.secrets.items():
        if isinstance(v, (str, int, float)):
            os.environ.setdefault(k, str(v))
except Exception:
    pass

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(ROOT / ".env", override=False)

import anthropic  # noqa: E402

st.set_page_config(page_title="Trade Reviewer", layout="wide")
st.title("Trade Reviewer")
st.caption(
    "Paste a trade idea or upload a chart screenshot. Claude evaluates it "
    "against the encoded methodology (bias, P/D, FVG, sweep, IFVG, DOL, RR). "
    "Save analyzed trades to the journal to track outcomes over time."
)

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "ANTHROPIC_API_KEY not set. Add it in Streamlit secrets or `.env`, "
        "then reload."
    )
    st.stop()

if not SPEC_PATH.exists():
    st.error(f"Methodology spec not found at {SPEC_PATH}.")
    st.stop()


@st.cache_data
def load_spec() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


SYSTEM_PROMPT = """You are a strict trade reviewer applying a specific encoded SMC methodology to user trade ideas. Your job is to score and critique the trade against the methodology, not to predict whether it will win.

The methodology is below. Use it as the definitive rubric. Cite specific sections when scoring.

Output a Markdown response with these sections:

## Verdict
One of: **VALID per spec** | **PARTIAL match** | **NOT a methodology trade** | **INSUFFICIENT INFO** (when the description or chart doesn't show enough to judge).

## Score by criterion
A 0-10 score for each of these, with a one-line reason:
- HTF bias direction (bullish / bearish / neutral)
- Premium/Discount alignment (long in discount, short in premium)
- Valid FVG (singular, fresh, correct size)
- Liquidity sweep (V-shaped, recent)
- IFVG inversion trigger (close past the FVG boundary)
- Draw on Liquidity (DOL) target
- Risk:Reward setup (TP1 >= 2R, TP2 cap at 3R)
- Session timing (kill zone vs lunch / Asia)
- Optional confluences (SMT divergence, BPR, displacement quality)

## Missing or wrong
Bullet list of things the trade is missing relative to the spec, or things that contradict it.

## Suggested adjustments
Concrete changes that would make this a methodology-compliant trade. Specify levels in the same units the user gave.

## Honest framing
A short reminder that "matches the methodology" is not the same as "will be profitable". The encoded strategy backtests near break-even / slightly negative.

Rules:
- Be strict. If a confluence is unstated, mark it missing rather than guessing.
- If the user uploaded a chart, use it. Read the price action visible on the chart for bias, sweeps, FVGs.
- If both a chart and text are given, cross-check them and flag contradictions.
- Quote 1-2 specific lines from the methodology when relevant.
- Never invent levels the user didn't show. If you cannot read a number from the chart, say so and ask for it."""


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


@st.cache_resource
def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not (url and key):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


@st.cache_data(ttl=60)
def fetch_calibration(_sb_marker: str, limit: int = 50) -> str:
    """Pull last `limit` closed trades from Supabase, group by Claude verdict,
    return a compact text block to inject into the system prompt. Returns
    empty string if not enough data.

    The `_sb_marker` arg is just a cache-buster so st.cache_data picks up
    schema changes; supabase client itself is unhashable.
    """
    sb = get_supabase()
    if sb is None:
        return ""
    try:
        # Fetch closed trades + their outcomes (left join via two queries)
        trades = (sb.table("reviewed_trades")
                  .select("id, verdict, status, symbol, side")
                  .eq("status", "closed")
                  .order("created_at", desc=True)
                  .limit(limit)
                  .execute().data) or []
        if len(trades) < 5:
            return ""
        ids = [t["id"] for t in trades]
        outcomes = (sb.table("trade_outcomes")
                    .select("trade_id, r_multiple, outcome")
                    .in_("trade_id", ids)
                    .execute().data) or []
    except Exception:
        return ""
    if not outcomes:
        return ""
    o_by_id = {o["trade_id"]: o for o in outcomes}
    buckets: dict[str, list[float]] = {"VALID": [], "PARTIAL": [], "NOT": [], "INSUFFICIENT": []}
    for t in trades:
        o = o_by_id.get(t["id"])
        if o is None:
            continue
        v = (t.get("verdict") or "").upper() or "INSUFFICIENT"
        try:
            r = float(o["r_multiple"]) if o.get("r_multiple") is not None else None
        except (TypeError, ValueError):
            r = None
        if r is not None:
            buckets.setdefault(v, []).append(r)
    lines: list[str] = []
    for verdict in ("VALID", "PARTIAL", "NOT", "INSUFFICIENT"):
        rs = buckets.get(verdict, [])
        if not rs:
            continue
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r <= 0)
        wr = wins / max(1, wins + losses) * 100
        avg_r = sum(rs) / len(rs)
        lines.append(f"  {verdict}: {len(rs)} trades, win_rate={wr:.0f}%, avg_R={avg_r:+.2f}")
    if not lines:
        return ""
    return (
        "\n\n--- USER'S JOURNAL CALIBRATION (last "
        f"{len(trades)} closed trades) ---\n"
        + "\n".join(lines)
        + "\n\nCalibrate against this. If you'd score this trade VALID but the user has only "
        "won 30% on VALID trades, flag that mismatch in your verdict. Add a 'Calibration' "
        "section after 'Honest framing' that compares this trade to the user's actual "
        "historical hit rate by verdict."
    )


def parse_verdict(md: str) -> str | None:
    m = re.search(r"##\s*Verdict\s*\n+\s*\**(\w[^\n*]*?)\**\s*(?:$|\n)", md, re.IGNORECASE)
    if not m:
        return None
    text = m.group(1).strip().upper()
    if "VALID" in text:
        return "VALID"
    if "PARTIAL" in text:
        return "PARTIAL"
    if "NOT" in text:
        return "NOT"
    if "INSUFFICIENT" in text:
        return "INSUFFICIENT"
    return None


def parse_scores(md: str) -> dict[str, int]:
    """Best-effort: find lines like '- HTF bias direction ... 7/10' or '7'."""
    scores: dict[str, int] = {}
    section = re.search(r"##\s*Score[^\n]*\n(.+?)(?:\n##|\Z)", md, re.DOTALL | re.IGNORECASE)
    if not section:
        return scores
    body = section.group(1)
    for line in body.splitlines():
        m = re.search(r"^\s*[-*]\s*([^:]+?)(?::|—|-)\s*\**(\d{1,2})(?:\s*/\s*10)?\**", line)
        if not m:
            m = re.search(r"^\s*[-*]\s*\**([^*:]+?)\**\s*[:\-—]\s*\**(\d{1,2})\b", line)
        if m:
            label = m.group(1).strip().lower()
            try:
                val = int(m.group(2))
            except ValueError:
                continue
            if 0 <= val <= 10:
                scores[label[:60]] = val
    return scores


def parse_summary(md: str) -> str:
    m = re.search(r"##\s*Verdict\s*\n+(.+?)(?:\n##|\Z)", md, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    return m.group(1).strip()[:500]


def build_user_message(description: str, image_bytes: bytes | None,
                       image_type: str | None, symbol: str, tf: str) -> list[dict]:
    parts: list[dict] = []
    header = (
        f"Symbol: {symbol or 'unspecified'}\n"
        f"Timeframe: {tf or 'unspecified'}\n\n"
        f"Trade description from the user:\n{description.strip() or '(no text provided)'}"
    )
    parts.append({"type": "text", "text": header})
    if image_bytes:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_type or "image/png",
                "data": b64,
            },
        })
    return parts


# --- Form: trade inputs ---
with st.form("trade_form", clear_on_submit=False):
    col1, col2 = st.columns([2, 1])
    with col1:
        description = st.text_area(
            "Trade idea",
            height=180,
            placeholder=(
                "Going long BTC at 65,200. Bearish 4h FVG just inverted "
                "(close above 65,150). Sweep of swing low at 63,800 happened "
                "6 bars ago. Stop at 63,750, TP1 at equal highs 67,400."
            ),
        )
    with col2:
        symbol = st.text_input("Symbol", value="", placeholder="BTC-USDT, EURUSD, ES, ...")
        tf = st.selectbox("Timeframe", ["", "5m", "15m", "1h", "4h", "1d"], index=0)
        side = st.selectbox("Side (optional)", ["", "long", "short"], index=0)
        uploaded = st.file_uploader(
            "Chart screenshot (optional)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=False,
        )
    submitted = st.form_submit_button("Analyze", type="primary")

# --- Run analysis ---
if submitted:
    if not description.strip() and uploaded is None:
        st.warning("Add a trade description, a screenshot, or both.")
        st.stop()

    image_bytes = None
    image_type = None
    if uploaded is not None:
        image_bytes = uploaded.getvalue()
        image_type = uploaded.type or "image/png"
        st.image(image_bytes, caption="Uploaded chart", use_container_width=True)

    spec = load_spec()
    calibration = fetch_calibration("v1")
    user_content = build_user_message(description, image_bytes, image_type, symbol, tf)

    if calibration:
        st.caption("Using journal calibration from your last closed trades.")

    system_text = (
        SYSTEM_PROMPT
        + "\n\n--- ENCODED METHODOLOGY ---\n\n"
        + spec
        + (calibration or "")
    )

    with st.spinner("Claude is reviewing the trade..."):
        client = get_client()
        try:
            r = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                system=[
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as e:
            st.error(f"Anthropic API error: {e}")
            st.stop()

    text = r.content[0].text
    usage = r.usage
    in_cost = usage.input_tokens / 1e6 * 3.0
    out_cost = usage.output_tokens / 1e6 * 15.0
    cache_read_cost = (usage.cache_read_input_tokens or 0) / 1e6 * 0.30
    cache_create_cost = (usage.cache_creation_input_tokens or 0) / 1e6 * 3.75
    total = in_cost + out_cost + cache_read_cost + cache_create_cost

    # Stash in session state for the save form below
    st.session_state["last_analysis"] = {
        "text": text,
        "verdict": parse_verdict(text),
        "scores": parse_scores(text),
        "summary": parse_summary(text),
        "symbol": symbol,
        "tf": tf,
        "side": side,
        "description": description,
        "has_chart": image_bytes is not None,
        "cost": total,
    }

# --- Show last analysis (persists across reruns inside this session) ---
analysis = st.session_state.get("last_analysis")
if analysis:
    st.caption(f"Last analysis cost: ~${analysis['cost']:.4f}")
    st.markdown(analysis["text"])

    st.divider()
    st.subheader("Save to journal")
    sb = get_supabase()
    if sb is None:
        st.info(
            "Supabase not configured — set `SUPABASE_URL` and `SUPABASE_KEY` "
            "to save analyzed trades to the journal."
        )
    else:
        with st.form("save_trade_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                save_status = st.selectbox(
                    "Action",
                    ["taken", "planned", "skipped"],
                    index=0,
                    help="taken = you opened the trade; planned = waiting; skipped = no fill",
                )
                save_side = st.selectbox(
                    "Side",
                    ["long", "short"],
                    index=0 if (analysis.get("side") or "long") == "long" else 1,
                )
            with c2:
                planned_entry = st.number_input("Entry", value=0.0, format="%.5f")
                planned_stop = st.number_input("Stop", value=0.0, format="%.5f")
            with c3:
                planned_tp1 = st.number_input("TP1", value=0.0, format="%.5f")
                planned_tp2 = st.number_input("TP2 (optional)", value=0.0, format="%.5f")
            risk_pct = st.number_input("Risk % of equity", value=1.0, min_value=0.0, max_value=10.0, step=0.1)
            note = st.text_area("Notes (optional)", height=70)
            save = st.form_submit_button("Save trade", type="primary")

        if save:
            row = {
                "symbol": analysis["symbol"] or None,
                "timeframe": analysis["tf"] or None,
                "side": save_side,
                "description": analysis["description"] or None,
                "has_chart": analysis["has_chart"],
                "verdict": analysis["verdict"],
                "claude_summary": analysis["summary"],
                "claude_full": analysis["text"][:50000],
                "scores": analysis["scores"] or None,
                "status": save_status,
                "planned_entry": planned_entry or None,
                "planned_stop": planned_stop or None,
                "planned_tp1": planned_tp1 or None,
                "planned_tp2": planned_tp2 or None,
                "risk_pct": risk_pct or None,
                "notes": note or None,
            }
            try:
                resp = sb.table("reviewed_trades").insert(row).execute()
                trade_id = resp.data[0]["id"] if resp.data else "(unknown)"
                st.success(f"Saved as `{trade_id[:8]}...`. See **Trade Journal** in the sidebar.")
            except Exception as e:
                st.error(f"Save failed: {e}")
