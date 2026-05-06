import pytest
from bot.paper_broker import PaperBroker


@pytest.mark.asyncio
async def test_open_long_applies_slippage_and_fee():
    b = PaperBroker(initial_equity=10_000, fee_pct=0.001, slippage_pct=0.001)
    pos = await b.open_position(
        symbol="BTC-USDT", side="long", size_usd=1000,
        entry_price=100.0, stop_loss=95.0, tp1=105.0, tp2=110.0,
    )
    # entry slipped up by 0.1%
    assert abs(pos.entry_price - 100.1) < 1e-9
    # fee = 1000 * 0.001 = 1.0 deducted from cash
    assert abs(b.cash - (10_000 - 1.0)) < 1e-9


@pytest.mark.asyncio
async def test_close_long_in_profit():
    b = PaperBroker(initial_equity=10_000, fee_pct=0.0, slippage_pct=0.0)
    pos = await b.open_position("BTC-USDT", "long", 1000, 100.0, 95.0, 105.0, 110.0)
    closed = await b.close_position(pos.id, exit_price=110.0, reason="tp2")
    # 10% gain on $1000 = $100
    assert abs(closed.realized_pnl_usd - 100.0) < 1e-6
    assert closed.outcome == "tp2"
    assert b.cash == 10_100.0


@pytest.mark.asyncio
async def test_close_short_in_profit():
    b = PaperBroker(initial_equity=10_000, fee_pct=0.0, slippage_pct=0.0)
    pos = await b.open_position("BTC-USDT", "short", 1000, 100.0, 105.0, 95.0, 90.0)
    closed = await b.close_position(pos.id, 90.0, reason="tp2")
    # 10% gain on $1000 = $100
    assert abs(closed.realized_pnl_usd - 100.0) < 1e-6


@pytest.mark.asyncio
async def test_partial_close_moves_sl_to_be():
    b = PaperBroker(initial_equity=10_000, fee_pct=0.0, slippage_pct=0.0)
    pos = await b.open_position("BTC-USDT", "long", 1000, 100.0, 95.0, 105.0, 110.0)
    await b.partial_close(pos.id, 105.0, fraction=0.5)
    assert pos.partial_closed
    assert pos.stop_loss == 100.0  # moved to BE
    assert abs(pos.realized_pnl_usd - 25.0) < 1e-6  # 5% of $500


def test_check_exits_long_sl():
    import asyncio
    b = PaperBroker(initial_equity=10_000, fee_pct=0.0, slippage_pct=0.0)
    pos = asyncio.run(b.open_position("BTC-USDT", "long", 1000, 100.0, 95.0, 105.0, 110.0))
    # Bar dips to 94 (below SL)
    actions = b.check_exits("BTC-USDT", high=99.0, low=94.0)
    assert len(actions) == 1
    assert actions[0][1] == "sl"


def test_check_exits_long_tp1():
    import asyncio
    b = PaperBroker(initial_equity=10_000, fee_pct=0.0, slippage_pct=0.0)
    pos = asyncio.run(b.open_position("BTC-USDT", "long", 1000, 100.0, 95.0, 105.0, 110.0))
    actions = b.check_exits("BTC-USDT", high=106.0, low=99.0)
    assert actions[0][1] == "tp1"


def test_check_exits_skips_other_symbol():
    import asyncio
    b = PaperBroker(initial_equity=10_000)
    asyncio.run(b.open_position("BTC-USDT", "long", 1000, 100.0, 95.0, 105.0, 110.0))
    actions = b.check_exits("ETH-USDT", high=200.0, low=100.0)
    assert actions == []
