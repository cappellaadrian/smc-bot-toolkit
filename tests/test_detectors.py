"""
Unit tests for SMC pattern detectors. Pure synthetic OHLCV, no network.
"""
import pandas as pd
import pytest

from bot.detectors import (
    Swing,
    detect_liquidity_sweep,
    detect_recent_liquidity_sweep,
    find_dol,
    find_freshly_inverted_fvg,
    find_fvgs_in_window,
    find_order_block,
    find_recent_fvg,
    find_swings,
    in_discount,
    in_premium,
    is_ifvg_trigger,
    market_structure,
)


def _df(rows: list[dict]) -> pd.DataFrame:
    """Build an OHLCV DataFrame with a default timestamp index."""
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="4h")
    return df


def test_find_swings_picks_strict_extrema():
    rows = [{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}] * 11
    rows[5] = {"open": 1, "high": 5.0, "low": 1, "close": 1, "volume": 1}
    swings = find_swings(_df(rows), lookback=3)
    highs = [s for s in swings if s.kind == "high"]
    assert len(highs) == 1
    assert highs[0].idx == 5
    assert highs[0].price == 5.0


def test_find_swings_skips_ties():
    # Two equal highs in the window -> neither qualifies as a strict swing high.
    rows = [{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}] * 11
    rows[4] = {"open": 1, "high": 5.0, "low": 1, "close": 1, "volume": 1}
    rows[6] = {"open": 1, "high": 5.0, "low": 1, "close": 1, "volume": 1}
    swings = find_swings(_df(rows), lookback=3)
    assert not any(s.kind == "high" and s.price == 5.0 for s in swings)


def test_find_swings_respects_lookback():
    # With lookback=2, indices 2..n-3 are checked. With lookback=5, fewer.
    rows = [{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}] * 11
    rows[5] = {"open": 1, "high": 5.0, "low": 1, "close": 1, "volume": 1}
    assert any(s.idx == 5 for s in find_swings(_df(rows), lookback=2))
    # With lookback=6, range(6, 5) is empty -> no swings detected at all
    assert find_swings(_df(rows), lookback=6) == []


def test_market_structure_bullish_on_hh_hl():
    from bot.detectors import Swing
    swings = [
        Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=100, kind="low"),
        Swing(idx=1, ts=pd.Timestamp("2026-01-01"), price=110, kind="high"),
        Swing(idx=2, ts=pd.Timestamp("2026-01-01"), price=105, kind="low"),  # HL
        Swing(idx=3, ts=pd.Timestamp("2026-01-01"), price=115, kind="high"),  # HH
    ]
    assert market_structure(swings) == "bullish"


def test_market_structure_bearish_on_lh_ll():
    from bot.detectors import Swing
    swings = [
        Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=120, kind="high"),
        Swing(idx=1, ts=pd.Timestamp("2026-01-01"), price=110, kind="low"),
        Swing(idx=2, ts=pd.Timestamp("2026-01-01"), price=115, kind="high"),  # LH
        Swing(idx=3, ts=pd.Timestamp("2026-01-01"), price=105, kind="low"),  # LL
    ]
    assert market_structure(swings) == "bearish"


def test_market_structure_neutral_on_mixed():
    from bot.detectors import Swing
    swings = [
        Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=100, kind="low"),
        Swing(idx=1, ts=pd.Timestamp("2026-01-01"), price=120, kind="high"),
        Swing(idx=2, ts=pd.Timestamp("2026-01-01"), price=95, kind="low"),  # LL
        Swing(idx=3, ts=pd.Timestamp("2026-01-01"), price=125, kind="high"),  # HH (mixed)
    ]
    assert market_structure(swings) == "neutral"


def test_market_structure_neutral_on_insufficient_swings():
    from bot.detectors import Swing
    one_high = [Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=110, kind="high")]
    assert market_structure(one_high) == "neutral"
    assert market_structure([]) == "neutral"


def test_detect_liquidity_sweep_bullish():
    from bot.detectors import Swing
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}] * 5
    rows.append({"open": 100, "high": 100.5, "low": 94.5, "close": 99.0, "volume": 1})
    df = _df(rows)
    swings = [Swing(idx=2, ts=df.index[2], price=95.0, kind="low")]
    sweep = detect_liquidity_sweep(df, swings, current_idx=5)
    assert sweep == {"kind": "bullish", "swept_level": 95.0, "swing_idx": 2}


def test_detect_liquidity_sweep_bearish():
    from bot.detectors import Swing
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}] * 5
    rows.append({"open": 100, "high": 105.5, "low": 99.5, "close": 101.0, "volume": 1})
    df = _df(rows)
    swings = [Swing(idx=2, ts=df.index[2], price=105.0, kind="high")]
    sweep = detect_liquidity_sweep(df, swings, current_idx=5)
    assert sweep == {"kind": "bearish", "swept_level": 105.0, "swing_idx": 2}


