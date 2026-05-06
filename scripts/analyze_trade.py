#!/usr/bin/env python3
"""Streamlit page: paste a trade idea (and/or upload a chart screenshot) and
have Claude evaluate it against the encoded SMC methodology.

Run with:
  streamlit run scripts/analyze_trade.py

Reads ANTHROPIC_API_KEY from project .env (../../.env) or live_bot/.env.
The methodology spec is loaded once and cached in the system prompt
(so subsequent analyses are cheap due to prompt caching).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]            # .../live_bot
PROJECT_ROOT = ROOT.parent                             # .../trading-project
SPEC_PATH = ROOT / "docs" / "daniel_ramirez_bot_strategy.md"

# .env preference: project root (where the extraction script writes it),
# then live_bot's own .env if a separate one exists.
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(ROOT / ".env", override=False)

import anthropic  # noqa: E402

st.set_page_config(page_title="SMC Trade Reviewer", layout="wide")
st.title("SMC Trade Reviewer")
st.caption(
    "Paste a trade idea or upload a chart screenshot. Claude evaluates it "
    "against the encoded methodology (Setups A/B/C, bias, P/D, FVG, sweep, DOL)."
)

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "ANTHROPIC_API_KEY not set. Add it to "
        f"`{PROJECT_ROOT}/.env` and reload."
    )
    st.stop()

if not SPEC_PATH.exists():
    st.error(
        f"Methodology spec not found at {SPEC_PATH}. "
        "Run the synthesis pipeline in the trading-project workspace first."
    )
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
- Never invent levels the user didn't show. If you can't see a number, say "I cannot read this from the chart" and ask for it."""


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


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


# --- UI ---
with st.form("trade_form", clear_on_submit=False):
    col1, col2 = st.columns([2, 1])
    with col1:
        description = st.text_area(
            "Trade idea",
            height=180,
            placeholder=(
                "Going long BTC at 65,200. There's a bearish 4h FVG that just "
                "got inverted (close above 65,150 last candle). Sweep of the "
                "swing low at 63,800 happened 6 bars ago. Stop at 63,750, "
                "TP1 at equal highs 67,400."
            ),
        )
    with col2:
        symbol = st.text_input("Symbol (optional)", value="")
        tf = st.selectbox("Timeframe", ["", "5m", "15m", "1h", "4h", "1d"], index=0)
        uploaded = st.file_uploader(
            "Chart screenshot (optional)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=False,
        )

    submitted = st.form_submit_button("Analyze", type="primary")

if submitted:
    if not description.strip() and uploaded is None:
        st.warning("Add a trade description, a screenshot, or both.")
        st.stop()

    image_bytes = None
    image_type = None
    if uploaded is not None:
        image_bytes = uploaded.getvalue()
        image_type = uploaded.type or "image/png"
        st.image(image_bytes, caption="Uploaded chart", width="stretch")

    spec = load_spec()
    user_content = build_user_message(description, image_bytes, image_type, symbol, tf)

    with st.spinner("Claude is reviewing the trade..."):
        client = get_client()
        try:
            r = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT + "\n\n--- ENCODED METHODOLOGY ---\n\n" + spec,
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
    st.caption(
        f"Tokens: input={usage.input_tokens} output={usage.output_tokens} "
        f"cache_read={usage.cache_read_input_tokens or 0} "
        f"cache_create={usage.cache_creation_input_tokens or 0} "
        f"— cost ~${total:.4f}"
    )
    st.markdown(text)
