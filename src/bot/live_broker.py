"""
Live broker stub. Intentionally raises until explicitly enabled.

To enable (DO NOT do this without thinking):
  1. Set BROKER=live in .env
  2. Set LIVE_TRADING_EXPLICITLY_ENABLED=yes_i_understand_the_risks
  3. Set BINGX_API_KEY and BINGX_API_SECRET
  4. Re-read CLAUDE.md and the backtest results
  5. Implement the methods below using ccxt
"""
from .config import Settings
from .paper_broker import Position


class LiveBrokerNotEnabled(RuntimeError):
    """Raised when someone tries to instantiate the live broker without the
    explicit guard env var set."""


class LiveBroker:
    """Real BingX execution. NOT IMPLEMENTED. Guarded behind config."""

    def __init__(self, settings: Settings):
        if not settings.live_trading_allowed:
            raise LiveBrokerNotEnabled(
                "Live trading is not enabled. Set BROKER=live AND "
                "LIVE_TRADING_EXPLICITLY_ENABLED=yes_i_understand_the_risks "
                "in your environment. Even then, do not run this until "
                "implementation is reviewed by a second person."
            )
        if not settings.bingx_api_key or not settings.bingx_api_secret:
            raise LiveBrokerNotEnabled("BINGX_API_KEY and BINGX_API_SECRET required")
        # TODO Claude Code:
        # import ccxt.async_support as ccxt
        # self.exchange = ccxt.bingx({
        #     "apiKey": settings.bingx_api_key,
        #     "secret": settings.bingx_api_secret,
        # })
        raise NotImplementedError(
            "LiveBroker is intentionally not implemented in v1. Use PaperBroker."
        )

    async def open_position(self, *args, **kwargs) -> Position:
        raise NotImplementedError

    async def close_position(self, *args, **kwargs) -> Position:
        raise NotImplementedError

    async def partial_close(self, *args, **kwargs) -> None:
        raise NotImplementedError

    async def get_open_positions(self) -> list[Position]:
        raise NotImplementedError

    def equity(self) -> float:
        raise NotImplementedError
