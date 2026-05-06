"""
Strategy: turn a rolling DataFrame of closed candles into a Signal (or None).

This is a thin wrapper around detectors. The same logic that drove the backtest
should produce identical signals here when fed the same data.
"""
from dataclasses import dataclass
from typing import Optional, Literal
import pandas as pd
from . import detectors as d


@dataclass
class Signal:
    side: Literal["long", "short"]
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    swept_level: float
    bias: str
    notes: str


@dataclass
class StrategyConfig:
    swing_lookback: int = 3
    range_window: int = 50
    enable_long: bool = True
    enable_short: bool = True
    slippage_pct: float = 0.0005


def generate_signal(df: pd.DataFrame, cfg: StrategyConfig = StrategyConfig()) -> Optional[Signal]:
    """Called once per closed candle. Returns a Signal or None."""
    if len(df) < 60:
        return None

    i = len(df) - 1
    bar = df.iloc[i]
    swings = d.find_swings(df, lookback=cfg.swing_lookback)
    if len(swings) < 4:
        return None

    bias = d.market_structure(swings)
    sweep = d.detect_liquidity_sweep(df, swings, i)
    if sweep is None:
        return None

    range_high = df["high"].iloc[-cfg.range_window:].max()
    range_low = df["low"].iloc[-cfg.range_window:].min()

    if cfg.enable_long and sweep["kind"] == "bullish" and bias in ("bullish", "neutral"):
        ob = d.find_order_block(df, i, "bullish", max_lookback=10)
        if ob is None:
            return None
        price = bar["close"]
        if not (ob.low <= price <= ob.high):
            return None
        if not d.in_discount(price, range_high, range_low):
            return None
        entry = price * (1 + cfg.slippage_pct)
        sl = sweep["swept_level"] * 0.999
        if entry <= sl:
            return None
        risk = entry - sl
        tp1 = entry + risk
        highs_above = [s.price for s in swings if s.kind == "high" and s.price > entry]
        tp2 = min(highs_above) if highs_above else entry + 3 * risk
        return Signal(
            side="long", entry=entry, stop_loss=sl,
            take_profit_1=tp1, take_profit_2=tp2,
            swept_level=sweep["swept_level"], bias=bias,
            notes=f"sweep@{sweep['swept_level']:.2f}",
        )

    if cfg.enable_short and sweep["kind"] == "bearish" and bias in ("bearish", "neutral"):
        ob = d.find_order_block(df, i, "bearish", max_lookback=10)
        if ob is None:
            return None
        price = bar["close"]
        if not (ob.low <= price <= ob.high):
            return None
        if not d.in_premium(price, range_high, range_low):
            return None
        entry = price * (1 - cfg.slippage_pct)
        sl = sweep["swept_level"] * 1.001
        if entry >= sl:
            return None
        risk = sl - entry
        tp1 = entry - risk
        lows_below = [s.price for s in swings if s.kind == "low" and s.price < entry]
        tp2 = max(lows_below) if lows_below else entry - 3 * risk
        return Signal(
            side="short", entry=entry, stop_loss=sl,
            take_profit_1=tp1, take_profit_2=tp2,
            swept_level=sweep["swept_level"], bias=bias,
            notes=f"sweep@{sweep['swept_level']:.2f}",
        )

    return None


def position_size_usd(equity: float, entry: float, stop_loss: float, risk_pct: float,
                     max_leverage: float = 10.0) -> float:
    """Return USD notional for a position risking risk_pct of equity."""
    risk_usd = equity * risk_pct
    distance = abs(entry - stop_loss) / entry
    if distance <= 0:
        return 0.0
    size = risk_usd / distance
    return min(size, equity * max_leverage)
