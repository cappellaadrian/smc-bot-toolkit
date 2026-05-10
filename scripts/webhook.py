#!/usr/bin/env python3
"""TradingView webhook receiver.

When a TradingView alert fires, it POSTs JSON here. We:
  1. Verify the shared token (query param or X-Token header)
  2. Parse the payload
  3. Run a Claude review using the methodology spec
  4. Insert a `reviewed_trades` row in Supabase (status=planned)
  5. Send a Telegram alert with the verdict + link to the journal

Run with:
  uvicorn scripts.webhook:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]      # .../live_bot
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env", override=False)

import anthropic  # noqa: E402
import requests   # noqa: E402

SPEC_PATH = ROOT / "docs" / "daniel_ramirez_bot_strategy.md"

WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def load_spec() -> str:
    return SPEC_PATH.read_text(encoding="utf-8") if SPEC_PATH.exists() else ""


def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY):
        return None
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


SYSTEM_PROMPT = """You are a strict trade reviewer applying a specific encoded SMC methodology to user trade ideas.

The methodology is below. Use it as the rubric. Be concise — this is an automated webhook flow.

Output a short Markdown response (under 800 tokens) with ONLY:
## Verdict
One of: **VALID per spec** | **PARTIAL match** | **NOT a methodology trade** | **INSUFFICIENT INFO**

## Why
2-4 bullet points on which criteria pass/fail.

## Suggested adjustments
1-3 bullet points if applicable.

Be strict. If a confluence is unstated, mark it missing rather than guessing."""


def parse_verdict(md: str) -> str | None:
    m = re.search(r"##\s*Verdict\s*\n+\s*\**(\w[^\n*]*?)\**\s*(?:$|\n)", md, re.IGNORECASE)
    if not m:
        return None
    text = m.group(1).strip().upper()
    for v in ("VALID", "PARTIAL", "NOT", "INSUFFICIENT"):
        if v in text:
            return v
    return None


def claude_review(payload: dict) -> dict:
    """Returns {verdict, full_text}."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
    if client is None:
        return {"verdict": None, "full_text": "(no ANTHROPIC_API_KEY)"}
    spec = load_spec()
    user_msg = (
        f"Symbol: {payload.get('symbol') or 'unspecified'}\n"
        f"Timeframe: {payload.get('tf') or payload.get('timeframe') or 'unspecified'}\n"
        f"Side: {payload.get('side') or 'unspecified'}\n"
        f"Entry: {payload.get('entry') or '-'}\n"
        f"Stop: {payload.get('stop') or '-'}\n"
        f"TP1: {payload.get('tp1') or '-'}\n"
        f"TP2: {payload.get('tp2') or '-'}\n"
        f"Note: {payload.get('note') or payload.get('description') or '-'}"
    )
    try:
        r = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=900,
            system=SYSTEM_PROMPT + "\n\n--- METHODOLOGY ---\n\n" + spec,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = r.content[0].text
        return {"verdict": parse_verdict(text), "full_text": text}
    except anthropic.APIError as e:
        return {"verdict": None, "full_text": f"Claude error: {e}"}


def send_telegram(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


app = FastAPI(title="SMC TV Webhook")


@app.get("/health")
async def health():
    spec_ok = SPEC_PATH.exists()
    sb = get_supabase() is not None
    tg = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    anth = bool(ANTHROPIC_API_KEY)
    return {"ok": True, "spec_loaded": spec_ok, "supabase": sb,
            "telegram": tg, "anthropic": anth}


@app.post("/tv-webhook")
async def tv_webhook(
    request: Request,
    token: Optional[str] = Query(default=None),
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
):
    if not WEBHOOK_TOKEN:
        raise HTTPException(status_code=500, detail="WEBHOOK_TOKEN not configured")
    incoming = token or x_token or ""
    if incoming != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")

    raw_body = await request.body()
    text = raw_body.decode("utf-8", errors="replace")
    # TradingView sometimes sends JSON, sometimes plain text. Try both.
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            payload = {"note": str(payload)}
    except json.JSONDecodeError:
        payload = {"note": text.strip()}

    payload.setdefault("source", "tradingview")

    # Run Claude review (synchronous; webhook OK to take a few seconds)
    review = claude_review(payload)

    # Insert into Supabase
    trade_id = None
    sb = get_supabase()
    if sb is not None:
        try:
            row = {
                "symbol": payload.get("symbol"),
                "timeframe": payload.get("tf") or payload.get("timeframe"),
                "side": payload.get("side"),
                "description": (payload.get("note") or payload.get("description") or "")[:5000],
                "has_chart": False,
                "verdict": review["verdict"],
                "claude_summary": (review["full_text"] or "")[:500],
                "claude_full": (review["full_text"] or "")[:50000],
                "scores": None,
                "status": "planned",
                "planned_entry": _maybe_float(payload.get("entry")),
                "planned_stop": _maybe_float(payload.get("stop")),
                "planned_tp1": _maybe_float(payload.get("tp1")),
                "planned_tp2": _maybe_float(payload.get("tp2")),
                "risk_pct": _maybe_float(payload.get("risk_pct")),
                "notes": f"source=tradingview\nraw={text[:1000]}",
            }
            resp = sb.table("reviewed_trades").insert(row).execute()
            trade_id = resp.data[0]["id"] if resp.data else None
        except Exception as e:
            print(f"[webhook] supabase insert failed: {e}", file=sys.stderr)

    # Telegram alert
    summary_text = (
        f"<b>TV alert → {review['verdict'] or '?'}</b>\n"
        f"{payload.get('symbol') or '?'} {payload.get('side') or '?'} "
        f"@ {payload.get('entry') or '?'}\n"
        f"SL {payload.get('stop') or '?'} · TP1 {payload.get('tp1') or '?'} · "
        f"TP2 {payload.get('tp2') or '?'}\n\n"
        f"{(review['full_text'] or '')[:600]}"
    )
    send_telegram(summary_text)

    return JSONResponse({
        "ok": True,
        "trade_id": trade_id,
        "verdict": review["verdict"],
    })


def _maybe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
