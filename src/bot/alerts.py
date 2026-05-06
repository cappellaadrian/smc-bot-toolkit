"""
Telegram alerting. Falls back to logging if not configured.
"""
import asyncio
import requests
from loguru import logger


class TelegramAlerter:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        if not self.enabled:
            logger.warning("Telegram not configured; alerts will go to logs only")

    async def send(self, text: str) -> None:
        if not self.enabled:
            logger.info(f"[alert] {text}")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            # offload sync requests to thread to keep loop responsive
            await asyncio.to_thread(
                requests.post, url,
                data={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"telegram send failed: {e}")

    async def trade_opened(self, symbol: str, side: str, entry: float, sl: float,
                           tp1: float, tp2: float, size_usd: float) -> None:
        await self.send(
            f"<b>OPEN</b> {side.upper()} {symbol}\n"
            f"Entry: {entry:.2f}\n"
            f"SL: {sl:.2f}  TP1: {tp1:.2f}  TP2: {tp2:.2f}\n"
            f"Size: ${size_usd:,.0f}"
        )

    async def trade_closed(self, symbol: str, side: str, exit_price: float,
                           pnl_usd: float, outcome: str) -> None:
        emoji = "+" if pnl_usd >= 0 else "-"
        await self.send(
            f"<b>CLOSE</b> {side.upper()} {symbol}\n"
            f"Exit: {exit_price:.2f} ({outcome})\n"
            f"PnL: {emoji}${abs(pnl_usd):,.2f}"
        )

    async def kill_switch(self, reason: str) -> None:
        await self.send(f"<b>KILL SWITCH</b>\n{reason}\nNew entries blocked until reset.")

    async def error(self, msg: str) -> None:
        await self.send(f"<b>ERROR</b>\n{msg}")
