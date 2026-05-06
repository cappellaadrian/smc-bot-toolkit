"""
Unit tests for SMC pattern detectors. Pure synthetic OHLCV, no network.
"""
import pandas as pd
import pytest

from bot.detectors import (
    find_swings,
    market_structure,
    detect_liquidity_sweep,
    find_order_block,
    find_fvgs_in_window,
    in_discount,
    in_premium,
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
    (95, 90, 100, True),    # below midpoint
    (100, 90, 110, False),  # at midpoint -> not strictly less
    (102, 90, 110, False),  # above midpoint
])
def test_in_discount(price, low, high, expected):
    assert in_discount(price, range_high=high, range_low=low) is expected


@pytest.mark.parametrize("price,low,high,expected", [
    (105, 90, 100, True),
    (100, 90, 110, False),
    (95, 90, 110, False),
])
def test_in_premium(price, low, high, expected):
    assert in_premium(price, range_high=high, range_low=low) is expected
