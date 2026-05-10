# TradingView Webhook Setup

When a TradingView alert fires, it POSTs JSON to your VPS. The webhook
runs a Claude review, inserts a row into the journal, and pings you on
Telegram.

You'll need: **TradingView Pro+** (free / Essential tiers can't fire to
webhooks).

---

## Once: configure the alert URL

Webhook URL (give the same one to every alert):

```
https://srv1183834.hstgr.cloud/tv-webhook?token=<YOUR_WEBHOOK_TOKEN>
```

The token lives in `/opt/smc-bot-toolkit/.env` on your VPS as
`WEBHOOK_TOKEN`. Anyone who has the URL with the token can post to your
journal, so don't share it.

To rotate: ssh in, edit `.env`, restart `docker compose -f /root/docker-compose.yml restart smc-webhook`.

---

## The Pine script

Paste this into TradingView (Pine Editor), modify the conditions for
your specific setups, then "Add to chart" and create alerts on it.

```pinescript
//@version=5
indicator("SMC Webhook Alerts", overlay = true)

// ---- Replace these with your actual setup detection ----
// Example: long when current bar closes above a 20-bar swing high
swingHi = ta.highest(high, 20)[1]
swingLo = ta.lowest(low, 20)[1]
longSig = ta.crossover(close, swingHi)
shortSig = ta.crossunder(close, swingLo)
// --------------------------------------------------------

// Build a JSON message TradingView will POST verbatim.
// Use {{...}} placeholders that TV substitutes at alert-fire time.
longMsg  = '{"symbol":"{{ticker}}","tf":"{{interval}}","side":"long",' +
           '"entry":{{close}},"note":"long swing breakout"}'
shortMsg = '{"symbol":"{{ticker}}","tf":"{{interval}}","side":"short",' +
           '"entry":{{close}},"note":"short swing breakdown"}'

alertcondition(longSig,  title = "SMC LONG",  message = longMsg)
alertcondition(shortSig, title = "SMC SHORT", message = shortMsg)

// Optional visual markers
plotshape(longSig,  style = shape.triangleup,   location = location.belowbar,
          color = color.green, size = size.small, title = "long")
plotshape(shortSig, style = shape.triangledown, location = location.abovebar,
          color = color.red,   size = size.small, title = "short")
```

---

## Once: create the TV alert

1. Open the Pine script on a chart, e.g. **BINANCE:BTCUSDT 4h**
2. Click the alarm-clock icon → **Create alert**
3. **Condition:** `SMC Webhook Alerts` → `SMC LONG` (or `SMC SHORT`; one alert per direction)
4. **Notifications** tab → **Webhook URL** → paste the URL above (with your real token)
5. **Message** → leave the default; the Pine script already provides it
6. **Once Per Bar Close** (so you only fire after a bar confirms)
7. Save

Repeat for SHORT, and on whatever symbols / timeframes you trade.

---

## Payload format

The webhook accepts any JSON object. Recognized fields:

| Field | Required | What it is |
|---|---|---|
| `symbol` | recommended | e.g. `BTC-USDT`, `EURUSD`, `ES1!` |
| `tf` (or `timeframe`) | recommended | e.g. `4h`, `15m` |
| `side` | recommended | `long` or `short` |
| `entry` | optional | numeric |
| `stop` | optional | numeric |
| `tp1` | optional | numeric |
| `tp2` | optional | numeric |
| `risk_pct` | optional | e.g. `1.0` |
| `note` (or `description`) | optional | freeform |

Anything else passes through as `notes` on the journal row.

---

## What happens when an alert fires

1. TV POSTs to the webhook
2. Webhook verifies the token, parses the JSON
3. Calls Claude (Haiku) with the spec to render a short verdict
4. Inserts a `reviewed_trades` row with `status=planned`, `verdict={VALID|PARTIAL|NOT|INSUFFICIENT}`
5. Sends Telegram message to your bot with the verdict
6. Returns `{"ok": true, "trade_id": "..."}` to TV

Cost: ~$0.005 per alert (Haiku 4.5 with the spec cached).

---

## Testing without TradingView

Manual curl (replace `TOKEN` with your `WEBHOOK_TOKEN`):

```bash
curl -X POST "https://srv1183834.hstgr.cloud/tv-webhook?token=TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol":"BTC-USDT",
    "tf":"4h",
    "side":"long",
    "entry":65200,
    "stop":63800,
    "tp1":67400,
    "note":"manual test from curl"
  }'
```

Within ~5s you should see:
- A response with `{"ok": true, "trade_id": "..."}`
- A row in **Trade Journal** (status=planned)
- A Telegram message in @TradingPipo19bot

---

## Health check

```
GET https://srv1183834.hstgr.cloud/tv-webhook/../health
# or directly on the container's port:
curl http://localhost:8080/health
```

Returns `{ok, spec_loaded, supabase, telegram, anthropic}`. Each should
be `true` for the webhook to do useful work.
