"""
Configuration. Loads from .env, validates, exposes a single Settings object.

The live-trading guard lives here. Even if BROKER=live is set, the live broker
will refuse to instantiate unless LIVE_TRADING_EXPLICITLY_ENABLED is set to the
exact magic string. This is intentional friction.
"""
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


LIVE_TRADING_MAGIC_STRING = "yes_i_understand_the_risks"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Broker
    broker: Literal["paper", "live"] = "paper"
    live_trading_explicitly_enabled: str = ""

    # BingX (only used if broker=live AND magic string set)
    bingx_api_key: str = ""
    bingx_api_secret: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Runtime
    symbols: str = "BTC-USDT,ETH-USDT"
    timeframe: str = "4h"
    initial_equity: float = 10_000.0
    risk_per_trade: float = 0.01
    max_daily_loss_pct: float = 0.05
    max_concurrent_positions: int = 1
    log_level: str = "INFO"

    @field_validator("risk_per_trade")
    @classmethod
    def validate_risk(cls, v: float) -> float:
        if not 0 < v <= 0.05:
            raise ValueError(f"risk_per_trade must be in (0, 0.05], got {v}")
        return v

    @field_validator("max_daily_loss_pct")
    @classmethod
    def validate_dd(cls, v: float) -> float:
        if not 0 < v <= 0.20:
            raise ValueError(f"max_daily_loss_pct must be in (0, 0.20], got {v}")
        return v

    @property
    def symbols_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def live_trading_allowed(self) -> bool:
        return (
            self.broker == "live"
            and self.live_trading_explicitly_enabled == LIVE_TRADING_MAGIC_STRING
        )


def load() -> Settings:
    """Load and validate settings."""
    return Settings()
