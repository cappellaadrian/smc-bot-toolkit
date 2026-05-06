# CLAUDE.md — Working Notes for Claude Code

## What this project is

A live execution wrapper around an SMC strategy distilled from a corpus of trader transcripts. The goal is **paper trading on BingX**, not live money. The strategy in v1 implements **Setup A (IFVG entry)** from the blended methodology in `docs/daniel_ramirez_bot_strategy.md`, derived from 1775 video transcripts of dodgysdd, ICT, and Daniel Ramirez. On a 1-year BTC/ETH 4h backtest the spec produces ~2 trades per year per symbol — the strict bias + premium/discount + IFVG + sweep + DOL filters are designed for 5M futures execution and are very restrictive on 4h crypto. Treat the result as infrastructure exercise, not alpha.

**DO NOT remove the paper-trading guards. DO NOT add live-trading code paths without an explicit instruction from Adrian.**

## Architecture

```
src/
  config.py           — env loading, secrets, runtime config
  data_feed.py        — BingX websocket client, OHLCV stream
  strategy.py         — port of the backtest strategy (uses detectors.py)
  detectors.py        — copied verbatim from /backtest, do not modify
  engine.py           — main loop, ties feed -> strategy -> broker
  state.py            — Supabase client, persistence layer
  risk.py             — daily loss limit, position cap, kill switch
  alerts.py           — Telegram notifications
  paper_broker.py     — in-memory paper trading broker (DEFAULT). Order/exit
                        logic lives here behind the Broker Protocol; there is
                        no separate execution.py layer.
  live_broker.py      — ccxt BingX wrapper (BLOCKED unless explicitly enabled)

tests/
  test_detectors.py
  test_strategy.py
  test_paper_broker.py
  test_risk.py

docs/
  SETUP.md            — getting it running
  RUNBOOK.md          — operational procedures
  STRATEGY.md         — what the bot trades and why
```

## Stack

- Python 3.11+
- `ccxt` for exchange abstraction (live, when enabled)
- `websockets` for BingX market data
- `supabase` Python client for state persistence
- `python-telegram-bot` for alerts
- `pytest` for tests
- `pydantic` for config validation
- `loguru` for structured logging

## Critical rules for Claude Code

1. **Paper trading is the default.** `BROKER=paper` in env. Live broker raises `NotImplementedError` unless `LIVE_TRADING_EXPLICITLY_ENABLED=yes_i_understand_the_risks` is set in env.
2. **Never push secrets.** Use `.env` (gitignored). Provide `.env.example` with placeholders.
3. **Every order goes through `risk.check_order()` before submission.** No exceptions.
4. **Every state mutation logs to Supabase.** No silent in-memory state for production runs.
5. **Telegram alert on every trade open AND close, plus any error or kill-switch trip.**
6. **Daily kill-switch.** If equity drops 5% in a day, halt all new entries until manual reset.
7. **Connection-loss handling.** If websocket disconnects > 30 seconds, flatten all positions.
8. **Tests required.** New code without a test PR will not be merged. Mock the exchange in tests.
9. **No em dashes in any user-facing text.** (Adrian's standing preference.)

## Build order (do in this sequence)

1. `config.py` + `.env.example` + load tests
2. `paper_broker.py` + tests (this is the riskiest piece, get it right first)
3. `data_feed.py` against BingX REST first, websocket second
4. Port `detectors.py` verbatim from /backtest
5. `strategy.py` thin wrapper around detectors that produces signals
6. `state.py` + Supabase schema migration
7. `risk.py` + tests
8. `engine.py` main loop
9. `alerts.py`
10. `live_broker.py` LAST and BEHIND THE FLAG

## Things Claude Code should ask Adrian about, not assume

- Telegram chat ID and bot token (he has Telegram automation already, will provide)
- Supabase project URL and anon key (he has projects already, will provide)
- Which symbols to trade in paper (default to BTC-USDT, ETH-USDT)
- Initial paper equity (default $10,000)
- Whether to run on his Hostinger VPS or Mac Mini

## Things to skip for v1

- Multi-timeframe (HTF bias + LTF entry). Single 4h timeframe only.
- SMT divergence across correlated assets. Add later.
- Trailing TP3. Use TP1 partial + TP2 full only.
- Web dashboard. CLI + Telegram only.

## Definition of done for v1

- `python -m bot.engine --paper` runs continuously, ingests live BingX 4h data, fires signals through the strategy, executes against paper broker, logs to Supabase, sends Telegram alerts.
- All tests pass.
- 30-day paper run produces a trade log that can be diffed against the backtest output for the same period (sanity check that live logic matches backtest logic).

## Background context

The strategy in v1 was derived from 1775 trader video transcripts (dodgysdd, ICT, Daniel Ramirez) — see `docs/daniel_ramirez_bot_strategy.md` for the full blended methodology spec, and the sibling `~/Documents/trading-project/` workspace for the extraction pipeline (`extract_concepts.py`, `aggregate_methodology.py`, `synthesize_strategy.py`) and historical data. Setup A (IFVG entry) is encoded; Setups B and C (HTF FVG + SMT, Judas swing) are deferred. The single 4h timeframe used here is a v1 simplification of the spec's multi-timeframe model — see `docs/STRATEGY.md` and the spec for what's missing. **The point of this build is the infrastructure, not the alpha.**