def test_detect_liquidity_sweep_returns_none_when_no_pierce():
    from bot.detectors import Swing
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}] * 5
    rows.append({"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1})
    df = _df(rows)
    swings = [Swing(idx=2, ts=df.index[2], price=95.0, kind="low")]
    assert detect_liquidity_sweep(df, swings, current_idx=5) is None


def test_detect_liquidity_sweep_ignores_current_and_future_swings():
    """Swings at or after current_idx must not be considered."""
    from bot.detectors import Swing
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}] * 6
    rows[5] = {"open": 100, "high": 100, "low": 94.5, "close": 99, "volume": 1}
    df = _df(rows)
    swings = [Swing(idx=5, ts=df.index[5], price=95.0, kind="low")]
    assert detect_liquidity_sweep(df, swings, current_idx=5) is None


def test_find_order_block_bullish_finds_first_bearish_walking_back():
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 102, "volume": 1},   # 0 bullish
        {"open": 102, "high": 103, "low": 101, "close": 100, "volume": 1},  # 1 bearish (target)
        {"open": 100, "high": 105, "low": 100, "close": 105, "volume": 1},  # 2 bullish
        {"open": 105, "high": 108, "low": 104, "close": 107, "volume": 1},  # 3 bullish (impulse end)
    ]
    ob = find_order_block(_df(rows), impulse_end_idx=3, kind="bullish", max_lookback=10)
    assert ob is not None
    assert ob.kind == "bullish"
    assert ob.created_idx == 1
    assert ob.high == 103
    assert ob.low == 101


def test_find_order_block_bearish_mirror():
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 98, "volume": 1},    # 0 bearish
        {"open": 98, "high": 99, "low": 97, "close": 100, "volume": 1},     # 1 bullish (target)
        {"open": 100, "high": 100.5, "low": 95, "close": 95, "volume": 1},  # 2 bearish
        {"open": 95, "high": 95.5, "low": 92, "close": 92.5, "volume": 1},  # 3 bearish (impulse end)
    ]
    ob = find_order_block(_df(rows), impulse_end_idx=3, kind="bearish", max_lookback=10)
    assert ob is not None
    assert ob.kind == "bearish"
    assert ob.created_idx == 1


def test_find_order_block_returns_none_when_no_match():
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 102, "volume": 1},
        {"open": 102, "high": 103, "low": 101, "close": 103, "volume": 1},
        {"open": 103, "high": 105, "low": 102, "close": 105, "volume": 1},
    ]
    assert find_order_block(_df(rows), impulse_end_idx=2, kind="bullish", max_lookback=10) is None


def test_find_order_block_respects_max_lookback():
    rows = [
        {"open": 102, "high": 103, "low": 101, "close": 100, "volume": 1},  # 0 bearish (too far back)
        {"open": 100, "high": 101, "low": 99, "close": 102, "volume": 1},   # 1 bullish
        {"open": 102, "high": 103, "low": 101, "close": 103, "volume": 1},  # 2 bullish
        {"open": 103, "high": 105, "low": 102, "close": 105, "volume": 1},  # 3 bullish (impulse end)
    ]
    assert find_order_block(_df(rows), impulse_end_idx=3, kind="bullish", max_lookback=2) is None
    ob = find_order_block(_df(rows), impulse_end_idx=3, kind="bullish", max_lookback=5)
    assert ob is not None and ob.created_idx == 0


def test_find_fvgs_bullish_gap():
    rows = [
        {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},   # 0
        {"open": 100, "high": 102, "low": 100, "close": 101, "volume": 1},  # 1 (impulse)
        {"open": 102, "high": 105, "low": 103, "close": 104, "volume": 1},  # 2: low(103) > c1.high(101) -> bullish FVG
    ]
    fvgs = find_fvgs_in_window(_df(rows), start_idx=0, end_idx=2)
    assert len(fvgs) == 1
    assert fvgs[0].kind == "bullish"
    assert fvgs[0].bottom == 101
    assert fvgs[0].top == 103
    assert fvgs[0].midpoint == 102


def test_find_fvgs_bearish_gap():
    rows = [
        {"open": 100, "high": 105, "low": 103, "close": 104, "volume": 1},   # 0
        {"open": 104, "high": 104, "low": 102, "close": 102.5, "volume": 1},  # 1
        {"open": 102, "high": 101, "low": 99, "close": 100, "volume": 1},    # 2: high(101) < c1.low(103) -> bearish FVG
    ]
    fvgs = find_fvgs_in_window(_df(rows), start_idx=0, end_idx=2)
    assert len(fvgs) == 1
    assert fvgs[0].kind == "bearish"
    assert fvgs[0].top == 103
    assert fvgs[0].bottom == 101


