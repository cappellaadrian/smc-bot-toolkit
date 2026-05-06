# Strategy

## Honest summary

The bot trades a deterministic encoding of ICT/SMC concepts (Smart Money Concepts) on 4h crypto candles. The same logic was backtested on 360 days of real BTC-USDT and ETH-USDT 4h data and lost between 23% and 47% of starting capital across all parameter variants.

This is not a profitable strategy. It is here so the live infrastructure has something to execute. Replace the contents of `strategy.py` with anything else and the bot will run that instead.

## The setup

A LONG trade requires, in order:

1. **Market structure** is bullish or neutral (last two swing lows are higher OR no clear bias)
2. **Liquidity sweep** below a recent swing low (wick below it, close back above)
3. **Order Block** — price is currently inside the last bearish candle before the swept-low impulse
4. **Discount filter** — price is in the lower half of the last 50 candles' range

A SHORT trade is the mirror.

## Entry, stop, target

| Parameter | Long | Short |
|---|---|---|
| Entry | Current close + 0.05% slippage | Current close - 0.05% slippage |
| Stop loss | 0.1% below the swept low | 0.1% above the swept high |
| TP1 | Entry + 1R (close 50%, move SL to BE) | Entry - 1R |
| TP2 | Next swing high above entry | Next swing low below entry |

## Position sizing

`size_usd = (equity × risk_per_trade) / (distance_to_sl / entry_price)`

Default risk: 1% of equity per trade. Capped at 10x leverage (i.e. position notional cannot exceed 10x equity).

## Where the strategy fails

From the backtest:
- **Win rate is too low** (~30%) for a 1:1 to 1:3 RR system to break even
- **TP1 hits often, TP2 rarely** — the partial-close-and-move-to-BE pattern means many trades end at breakeven instead of running to full target
- **Order Blocks are too generous** — any opposite-color candle qualifies, leading to many low-quality entries
- **No quality filter on the impulse** — small moves and large moves are treated equally
- **Discretion is missing** — human ICT traders filter setups by judgment that the rules can't capture

## Improvements that might help (but won't be done in v1)

1. Multi-timeframe — use 1d for bias, 4h for setup, 15m for entry trigger
2. Volume filter on the OB candle (require above-average volume)
3. SMT divergence as confluence (require BTC and ETH to disagree on the swept level)
4. Asymmetric position sizing — size up on higher-conviction setups
5. Time-of-day filter — only trade ICT killzones (London 06-09 UTC, NY 13-16 UTC)

If you want to pursue these, do them in the backtester first. Do not "improve" a live bot without proof on historical data.
