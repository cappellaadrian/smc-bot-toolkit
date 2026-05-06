"""
Main engine loop. Orchestrates feed -> strategy -> risk -> broker.

Run with:
  python -m bot.engine --paper
"""
import asyncio
import sys
from datetime import datetime, timezone
import click
from loguru import logger

from .config import load
from .data_feed import CandleFeed
from .strategy import generate_signal, position_size_usd, StrategyConfig
from .risk import RiskManager
from .paper_broker import PaperBroker
from .live_broker import LiveBroker
from .state import make_store
from .alerts import TelegramAlerter


async def run_engine(paper: bool = True):
    settings = load()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    logger.add("logs/bot.log", level="DEBUG", rotation="10 MB", retention="30 days")

    logger.info(f"=== SMC bot starting === broker={settings.broker} paper={paper}")
    logger.info(f"symbols={settings.symbols_list} timeframe={settings.timeframe}")

    if not paper or settings.broker == "live":
        broker = LiveBroker(settings)
    else:
        broker = PaperBroker(initial_equity=settings.initial_equity)

    risk = RiskManager(
        initial_equity=settings.initial_equity,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_positions=settings.max_concurrent_positions,
    )
    store = make_store(settings.supabase_url, settings.supabase_key)
    alerter = TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id)
    await alerter.send(f"Bot started ({settings.broker}). "
                      f"Symbols: {', '.join(settings.symbols_list)}")

    feed = CandleFeed(settings.symbols_list, settings.timeframe, history_bars=200)
    feed.warm_up()

    strat_cfg = StrategyConfig()

    try:
        async for symbol, df in feed.stream():
            risk.maybe_reset_for_new_day()

            # 1. Check exits on existing positions for this symbol
            last = df.iloc[-1]
            actions = broker.check_exits(symbol, last["high"], last["low"])
            for pos_id, action, price in actions:
                if action == "tp1":
                    await broker.partial_close(pos_id, price, fraction=0.5)
                else:
                    pos = await broker.close_position(pos_id, price, reason=action)
                    await alerter.trade_closed(symbol, pos.side, price,
                                              pos.realized_pnl_usd, action)
                    store.record_close({
                        "id": pos.id,
                        "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
                        "exit_price": pos.exit_price,
                        "outcome": pos.outcome,
                        "realized_pnl_usd": pos.realized_pnl_usd,
                    })

            # 2. Update equity and risk state
            equity = broker.equity()
            risk.update_equity(equity)
            risk.update_position_count(len(await broker.get_open_positions()))
            store.record_equity(equity, risk.state.daily_pnl_pct())

            if risk.state.kill_switch_tripped:
                continue

            # 3. Generate new signal
            signal = generate_signal(df, strat_cfg)
            if signal is None:
                continue

            size = position_size_usd(equity, signal.entry, signal.stop_loss,
                                    settings.risk_per_trade)
            allowed, reason = risk.check_order(signal.side, size)
            if not allowed:
                logger.debug(f"order blocked: {reason}")
                continue

            pos = await broker.open_position(
                symbol=symbol, side=signal.side, size_usd=size,
                entry_price=signal.entry, stop_loss=signal.stop_loss,
                tp1=signal.take_profit_1, tp2=signal.take_profit_2,
                notes=signal.notes,
            )
            await alerter.trade_opened(symbol, signal.side, pos.entry_price,
                                      signal.stop_loss, signal.take_profit_1,
                                      signal.take_profit_2, size)
            store.record_open({
                "id": pos.id,
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "size_usd": pos.size_usd,
                "stop_loss": pos.stop_loss,
                "take_profit_1": pos.take_profit_1,
                "take_profit_2": pos.take_profit_2,
                "opened_at": pos.opened_at.isoformat(),
                "notes": pos.notes,
            })

    except KeyboardInterrupt:
        logger.info("interrupted, flattening positions...")
        for pos in await broker.get_open_positions():
            last_price = pos.entry_price  # placeholder; in live use last tick
            await broker.close_position(pos.id, last_price, reason="manual")
        await alerter.send("Bot stopped.")
    except Exception as e:
        logger.exception("engine crashed")
        await alerter.error(f"Engine crashed: {e}")
        raise


@click.command()
@click.option("--paper", is_flag=True, default=True, help="Force paper trading (default)")
@click.option("--live", is_flag=True, default=False,
              help="Use live broker (requires explicit env guard)")
def main(paper: bool, live: bool):
    if live:
        paper = False
    asyncio.run(run_engine(paper=paper))


if __name__ == "__main__":
    main()
