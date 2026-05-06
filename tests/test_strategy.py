"""Tests for bot.strategy.generate_signal and position_size_usd."""
import pandas as pd
import pytest

from bot.strategy import StrategyConfig, generate_signal, position_size_usd


def _flat_df(n: int, price: float = 100.0) -> pd.DataFrame:
    rows = [{"open": price, "high": price, "low": price,
             "close": price, "volume": 1.0} for _ in range(n)]
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=n, freq="4h")
    return df


def test_generate_signal_returns_none_when_df_too_short():
    df = _flat_df(10)
    assert generate_signal(df) is None


def test_generate_signal_returns_none_for_flat_data():
    """No swings, no bias, no FVGs -> no signal."""
    df = _flat_df(80)
    assert generate_signal(df) is None


def test_generate_signal_returns_none_when_bias_neutral():
    """Random oscillation that doesn't form HH+HL or LH+LL -> neutral bias."""
    rows = []
    for i in range(80):
        # Tight oscillation around 100
        c = 100 + (i % 4 - 1.5) * 0.5
        rows.append({"open": c, "high": c + 0.1, "low": c - 0.1,
                     "close": c, "volume": 1.0})
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=80, freq="4h")
    assert generate_signal(df) is None


def test_position_size_usd_basic():
    # equity 10000, risk 1%, stop 5% away from entry
    # risk_usd = 100; distance = 0.05; size = 100 / 0.05 = 2000
    size = position_size_usd(equity=10000, entry=100, stop_loss=95, risk_pct=0.01)
    assert size == pytest.approx(2000.0)


def test_position_size_usd_capped_by_max_leverage():
    # equity 10000, risk 5% with stop 0.5% away -> would need 100k notional;
    # max_leverage=10 caps at 100000. Risk_usd=500, distance=0.005 -> 100000.
    size = position_size_usd(equity=10000, entry=100, stop_loss=99.5,
                              risk_pct=0.05, max_leverage=10.0)
    assert size == pytest.approx(100000.0)


def test_position_size_usd_returns_zero_when_entry_equals_stop():
    size = position_size_usd(equity=10000, entry=100, stop_loss=100, risk_pct=0.01)
    assert size == 0.0


def test_position_size_usd_short_position():
    # Same math, stop above entry (short)
    size = position_size_usd(equity=10000, entry=100, stop_loss=105, risk_pct=0.01)
    assert size == pytest.approx(2000.0)


def test_strategy_config_defaults_are_sensible():
    cfg = StrategyConfig()
    assert cfg.min_rr < cfg.max_rr
    assert 0 < cfg.min_fvg_size_pct < cfg.max_fvg_size_pct
    assert cfg.max_fvg_age > 0
    assert cfg.sweep_lookback > 0
    assert cfg.range_window > 0
