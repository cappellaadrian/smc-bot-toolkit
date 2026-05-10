#!/usr/bin/env python3
"""Pull multi-year historical OHLCV from BingX for backtesting.

BingX's spot kline endpoint returns up to 1000 candles per call. We page
backwards using the `endTime` parameter until we have the requested span.

Output: data/<symbol>_<interval>.parquet

Usage:
  python3 fetch_history.py BTC-USDT 4h 1095   # 3 years of 4h candles
  python3 fetch_history.py ETH-USDT 4h 1095
"""
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]      # .../live_bot
DATA_DIR = ROOT / "data"

KLINE_URL = "https://open-api.bingx.com/openApi/spot/v2/market/kline"
INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def fetch_page(symbol: str, interval: str, end_ms: int, limit: int = 1000) -> pd.DataFrame:
    params = {"symbol": symbol, "interval": interval, "endTime": end_ms, "limit": limit}
    r = requests.get(KLINE_URL, params=params, timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        if j.get("code") == 100204:
            return pd.DataFrame()
        raise RuntimeError(f"BingX error: {j}")
    rows = j.get("data") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "volume", "close_ts", "quote_vol"
    ])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df = df.set_index("dt").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def fetch_history(symbol: str, interval: str, days: int) -> pd.DataFrame:
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    span_ms = days * 86_400_000
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    earliest_target = end_ms - span_ms
    chunks: list[pd.DataFrame] = []
    page = 0
    while True:
        page += 1
        df = fetch_page(symbol, interval, end_ms=end_ms)
        if df.empty:
            print(f"  page {page}: empty, stopping")
            break
        first_ts = int(df.index[0].timestamp() * 1000)
        last_ts = int(df.index[-1].timestamp() * 1000)
        chunks.append(df)
        print(f"  page {page}: {len(df)} bars [{df.index[0]} .. {df.index[-1]}]", flush=True)
        if first_ts <= earliest_target:
            break
        # Step end_ms back to one interval before this chunk's first bar
        end_ms = first_ts - INTERVAL_MS[interval]
        time.sleep(0.25)  # be polite
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    out = out[out.index >= cutoff]
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    symbol = sys.argv[1]
    interval = sys.argv[2] if len(sys.argv) > 2 else "4h"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 1095
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {days} days of {symbol} {interval}...", flush=True)
    df = fetch_history(symbol, interval, days)
    if df.empty:
        print("No data returned", file=sys.stderr)
        sys.exit(2)
    out = DATA_DIR / f"{symbol}_{interval}.parquet"
    df.to_parquet(out)
    print(f"Wrote {len(df)} bars to {out}")
    print(f"Range: {df.index[0]} .. {df.index[-1]}")


if __name__ == "__main__":
    main()
