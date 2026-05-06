# SMC Paper Trading Bot

**Status: paper-trading only.** This bot runs an SMC (Smart Money Concepts) strategy that was backtested and shown to lose money on real data. It exists as a learning exercise for live trading infrastructure, not as a profit-generating tool.

## Quick start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SUPABASE_URL, SUPABASE_KEY

# 3. Run paper trading
python -m bot.engine --paper --symbols BTC-USDT,ETH-USDT --equity 10000

# 4. Watch logs
tail -f logs/bot.log
```

## Architecture

```
BingX websocket -> data_feed -> strategy (SMC detectors) -> risk check -> paper broker
                                                              |
                                                              v
                                                       Supabase + Telegram
```

## Documentation

- `CLAUDE.md` — instructions for Claude Code working on this repo
- `docs/SETUP.md` — environment setup
- `docs/RUNBOOK.md` — operational procedures, what to do when things break
- `docs/STRATEGY.md` — what the bot trades and why

## Honest disclosure

This strategy lost ~40% over 12 months in backtesting. Do not point this at a real funded account. Paper trading only.
