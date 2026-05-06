#!/usr/bin/env python3
"""Reconcile: summarize the trades the bot took in a date range from Supabase.

Referenced by docs/RUNBOOK.md as the weekly diff-against-backtest tool. We
don't have a backtest output to diff against in v1, so this prints a
"what trades happened" summary by symbol with PnL, count, and win rate.

Usage:
  python scripts/reconcile.py --start 2026-05-01 --end 2026-05-07
  python scripts/reconcile.py --start 2026-05-01 --end 2026-05-07 --symbol BTC-USDT
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone

from bot.config import load
from bot.state import SUPABASE_AVAILABLE


def parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="ISO date e.g. 2026-05-01")
    p.add_argument("--end", required=True, help="ISO date e.g. 2026-05-07")
    p.add_argument("--symbol", default=None, help="filter to one symbol")
    args = p.parse_args()

    settings = load()
    if not settings.supabase_url or not settings.supabase_key:
        print("Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY in .env.",
              file=sys.stderr)
        return 1
    if not SUPABASE_AVAILABLE:
        print("supabase-py not installed. pip install -e .[dev]", file=sys.stderr)
        return 1

    from supabase import create_client
    client = create_client(settings.supabase_url, settings.supabase_key)

    start = parse_date(args.start)
    end = parse_date(args.end)
    q = (client.table("positions")
         .select("*")
         .gte("opened_at", start.isoformat())
         .lt("opened_at", end.isoformat()))
    if args.symbol:
        q = q.eq("symbol", args.symbol)

    rows = q.execute().data or []
    if not rows:
        print(f"No trades opened between {args.start} and {args.end}.")
        return 0

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)

    total_pnl = 0.0
    total_trades = total_wins = total_losses = total_open = 0
    print(f"Trades from {args.start} to {args.end} ({len(rows)} total)")
    print(f"{'symbol':<14} {'count':>5} {'wins':>5} {'losses':>6} "
          f"{'open':>5} {'win%':>6} {'pnl_usd':>10}")
    print("-" * 60)
    for sym, trades in sorted(by_symbol.items()):
        wins = sum(1 for t in trades if (t.get("realized_pnl_usd") or 0) > 0)
        losses = sum(1 for t in trades if (t.get("realized_pnl_usd") or 0) < 0)
        opens = sum(1 for t in trades if t.get("closed_at") is None)
        pnl = sum((t.get("realized_pnl_usd") or 0) for t in trades)
        closed = wins + losses
        win_rate = (wins / closed * 100) if closed else 0
        print(f"{sym:<14} {len(trades):>5} {wins:>5} {losses:>6} "
              f"{opens:>5} {win_rate:>5.1f}% {pnl:>+10.2f}")
        total_pnl += pnl
        total_trades += len(trades)
        total_wins += wins
        total_losses += losses
        total_open += opens
    print("-" * 60)
    closed = total_wins + total_losses
    overall_wr = (total_wins / closed * 100) if closed else 0
    print(f"{'TOTAL':<14} {total_trades:>5} {total_wins:>5} {total_losses:>6} "
          f"{total_open:>5} {overall_wr:>5.1f}% {total_pnl:>+10.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
