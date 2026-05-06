"""
State persistence layer. Mirrors broker state to Supabase.

If SUPABASE_URL is empty (e.g. in tests), falls back to a no-op recorder so the
engine can still run without persistence.

Schema (run migrations from supabase/migrations/):
  - positions: id, symbol, side, entry_price, size_usd, sl, tp1, tp2,
               opened_at, closed_at, exit_price, outcome, realized_pnl_usd, notes
  - equity_snapshots: ts, equity, daily_pnl_pct
  - kill_switch_events: ts, tripped, reason
"""
from datetime import datetime, timezone
from typing import Protocol
from loguru import logger

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


class StateStore(Protocol):
    def record_open(self, position: dict) -> None: ...
    def record_close(self, position: dict) -> None: ...
    def record_equity(self, equity: float, daily_pnl_pct: float) -> None: ...
    def record_kill_switch(self, tripped: bool, reason: str) -> None: ...


class NullStateStore:
    """No-op store for tests or when Supabase is not configured."""
    def record_open(self, position: dict) -> None:
        logger.debug(f"[null-store] open: {position.get('id')}")
    def record_close(self, position: dict) -> None:
        logger.debug(f"[null-store] close: {position.get('id')}")
    def record_equity(self, equity: float, daily_pnl_pct: float) -> None:
        logger.debug(f"[null-store] equity={equity:.2f} pnl_pct={daily_pnl_pct:.4f}")
    def record_kill_switch(self, tripped: bool, reason: str) -> None:
        logger.debug(f"[null-store] kill_switch tripped={tripped} reason={reason}")


class SupabaseStateStore:
    def __init__(self, url: str, key: str):
        if not SUPABASE_AVAILABLE:
            raise RuntimeError("supabase-py not installed")
        self.client: Client = create_client(url, key)

    def record_open(self, position: dict) -> None:
        try:
            self.client.table("positions").insert(position).execute()
        except Exception as e:
            logger.error(f"supabase record_open failed: {e}")

    def record_close(self, position: dict) -> None:
        try:
            self.client.table("positions").update({
                "closed_at": position["closed_at"],
                "exit_price": position["exit_price"],
                "outcome": position["outcome"],
                "realized_pnl_usd": position["realized_pnl_usd"],
            }).eq("id", position["id"]).execute()
        except Exception as e:
            logger.error(f"supabase record_close failed: {e}")

    def record_equity(self, equity: float, daily_pnl_pct: float) -> None:
        try:
            self.client.table("equity_snapshots").insert({
                "ts": datetime.now(timezone.utc).isoformat(),
                "equity": equity,
                "daily_pnl_pct": daily_pnl_pct,
            }).execute()
        except Exception as e:
            logger.error(f"supabase record_equity failed: {e}")

    def record_kill_switch(self, tripped: bool, reason: str) -> None:
        try:
            self.client.table("kill_switch_events").insert({
                "ts": datetime.now(timezone.utc).isoformat(),
                "tripped": tripped,
                "reason": reason,
            }).execute()
        except Exception as e:
            logger.error(f"supabase record_kill_switch failed: {e}")


def make_store(url: str, key: str) -> StateStore:
    if not url or not key:
        logger.warning("Supabase not configured; using NullStateStore")
        return NullStateStore()
    return SupabaseStateStore(url, key)
