from bot.config import Settings, LIVE_TRADING_MAGIC_STRING


def test_default_is_paper(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    s = Settings(_env_file=None)
    assert s.broker == "paper"
    assert not s.live_trading_allowed


def test_live_blocked_without_magic_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(broker="live", live_trading_explicitly_enabled="", _env_file=None)
    assert not s.live_trading_allowed


def test_live_allowed_with_magic_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(
        broker="live",
        live_trading_explicitly_enabled=LIVE_TRADING_MAGIC_STRING,
        _env_file=None,
    )
    assert s.live_trading_allowed


def test_live_blocked_with_wrong_magic_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(
        broker="live",
        live_trading_explicitly_enabled="yes",
        _env_file=None,
    )
    assert not s.live_trading_allowed


def test_risk_per_trade_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import pytest
    with pytest.raises(ValueError):
        Settings(risk_per_trade=0.10, _env_file=None)


def test_symbols_list_parsing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(symbols="BTC-USDT, ETH-USDT,SOL-USDT", _env_file=None)
    assert s.symbols_list == ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
