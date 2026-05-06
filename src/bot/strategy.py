"""
Strategy: SMC IFVG entry on a single timeframe (4h).

This is a methodology-derived strategy distilled from 1775 trader transcripts
(see docs/daniel_ramirez_bot_strategy.md for the full blended spec).

V1 implements the spec's "Setup A: Inversion FVG (IFVG) Entry" on a single
timeframe only. Multi-timeframe bias and SMT divergence are deferred per
CLAUDE.md's "things to skip for v1" list.

Pipeline (called once per closed candle):
  1. Bias: market_structure on swings (HH+HL = bullish; LH+LL = bearish)
  2. Premium/Discount filter: longs in discount only, shorts in premium only
  3. FVG: most-recent valid FVG within max_age, sized between min/max pct
  4. IFVG trigger: current bar close inverts that FVG
  5. Liquidity sweep: V-shaped sweep within last sweep_lookback bars
  6. DOL: equal highs/lows or nearest swing past min_rr * stop_distance
  7. TP1 = max(entry + min_rr * R, DOL); TP2 = entry + max_rr * R
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
    # IFVG-specific. The methodology spec uses these for ES/NQ futures at
    # 5M; we adapt to BTC/ETH 4h here. Wider size band to accommodate higher
    # crypto volatility and 4h gap distribution.
    max_fvg_age: int = 20            # bars; FVGs older than this are stale
    min_fvg_size_pct: float = 0.001  # 0.1% of price
    max_fvg_size_pct: float = 0.020  # 2.0% of price
    sweep_lookback: int = 30         # bars to walk back searching for a sweep
    stop_buffer_pct: float = 0.001   # extra distance below sweep low / above sweep high
    min_rr: float = 2.0              # TP1 floor in R-multiples
    max_rr: float = 3.0              # TP2 cap in R-multiples
    # Filter toggles. Strict (require_bias=True, require_pd=True) follows
    # the spec faithfully but produces ~1 trade/year/symbol on 4h crypto.
    # Default is require_bias=False because backtests showed the bias filter
    # cuts signals 22x without improving win rate; require_pd stays on.
    require_bias: bool = False       # restrict by HH/HL or LH/LL structure
    require_pd: bool = True          # require discount for long, premium for short


def generate_signal(df: pd.DataFrame, cfg: StrategyConfig = StrategyConfig()) -> Optional[Signal]:
    """One Signal or None per closed bar. Same contract as before so the
    engine and backtester are unchanged."""
    if len(df) < 60:
        return None

    swings = d.find_swings(df, lookback=cfg.swing_lookback)
    if len(swings) < 4:
        return None

    bias = d.market_structure(swings)
    if cfg.require_bias and bias == "neutral":
        return None

    bar = df.iloc[-1]
    price = float(bar["close"])
    range_high = float(df["high"].iloc[-cfg.range_window:].max())
    range_low = float(df["low"].iloc[-cfg.range_window:].min())
    in_disc = d.in_discount(price, range_high, range_low)
    in_prem = d.in_premium(price, range_high, range_low)

    long_ok = cfg.enable_long and (
        not cfg.require_bias or bias in ("bullish", "neutral")
    ) and (not cfg.require_pd or in_disc)
    short_ok = cfg.enable_short and (
        not cfg.require_bias or bias in ("bearish", "neutral")
    ) and (not cfg.require_pd or in_prem)

    if long_ok:
        sig = _long_signal(df, swings, bar, price, cfg)
        if sig is not None:
            return sig

    if short_ok:
        sig = _short_signal(df, swings, bar, price, cfg)
        if sig is not None:
            return sig

    return None


def _long_signal(df, swings, bar, price, cfg) -> Optional[Signal]:
    fvg = d.find_freshly_inverted_fvg(
        df,
        side="long",
        max_age=cfg.max_fvg_age,
        min_size_pct=cfg.min_fvg_size_pct,
        max_size_pct=cfg.max_fvg_size_pct,
    )
    if fvg is None:
        return None

    sweep = d.detect_recent_liquidity_sweep(df, swings, lookback=cfg.sweep_lookback)
    if sweep is None or sweep["kind"] != "bullish":
        return None

    entry = price * (1 + cfg.slippage_pct)
    stop = sweep["swept_level"] * (1 - cfg.stop_buffer_pct)
    if entry <= stop:
        return None
    risk = entry - stop

    dol = d.find_dol(swings, side="long", entry=entry, min_distance=cfg.min_rr * risk)
    if dol is None:
        return None

    tp1 = max(entry + cfg.min_rr * risk, dol)
    tp2 = entry + cfg.max_rr * risk

    return Signal(
        side="long",
        entry=entry,
        stop_loss=stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        swept_level=float(sweep["swept_level"]),
        bias="bullish",
        notes=f"ifvg_long sweep@{sweep['swept_level']:.2f} fvg=[{fvg.bottom:.2f},{fvg.top:.2f}]",
    )


def _short_signal(df, swings, bar, price, cfg) -> Optional[Signal]:
    fvg = d.find_freshly_inverted_fvg(
        df,
        side="short",
        max_age=cfg.max_fvg_age,
        min_size_pct=cfg.min_fvg_size_pct,
        max_size_pct=cfg.max_fvg_size_pct,
    )
    if fvg is None:
        return None

    sweep = d.detect_recent_liquidity_sweep(df, swings, lookback=cfg.sweep_lookback)
    if sweep is None or sweep["kind"] != "bearish":
        return None

    entry = price * (1 - cfg.slippage_pct)
    stop = sweep["swept_level"] * (1 + cfg.stop_buffer_pct)
    if entry >= stop:
        return None
    risk = stop - entry

    dol = d.find_dol(swings, side="short", entry=entry, min_distance=cfg.min_rr * risk)
    if dol is None:
        return None

    tp1 = min(entry - cfg.min_rr * risk, dol)
    tp2 = entry - cfg.max_rr * risk

    return Signal(
        side="short",
        entry=entry,
        stop_loss=stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        swept_level=float(sweep["swept_level"]),
        bias="bearish",
        notes=f"ifvg_short sweep@{sweep['swept_level']:.2f} fvg=[{fvg.bottom:.2f},{fvg.top:.2f}]",
    )


def position_size_usd(equity: float, entry: float, stop_loss: float, risk_pct: float,
                      max_leverage: float = 10.0) -> float:
    """USD notional for a position risking risk_pct of equity, capped at max_leverage."""
    risk_usd = equity * risk_pct
    distance = abs(entry - stop_loss) / entry
    if distance <= 0:
        return 0.0
    size = risk_usd / distance
    return min(size, equity * max_leverage)
