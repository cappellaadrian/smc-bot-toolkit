"""
Market data feed.

V1 implementation: REST polling of BingX kline endpoint at the candle close
boundary. Simple, reliable, sufficient for 4h timeframe trading.

V2 TODO: switch to websocket for sub-second data (only needed for lower TFs).
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator
import pandas as pd
import requests
from loguru import logger


BINGX_KLINE_URL = "https://open-api.bingx.com/openApi/spot/v2/market/kline"

INTERVAL_TO_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400,
}


def fetch_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Synchronous BingX kline fetch. Returns latest `limit` closed candles."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(BINGX_KLINE_URL, params=params, timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        if j.get("code") == 100204:
            return pd.DataFrame()
        raise RuntimeError(f"BingX error: {j}")
    rows = j["data"]
    df = pd.DataFrame(rows, columns=[
        "ts", "open", "high", "low", "close", "volume", "close_ts", "quote_vol"
    ])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df = df.set_index("dt").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def next_close_time(now: datetime, interval: str) -> datetime:
    """Compute the next candle-close timestamp aligned to the interval."""
    secs = INTERVAL_TO_SECONDS[interval]
    epoch = int(now.timestamp())
    next_close = ((epoch // secs) + 1) * secs
    return datetime.fromtimestamp(next_close, tz=timezone.utc)


class CandleFeed:
    """Async generator yielding the latest closed-candle DataFrame for each symbol
    on every interval boundary."""

    def __init__(self, symbols: list[str], interval: str, history_bars: int = 200):
        self.symbols = symbols
        self.interval = interval
        self.history_bars = history_bars
        self._cache: dict[str, pd.DataFrame] = {}

    def warm_up(self) -> None:
        """Initial history pull. Call once before stream()."""
        for sym in self.symbols:
            logger.info(f"warming up {sym} {self.interval}...")
            df = fetch_klines(sym, self.interval, limit=self.history_bars)
            if df.empty:
                raise RuntimeError(f"no history available for {sym}")
            self._cache[sym] = df
            logger.info(f"  -> {len(df)} candles, latest {df.index[-1]}")

    async def stream(self) -> AsyncIterator[tuple[str, pd.DataFrame]]:
        """Yield (symbol, dataframe) tuples on each new closed candle."""
        if not self._cache:
            self.warm_up()
        while True:
            now = datetime.now(timezone.utc)
            target = next_close_time(now, self.interval) + timedelta(seconds=15)
            wait = (target - now).total_seconds()
            logger.debug(f"sleeping {wait:.0f}s until {target}")
            await asyncio.sleep(max(1, wait))
            for sym in self.symbols:
                try:
                    df = fetch_klines(sym, self.interval, limit=self.history_bars)
                    if df.empty:
                        logger.warning(f"empty kline response for {sym}")
                        continue
                    self._cache[sym] = df
                    yield sym, df
                except Exception as e:
                    logger.error(f"fetch failed for {sym}: {e}")
                    continue