def test_find_fvgs_no_gap():
    rows = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}] * 5
    assert find_fvgs_in_window(_df(rows), start_idx=0, end_idx=4) == []


@pytest.mark.parametrize("price,low,high,expected", [
    (94, 90, 100, True),    # below midpoint (95)
    (95, 90, 100, False),   # at midpoint -> not strictly less
    (100, 90, 110, False),  # at midpoint
    (102, 90, 110, False),  # above midpoint
])
def test_in_discount(price, low, high, expected):
    assert in_discount(price, range_high=high, range_low=low) is expected


@pytest.mark.parametrize("price,low,high,expected", [
    (96, 90, 100, True),    # above midpoint (95)
    (95, 90, 100, False),   # at midpoint
    (100, 90, 110, False),
    (95, 90, 110, False),
])
def test_in_premium(price, low, high, expected):
    assert in_premium(price, range_high=high, range_low=low) is expected


# -----------------------------------------------------------------------------
# Tests for the new IFVG detector functions.
# -----------------------------------------------------------------------------


def _bar(o, h, lo, c, v=1.0):
    return {"open": o, "high": h, "low": lo, "close": c, "volume": v}


def test_is_ifvg_trigger_long():
    from bot.detectors import FVG
    fvg = FVG(kind="bearish", top=105.0, bottom=100.0, created_idx=5)
    assert is_ifvg_trigger(pd.Series({"close": 106.0}), fvg, side="long")
    assert not is_ifvg_trigger(pd.Series({"close": 104.0}), fvg, side="long")
    # Wrong-kind FVG
    bull_fvg = FVG(kind="bullish", top=105.0, bottom=100.0, created_idx=5)
    assert not is_ifvg_trigger(pd.Series({"close": 106.0}), bull_fvg, side="long")


def test_is_ifvg_trigger_short():
    from bot.detectors import FVG
    fvg = FVG(kind="bullish", top=105.0, bottom=100.0, created_idx=5)
    assert is_ifvg_trigger(pd.Series({"close": 99.0}), fvg, side="short")
    assert not is_ifvg_trigger(pd.Series({"close": 101.0}), fvg, side="short")


def test_find_recent_fvg_picks_in_size_band():
    # Build data with one clear bullish FVG and intermediate bars that don't
    # also create FVGs (require c[i-2].high >= c[i].low for those middle indices).
    rows = [
        _bar(100, 101, 99, 100),     # 0  c[i-2] for the FVG
        _bar(100, 100.5, 99.5, 100), # 1  middle (its high won't conflict)
        _bar(101, 105, 103, 104),    # 2  c[i] -> bullish FVG: c0.high=101 < c2.low=103
        _bar(103, 104, 102.5, 103),  # 3  prevents new FVG (c1.high=100.5 >= c3.low=102.5? no, 100.5 < 102.5 -> FVG. avoid.)
    ]
    # Actually: c1.high=100.5 vs c3.low=102.5 -> 100.5 < 102.5 -> creates a 2nd bullish FVG.
    # Build differently: pull c1.high up so no second FVG.
    rows = [
        _bar(100, 101, 99, 100),       # 0
        _bar(100, 103, 99.5, 100),     # 1 -- high=103 high enough that c1.high >= c3.low
        _bar(101, 105, 103, 104),      # 2 -- bullish FVG c0.high=101 < c2.low=103
        _bar(103.5, 104, 103, 103.5),  # 3 -- c1.high=103 vs c3.low=103, no strict gap
    ]
    df = _df(rows)
    fvg = find_recent_fvg(df, kind="bullish", max_age=10,
                          min_size_pct=0.005, max_size_pct=0.05)
    assert fvg is not None
    assert fvg.kind == "bullish"
    assert fvg.bottom == 101
    assert fvg.top == 103


def test_find_recent_fvg_returns_none_when_too_small():
    rows = [
        _bar(100, 101, 99, 100),
        _bar(100, 102, 100, 101),
        _bar(101, 105, 103, 104),  # bullish FVG
        _bar(104, 106, 103, 105),
    ]
    df = _df(rows)
    # Min size 5% rules out a 2% FVG
    assert find_recent_fvg(df, kind="bullish", max_age=10,
                           min_size_pct=0.05, max_size_pct=0.10) is None


