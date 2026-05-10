#!/usr/bin/env python3
"""Run backtests across BTC + ETH at all filter modes, write results to
Supabase `backtest_runs`. Designed to be invoked from cron.

Usage:
  python -m scripts.run_backtest                    # default: BTC+ETH 4h, all modes
  python -m scripts.run_backtest --symbol BTC-USDT  # one symbol
  python -m scripts.run_backtest --interval 4h --days 360
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]      # .../live_bot
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env", override=False)

from bot.paper_broker import PaperBroker  # noqa: E402
from bot.strategy import StrategyConfig, generate_signal, position_size_usd  # noqa: E402
from fetch_history import fetch_history  # noqa: E402


MODES: dict[str, StrategyConfig] = {
    "strict":  StrategyConfig(require_bias=True,  require_pd=True),
    "no-bias": StrategyConfig(require_bias=False, require_pd=True),
    "no-pd":   StrategyConfig(require_bias=True,  require_pd=False),
    "loose":   StrategyConfig(require_bias=False, require_pd=False),
}


def git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return ""


async def backtest_one(df: pd.DataFrame, symbol: str, cfg: StrategyConfig,
                       initial_equity: float = 10_000, risk_pct: float = 0.01,
                       lookback: int = 200) -> dict:
    broker = PaperBroker(initial_equity=initial_equity)
    n_signals = 0
    equity_curve: list[float] = []
    for i in range(lookback, len(df) - 1):
        next_bar = df.iloc[i + 1]
        for pos_id, action, price in broker.check_exits(symbol, next_bar["high"], next_bar["low"]):
            if action == "tp1":
                await broker.partial_close(pos_id, price, fraction=0.5)
            else:
                await broker.close_position(pos_id, price, reason=action)
        win = df.iloc[max(0, i - lookback): i + 1]
        sig = generate_signal(win, cfg)
        if sig is None:
            continue
        n_signals += 1
        size = position_size_usd(broker.equity(), sig.entry, sig.stop_loss, risk_pct)
        if size <= 0:
            continue
        await broker.open_position(
            symbol=symbol, side=sig.side, size_usd=size,
            entry_price=sig.entry, stop_loss=sig.stop_loss,
            tp1=sig.take_profit_1, tp2=sig.take_profit_2, notes=sig.notes,
        )
        equity_curve.append(broker.equity())
    last_close = float(df.iloc[-1]["close"])
    for pos in list(broker.positions.values()):
        await broker.close_position(pos.id, last_close, reason="manual")

    closed = broker.closed_positions
    wins = sum(1 for p in closed if (p.realized_pnl_usd or 0) > 0)
    losses = sum(1 for p in closed if (p.realized_pnl_usd or 0) < 0)
    by_outcome: dict[str, int] = {}
    for p in closed:
        by_outcome[p.outcome or "unknown"] = by_outcome.get(p.outcome or "unknown", 0) + 1
    final = broker.equity()
    if equity_curve:
        peak = pd.Series(equity_curve).cummax()
        dd_series = (pd.Series(equity_curve) / peak - 1) * 100
        max_dd = float(dd_series.min())
    else:
        max_dd = 0.0
    return {
        "n_signals": n_signals,
        "n_trades": len(closed),
        "wins": wins,
        "losses": losses,
        "by_outcome": by_outcome,
        "win_rate_pct": (wins / max(1, wins + losses)) * 100,
        "return_pct": (final / initial_equity - 1) * 100,
        "final_equity": final,
        "max_drawdown_pct": max_dd,
    }


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["BTC-USDT", "ETH-USDT"])
    p.add_argument("--interval", default="4h")
    p.add_argument("--days", type=int, default=360)
    p.add_argument("--equity", type=float, default=10_000.0)
    p.add_argument("--risk", type=float, default=0.01)
    p.add_argument("--no-fetch", action="store_true",
                    help="use existing data/<symbol>_<interval>.parquet without refresh")
    args = p.parse_args()

    sb = get_supabase()
    if sb is None:
        print("WARNING: Supabase not configured. Results will be printed but not stored.")

    sha = git_sha()
    rows_to_write: list[dict] = []
    for sym in args.symbols:
        path = ROOT / "data" / f"{sym}_{args.interval}.parquet"
        if not args.no_fetch:
            print(f"[{sym}] fetching {args.days}d of {args.interval} from BingX...")
            df = fetch_history(sym, args.interval, args.days)
            if df.empty:
                print(f"  empty, skipping")
                continue
            (ROOT / "data").mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        else:
            if not path.exists():
                print(f"[{sym}] no parquet at {path}, skipping")
                continue
            df = pd.read_parquet(path)
        print(f"[{sym}] {len(df)} bars from {df.index[0]} to {df.index[-1]}")
        for mode, cfg in MODES.items():
            r = asyncio.run(backtest_one(df, sym, cfg, args.equity, args.risk))
            row = {
                "symbol": sym,
                "interval": args.interval,
                "mode": mode,
                "initial_equity": args.equity,
                "risk_pct": args.risk,
                "bars": len(df),
                "range_start": df.index[0].isoformat(),
                "range_end": df.index[-1].isoformat(),
                "git_sha": sha,
                **r,
            }
            print(f"  {mode:<8} trades={r['n_trades']:>4} win%={r['win_rate_pct']:>5.1f} "
                  f"return%={r['return_pct']:>+7.2f} dd%={r['max_drawdown_pct']:>+6.2f}")
            rows_to_write.append(row)

    if sb and rows_to_write:
        try:
            sb.table("backtest_runs").insert(rows_to_write).execute()
            print(f"Wrote {len(rows_to_write)} rows to backtest_runs.")
        except Exception as e:
            print(f"ERROR writing to Supabase: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
