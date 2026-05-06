# Paper-Trade Setup Checklist

What to do before launching a 30-day paper run. ~20 minutes of one-time configuration.

## 1. Supabase project

Free tier is fine; we only write a few rows per day.

1. Go to https://supabase.com/dashboard, sign up if needed
2. **New project** → name it "smc-paper-bot"
3. Pick a strong database password (you won't need it for this bot — we use the anon key)
4. Wait for the project to provision (~2 minutes)
5. **SQL Editor** → paste the contents of `supabase/migrations/20260506_init.sql` → **Run**
6. **Project Settings → API** → copy:
   - **Project URL** (looks like `https://xxxxx.supabase.co`) → put in `.env` as `SUPABASE_URL`
   - **anon public key** → put in `.env` as `SUPABASE_KEY`

## 2. Telegram bot

1. Open Telegram, find **@BotFather**
2. `/newbot` → pick a name (anything) and a username ending in `bot`
3. BotFather replies with a token like `123456:ABC-DEF...` → put in `.env` as `TELEGRAM_BOT_TOKEN`
4. **Important:** message your new bot at least once so it knows you exist. Send `/start`
5. Get your chat ID:
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python -m json.tool
   ```
   Look for `"chat":{"id": NNNN, ...` — that's your chat ID. Put in `.env` as `TELEGRAM_CHAT_ID`

## 3. Verify connectivity

```bash
cd /Users/adriancappella/Documents/trading-project/live_bot
source .venv/bin/activate
python -c "
from bot.config import load
from bot.alerts import TelegramAlerter
from bot.state import make_store
import asyncio
s = load()
print('Supabase URL:', s.supabase_url[:40] if s.supabase_url else 'NOT SET')
print('Telegram token:', 'SET' if s.telegram_bot_token else 'NOT SET')
store = make_store(s.supabase_url, s.supabase_key)
print('Store:', type(store).__name__)
alerter = TelegramAlerter(s.telegram_bot_token, s.telegram_chat_id)
asyncio.run(alerter.send('SMC bot connectivity test — you should see this in Telegram.'))
print('Sent test message; check your bot chat.')
"
```

If you see the test message in Telegram and `Store: SupabaseStateStore`, you're good.

## 4. Run paper-trading

Foreground (for your first run):

```bash
python -m bot.engine --paper
```

Expected output:
- `=== SMC bot starting === broker=paper paper=True`
- `Bot started (paper). Symbols: BTC-USDT, ETH-USDT` in Telegram
- `warming up BTC-USDT 4h...` and `warming up ETH-USDT 4h...`
- Then idle, waiting for the next 4h candle close (every 04:00, 08:00, 12:00, 16:00, 20:00, 00:00 UTC)

Ctrl-C to stop. Positions and equity snapshots are persisted, so you can resume later.

## 5. Background run (optional)

On your Mac:

```bash
nohup python -m bot.engine --paper > logs/stdout.log 2>&1 &
echo $! > .bot.pid
```

To stop: `kill $(cat .bot.pid)`

On a Linux VPS, use the included systemd unit:

```bash
sudo cp deploy/smc-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smc-bot
journalctl -u smc-bot -f
```

## 6. Watch the dashboard

```bash
pip install -e ".[dashboard]"   # one-time, adds streamlit + altair
streamlit run scripts/dashboard.py
```

Opens at http://localhost:8501. Auto-refreshes every 30 seconds with new equity/trade data.

## 7. Reconcile weekly

```bash
python scripts/reconcile.py --start 2026-05-01 --end 2026-05-07
```

Prints a per-symbol summary of the week's trades.

## What "good" looks like for v1

- 30 days of continuous uptime (no crash loops)
- 5 to 50 closed trades across both symbols (4h IFVG triggers are sparse)
- Telegram messages on every open and close
- Supabase rows match Telegram messages (no silent state)
- Dashboard equity curve is a recognizable line, not a spike or drop to zero

If you see a runaway loss, the kill switch trips at -5% intraday and halts new entries. That's expected behavior.

## What "bad" looks like

- Silent entries (Telegram shows OPEN but no row in `positions` table) → Supabase auth issue
- Bot crashes on every candle close → check `logs/bot.log` for tracebacks
- Kill switch trips repeatedly → tighten the `MAX_DAILY_LOSS_PCT` env var or reduce `RISK_PER_TRADE`
- ~~Live broker accidentally enabled~~ — guarded by config, hard to do by accident