def test_find_recent_fvg_skips_already_inverted():
    rows = [
        _bar(100, 101, 99, 100),
        _bar(100, 102, 100, 101),
        _bar(101, 105, 103, 104),  # bullish FVG bottom=101 top=103
        _bar(104, 105, 100, 100.5),  # close 100.5 < bottom -> already inverted
        _bar(100.5, 101, 100, 100),
        _bar(100, 100.5, 99.5, 100),
    ]
    df = _df(rows)
    assert find_recent_fvg(df, kind="bullish", max_age=10,
                           min_size_pct=0.005, max_size_pct=0.05) is None


def test_detect_recent_liquidity_sweep_walks_back():
    rows = [_bar(100, 101, 99, 100) for _ in range(5)]
    rows.append(_bar(100, 100.5, 94.0, 99.0))  # idx 5: bullish sweep below 95
    rows.append(_bar(99, 100, 98.5, 99.5))     # idx 6: no sweep
    df = _df(rows)
    swings = [Swing(idx=2, ts=df.index[2], price=95.0, kind="low")]
    res = detect_recent_liquidity_sweep(df, swings, lookback=10)
    assert res is not None
    assert res["kind"] == "bullish"
    assert res["bar_idx"] == 5


def test_detect_recent_liquidity_sweep_returns_none_when_outside_lookback():
    rows = [_bar(100, 101, 99, 100) for _ in range(20)]
    rows[3] = _bar(100, 100.5, 94.0, 99.0)  # sweep at idx 3
    df = _df(rows)
    swings = [Swing(idx=2, ts=df.index[2], price=95.0, kind="low")]
    # lookback=5 means we only look at last 5 bars (15-19); sweep at 3 is outside
    res = detect_recent_liquidity_sweep(df, swings, lookback=5)
    assert res is None


def test_find_dol_long_picks_nearest_qualifying_swing():
    swings = [
        Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=120, kind="high"),
        Swing(idx=1, ts=pd.Timestamp("2026-01-01"), price=110, kind="high"),
        Swing(idx=2, ts=pd.Timestamp("2026-01-01"), price=130, kind="high"),
    ]
    # entry=100, min_distance=5 -> 110, 120, 130 all qualify, nearest is 110
    assert find_dol(swings, side="long", entry=100, min_distance=5) == 110


def test_find_dol_long_returns_none_when_nothing_close_enough():
    swings = [
        Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=102, kind="high"),
    ]
    # entry=100, min_distance=5 -> 102 does not qualify
    assert find_dol(swings, side="long", entry=100, min_distance=5) is None


def test_find_dol_long_uses_equal_highs_when_clustered():
    # Two highs within 0.1% of each other: 110.0 and 110.05
    swings = [
        Swing(idx=0, ts=pd.Timestamp("2026-01-01"), price=110.0, kind="high"),
        Swing(idx=1, ts=pd.Timestamp("2026-01-01"), price=110.05, kind="high"),
        Swing(idx=2, ts=pd.Timestamp("2026-01-01"), price=120.0, kind="high"),
    ]
    dol = find_dol(swings, side="long", entry=100, min_distance=5)
    assert dol == pytest.approx(110.025, rel=0.001)


def test_find_freshly_inverted_fvg_long():
    rows = [
        _bar(100, 101, 99, 100),     # 0
        _bar(100, 102, 100, 101),    # 1
        _bar(98, 99, 96, 96.5),      # 2 -> bearish FVG: c0.low=99 > c2.high=99? no, want c0.low > c2.high so..
    ]
    # Build a clean bearish FVG: c[i-2].low > c[i].high
    # Use c0.low=99, c2.high=96 -> bearish FVG top=99 bottom=96 (3% gap from ~97)
    rows = [
        _bar(99.5, 100, 99, 99.5),     # 0  c1
        _bar(99, 99.5, 96.5, 97),      # 1  c2 (middle)
        _bar(97, 96.5, 95, 95.5),      # 2  -- creates bearish FVG: c0.low=99 > c2.high=96.5
        _bar(95.5, 96, 94, 94.5),      # 3 (price below FVG, FVG still active)
        _bar(94.5, 100, 94, 99.5),     # 4 (close 99.5 < fvg.top 99? no it's > 99; but we need bullish IFVG)
    ]
    df = _df(rows)
    # last bar (idx 4) closes at 99.5, which is > fvg.top=99 -> fresh bullish IFVG
    fvg = find_freshly_inverted_fvg(df, side="long", max_age=10,
                                     min_size_pct=0.005, max_size_pct=0.05)
    assert fvg is not None
    assert fvg.kind == "bearish"


def test_find_freshly_inverted_fvg_returns_none_if_no_fresh_inversion():
    rows = [_bar(100, 101, 99, 100) for _ in range(10)]
    df = _df(rows)
    assert find_freshly_inverted_fvg(df, side="long", max_age=10,
                                      min_size_pct=0.001, max_size_pct=0.05) is None
