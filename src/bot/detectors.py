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


# -----------------------------------------------------------------------------
# Additions for the methodology-derived strategy (Setup A: IFVG entry).
# These are additive — existing functions above are untouched.
# -----------------------------------------------------------------------------


def find_recent_fvg(
    df: pd.DataFrame,
    kind: Literal["bullish", "bearish"],
    max_age: int = 10,
    min_size_pct: float = 0.002,
    max_size_pct: float = 0.010,
) -> Optional[FVG]:
    """Return the most-recent unfilled FVG of `kind` within `max_age` bars,
    sized between min_size_pct and max_size_pct of the FVG's reference price.
    Returns None if no qualifying FVG exists."""
    n = len(df)
    if n < 3:
        return None
    start = max(2, n - max_age - 1)
    fvgs = find_fvgs_in_window(df, start_idx=start, end_idx=n - 1)
    matching = [f for f in fvgs if f.kind == kind]
    if not matching:
        return None
    matching.sort(key=lambda f: f.created_idx, reverse=True)
    for fvg in matching:
        size = abs(fvg.top - fvg.bottom)
        ref = (fvg.top + fvg.bottom) / 2
        if ref <= 0:
            continue
        size_pct = size / ref
        if not (min_size_pct <= size_pct <= max_size_pct):
            continue
        # FVG is "stale" if it was already inverted (closed past) in a prior
        # bar. We want a FRESH inversion on the current bar. Wicks/highs that
        # poked through but didn't close past are tolerated (FVG was tested
        # and held).
        later = df.iloc[fvg.created_idx + 1 : -1]  # exclude current bar
        if kind == "bullish" and (later["close"] < fvg.bottom).any():
            continue
        if kind == "bearish" and (later["close"] > fvg.top).any():
            continue
        return fvg
    return None


def is_ifvg_trigger(bar: pd.Series, fvg: FVG, side: Literal["long", "short"]) -> bool:
    """A bar inverts an FVG when its close crosses the opposite side of the gap.

    Long (bullish IFVG entry): a previously bearish FVG is broken upward —
        bar.close > fvg.top.
    Short (bearish IFVG entry): a previously bullish FVG is broken downward —
        bar.close < fvg.bottom.
    """
    if side == "long":
        return fvg.kind == "bearish" and bar["close"] > fvg.top
    if side == "short":
        return fvg.kind == "bullish" and bar["close"] < fvg.bottom
    return False


def find_freshly_inverted_fvg(
    df: pd.DataFrame,
    side: Literal["long", "short"],
    max_age: int = 20,
    min_size_pct: float = 0.001,
    max_size_pct: float = 0.020,
) -> Optional[FVG]:
    """Return an FVG that the LATEST bar in df has just inverted (closed past)
    for the first time. Used as the IFVG entry trigger.

    For side='long': look for a bearish FVG where last_bar.close > fvg.top
        and no prior bar after creation had close > fvg.top.
    For side='short': mirror with bullish FVG and close < fvg.bottom.
    """
    n = len(df)
    if n < 3:
        return None
    last = df.iloc[-1]
    start = max(2, n - max_age - 1)
    kind = "bearish" if side == "long" else "bullish"
    fvgs = [f for f in find_fvgs_in_window(df, start_idx=start, end_idx=n - 2)
            if f.kind == kind]
    fvgs.sort(key=lambda f: f.created_idx, reverse=True)
    for fvg in fvgs:
        size = abs(fvg.top - fvg.bottom)
        ref = (fvg.top + fvg.bottom) / 2
        if ref <= 0:
            continue
        size_pct = size / ref
        if not (min_size_pct <= size_pct <= max_size_pct):
            continue
        intermediate = df.iloc[fvg.created_idx + 1 : -1]
        if side == "long":
            if last["close"] <= fvg.top:
                continue
            if (intermediate["close"] > fvg.top).any():
                continue
        else:
            if last["close"] >= fvg.bottom:
                continue
            if (intermediate["close"] < fvg.bottom).any():
                continue
        return fvg
    return None


def detect_recent_liquidity_sweep(
    df: pd.DataFrame,
    swings: List[Swing],
    lookback: int = 20,
) -> Optional[dict]:
    """Walk the last `lookback` bars looking for a V-shaped sweep candle:
    one that pierced a recent swing high/low and closed back inside.

    Returns the most recent qualifying sweep (or None). The dict matches
    detect_liquidity_sweep's: {"kind", "swept_level", "swing_idx", "bar_idx"}.
    """
    n = len(df)
    if n == 0:
        return None
    start = max(0, n - lookback)
    for i in range(n - 1, start - 1, -1):
        bar = df.iloc[i]
        recent_lows = [s for s in swings if s.kind == "low" and s.idx < i][-5:]
        for s in recent_lows:
            if bar["low"] < s.price and bar["close"] > s.price:
                return {
                    "kind": "bullish",
                    "swept_level": s.price,
                    "swing_idx": s.idx,
                    "bar_idx": i,
                }
        recent_highs = [s for s in swings if s.kind == "high" and s.idx < i][-5:]
        for s in recent_highs:
            if bar["high"] > s.price and bar["close"] < s.price:
                return {
                    "kind": "bearish",
                    "swept_level": s.price,
                    "swing_idx": s.idx,
                    "bar_idx": i,
                }
    return None


def find_dol(
    swings: List[Swing],
    side: Literal["long", "short"],
    entry: float,
    min_distance: float,
) -> Optional[float]:
    """Find Draw on Liquidity: nearest qualifying swing high (long) or
    swing low (short) at least `min_distance` away from `entry`.

    Equal highs/lows are detected by clustering swings within a small
    tolerance and using the cluster level. If no cluster qualifies, the
    nearest single swing past `min_distance` is returned.
    """
    tol_pct = 0.001  # 0.1% tolerance for equal highs/lows
    if side == "long":
        candidates = sorted(
            (s.price for s in swings if s.kind == "high" and s.price > entry + min_distance)
        )
        if not candidates:
            return None
        # Look for clusters
        for i in range(len(candidates) - 1):
            a, b = candidates[i], candidates[i + 1]
            if abs(b - a) / a <= tol_pct:
                return (a + b) / 2  # equal highs
        return candidates[0]
    else:  # short
        candidates = sorted(
            (s.price for s in swings if s.kind == "low" and s.price < entry - min_distance),
            reverse=True,
        )
        if not candidates:
            return None
        for i in range(len(candidates) - 1):
            a, b = candidates[i], candidates[i + 1]
            if abs(b - a) / a <= tol_pct:
                return (a + b) / 2
        return candidates[0]
