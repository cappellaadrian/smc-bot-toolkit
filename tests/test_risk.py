from bot.risk import RiskManager


def test_check_order_allows_first_position():
    r = RiskManager(initial_equity=10_000, max_positions=1)
    allowed, reason = r.check_order("long", size_usd=500)
    assert allowed
    assert reason is None


def test_check_order_blocks_when_max_positions():
    r = RiskManager(initial_equity=10_000, max_positions=1)
    r.update_position_count(1)
    allowed, reason = r.check_order("long", size_usd=500)
    assert not allowed
    assert "max positions" in reason


def test_check_order_blocks_on_kill_switch():
    r = RiskManager(initial_equity=10_000)
    r.trip_kill_switch("test")
    allowed, reason = r.check_order("long", size_usd=500)
    assert not allowed
    assert "kill switch" in reason


def test_kill_switch_trips_on_daily_loss():
    r = RiskManager(initial_equity=10_000, max_daily_loss_pct=0.05)
    r.update_equity(9_500)  # -5%
    assert r.state.kill_switch_tripped


def test_kill_switch_does_not_trip_at_4_99_percent():
    r = RiskManager(initial_equity=10_000, max_daily_loss_pct=0.05)
    r.update_equity(9_501)
    assert not r.state.kill_switch_tripped


def test_kill_switch_sticky_across_equity_recovery():
    r = RiskManager(initial_equity=10_000, max_daily_loss_pct=0.05)
    r.update_equity(9_400)
    assert r.state.kill_switch_tripped
    r.update_equity(10_500)  # recovered, but should stay tripped
    assert r.state.kill_switch_tripped


def test_kill_switch_manual_reset():
    r = RiskManager(initial_equity=10_000)
    r.trip_kill_switch("test")
    r.reset_kill_switch()
    assert not r.state.kill_switch_tripped


def test_oversized_order_blocked():
    r = RiskManager(initial_equity=1_000)
    allowed, reason = r.check_order("long", size_usd=50_000)  # 50x equity
    assert not allowed
    assert "exceeds 20x" in reason
