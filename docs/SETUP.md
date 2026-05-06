# Setup

## 1. Local environment

```bash
git clone <repo>
cd smc-paper-bot
python -m venv .venv
source .venv/bin/activate     # on Mac/Linux
pip install -e ".[dev]"
```

## 2. Environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```ini
BROKER=paper                                # leave as paper for v1
INITIAL_EQUITY=10000
RISK_PER_TRADE=0.01

SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_KEY=<anon key>

TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_CHAT_ID=<get with /start to your bot, then check getUpdates>
```

To get a Telegram chat ID:
1. Create a bot through @BotFather, get the token
2. Send /start to your bot
3. Open https://api.telegram.org/bot<TOKEN>/getUpdates and find chat.id

## 3. Supabase schema

Either run the migration through Supabase CLI:

```bash
supabase db push
```

Or paste the contents of `supabase/migrations/20260506_init.sql` into the Supabase SQL Editor and run it.

## 4. Verify it runs

```bash
pytest -v                           # all tests should pass
python -m bot.engine --paper        # starts the bot in paper mode
```

You should see:
- "Bot started (paper). Symbols: BTC-USDT, ETH-USDT" in Telegram
- Logs in `logs/bot.log`
- The bot waiting for the next 4h candle close before doing anything

## 5. Deploying to the Hostinger VPS

```bash
# on VPS:
git clone <repo>
cd smc-paper-bot
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# edit .env with production values

# run under systemd (recommended) or tmux
nohup python -m bot.engine --paper > logs/stdout.log 2>&1 &
```

A systemd unit file is in `deploy/smc-bot.service` — copy to `/etc/systemd/system/` and `systemctl enable --now smc-bot`.
