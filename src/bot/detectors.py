"""
SMC pattern detectors. Ported verbatim from the backtest package.
DO NOT modify these without re-running the backtest to confirm parity.

Functions operate on a pandas DataFrame with columns:
[open, high, low, close, volume] indexed by timestamp.
"""
from dataclasses import dataclass
from typing import Optional, List, Literal
import pandas as pd


@dataclass
class Swing:
    idx: int
    ts: pd.Timestamp
    price: float
    kind: Literal["high", "low"]


@dataclass
class OrderBlock:
    kind: Literal["bullish", "bearish"]
    high: float
    low: float
    created_idx: int
    mitigated: bool = False
    swept_level: Optional[float] = None


@dataclass
class FVG:
    kind: Literal["bullish", "bearish"]
    top: float
    bottom: float
    created_idx: int
    filled: bool = False

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2


def find_swings(df: pd.DataFrame, lookback: int = 3) -> List[Swing]:
    swings = []
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    for i in range(lookback, n - lookback):
        wh = highs[i - lookback : i + lookback + 1]
        wl = lows[i - lookback : i + lookback + 1]
        if highs[i] == wh.max() and (wh == highs[i]).sum() == 1:
            swings.append(Swing(i, df.index[i], highs[i], "high"))
        if lows[i] == wl.min() and (wl == lows[i]).sum() == 1:
            swings.append(Swing(i, df.index[i], lows[i], "low"))
    return sorted(swings, key=lambda s: s.idx)


def market_structure(swings: List[Swing]) -> Literal["bullish", "bearish", "neutral"]:
    highs = [s for s in swings if s.kind == "high"][-2:]
    lows = [s for s in swings if s.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return "neutral"
    hh = highs[1].price > highs[0].price
    hl = lows[1].price > lows[0].price
    lh = highs[1].price < highs[0].price
    ll = lows[1].price < lows[0].price
    if hh and hl: return "bullish"
    if lh and ll: return "bearish"
    return "neutral"


def detect_liquidity_sweep(df: pd.DataFrame, swings: List[Swing], current_idx: int) -> Optional[dict]:
    if current_idx < 1: return None
    candle = df.iloc[current_idx]
    recent_highs = [s for s in swings if s.kind == "high" and s.idx < current_idx][-5:]
    recent_lows = [s for s in swings if s.kind == "low" and s.idx < current_idx][-5:]
    for s in recent_lows:
        if candle["low"] < s.price and candle["close"] > s.price:
            return {"kind": "bullish", "swept_level": s.price, "swing_idx": s.idx}
    for s in recent_highs:
        if candle["high"] > s.price and candle["close"] < s.price:
            return {"kind": "bearish", "swept_level": s.price, "swing_idx": s.idx}
    return None


def find_order_block(df: pd.DataFrame, impulse_end_idx: int, kind: Literal["bullish", "bearish"],
                     max_lookback: int = 15) -> Optional[OrderBlock]:
    start = max(0, impulse_end_idx - max_lookback)
    if kind == "bullish":
        for i in range(impulse_end_idx - 1, start - 1, -1):
            c = df.iloc[i]
            if c["close"] < c["open"]:
                return OrderBlock(kind="bullish", high=c["high"], low=c["low"], created_idx=i)
    else:
        for i in range(impulse_end_idx - 1, start - 1, -1):
            c = df.iloc[i]
            if c["close"] > c["open"]:
                return OrderBlock(kind="bearish", high=c["high"], low=c["low"], created_idx=i)
    return None


def find_fvgs_in_window(df: pd.DataFrame, start_idx: int, end_idx: int) -> List[FVG]:
    fvgs = []
    for i in range(max(2, start_idx), min(len(df), end_idx + 1)):
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]
        if c1["high"] < c3["low"]:
            fvgs.append(FVG(kind="bullish", top=c3["low"], bottom=c1["high"], created_idx=i))
        elif c1["low"] > c3["high"]:
            fvgs.append(FVG(kind="bearish", top=c1["low"], bottom=c3["high"], created_idx=i))
    return fvgs


def in_discount(price: float, range_high: float, range_low: float) -> bool:
    return price < (range_high + range_low) / 2


def in_premium(price: float, range_high: float, range_low: float) -> bool:
    return price > (range_high + range_low) / 2
