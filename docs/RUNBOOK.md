# Runbook

What to do when things break.

## Bot won't start

| Symptom | Likely cause | Fix |
|---|---|---|
| `LiveBrokerNotEnabled` | Tried to run live without explicit guard | Use `--paper` or set the magic string |
| `pydantic.ValidationError` | Bad env var (e.g. risk_per_trade out of range) | Fix `.env`, valid risk is 0 < x <= 0.05 |
| Supabase connection error | URL or key wrong | Verify in dashboard, regenerate anon key if needed |
| Telegram 401 | Token revoked | Get new token from @BotFather |

## Bot is running but not trading

The 4h timeframe means at most 6 candles per day. If the bot ran less than a few hours, no signal is expected. Check:

1. `logs/bot.log` — search for "no signal" or "order blocked"
2. Common reasons:
   - Market structure neutral (no recent HH/HL or LH/LL)
   - No liquidity sweep on the latest candle
   - Price not in the OB zone after sweep
   - Price not in discount/premium half of dealing range
3. The historical data in `feed._cache` should be growing — if not, the BingX REST polling is failing

## Bot opened a trade in the wrong direction

This is the strategy doing what it's told. The strategy was backtested and shown to lose money. Bad trades are expected. If you want fewer losing trades, change the strategy, not the bot.

## Kill switch tripped

```python
# Check why:
python -c "from bot.config import load; from bot.state import make_store; s=load(); store=make_store(s.supabase_url, s.supabase_key); print(store.client.table('kill_switch_events').select('*').order('ts', desc=True).limit(5).execute().data)"
```

To reset (do this carefully):
1. Stop the bot: `systemctl stop smc-bot`
2. Decide whether the loss is recoverable or whether to halt for the day
3. If resuming, restart the bot — it resets the daily anchor on the next UTC day boundary automatically. To force-reset within the same day, edit `risk.py` state in a Python REPL or restart with `INITIAL_EQUITY` set to current balance.

## Websocket / data feed dead

V1 uses REST polling, not websockets. If the polling is failing:

1. Check BingX status: https://bingx.com/en-us/support/status/
2. Check the proxy/network from the VPS: `curl https://open-api.bingx.com/openApi/spot/v1/server/time`
3. If the feed is broken for more than 30 minutes, the engine's connection-loss handler should flatten positions. If it doesn't, do it manually in Supabase by setting `closed_at` and `exit_price`.

## Reconciliation

Once a week, diff the trades the bot logged against the backtest's expected trades for the same window:

```bash
python scripts/reconcile.py --start 2026-05-01 --end 2026-05-07
```

Live trades should match backtest trades trade-for-trade (modulo the slippage/fee model). Any divergence is a bug.

## Emergency stop

```bash
systemctl stop smc-bot
# or, if not under systemd:
pkill -f "bot.engine"
```

Then in Supabase, manually close any open positions.
