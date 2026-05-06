# Blended SMC Strategy Spec

## Source

Three channels analyzed: **dodgysdd** (1,246 videos, ICT/SMC practitioner, ES/NQ futures focus), **ICT / Inner Circle Trader** (660 videos, methodology originator, forex + futures), **danielramirezcr** (190 videos, ICT/SMC + crypto, Spanish-language). Total: ~2,096 videos.

**Highest cross-channel agreement (all three channels):**
- Fair Value Gap (FVG) as the core price structure unit
- Inversion FVG (IFVG) as the primary entry trigger
- Liquidity sweep prerequisite before high-probability entries
- Premium/discount framework (longs in discount, shorts in premium)
- Kill zone time windows (London Open, NY AM) as session filters
- Draw on liquidity (DOL) / equal highs/lows as targets
- SMT divergence (correlated instrument confirmation) as optional confluence
- Asia session avoidance
- Higher-timeframe bias must precede lower-timeframe entries

**Where they differ:** ICT uses COT/seasonal data and weekly swing models (not encodable without external data feeds); Daniel adds indicator-based setups (EMA/MACD) and crypto assets; dodgysdd is the most execution-specific and provides the clearest entry/stop rules. Where parameters differ, dodgysdd's rules are preferred for the intraday execution layer; ICT's rules are preferred for the bias layer.

---

## Trade Universe

**Instruments (primary):** ES (E-mini S&P 500 futures), NQ (E-mini Nasdaq futures). Both channels with futures focus agree on this pair. MNQ used for position sizing flexibility only.

**Instruments (secondary / optional):** XAUUSD, EURUSD, BTC. Require the same rule set; enabled only if correlated-instrument SMT pairs are available (ES/NQ for futures; EURUSD/GBPUSD for forex; BTC/ETH for crypto).

**Instruments excluded from encoding:** YM, MES, altcoins (insufficient cross-channel rule agreement).

**Timeframe stack used by the encoded strategy:**

| Role | Timeframe |
|---|---|
| Bias layer | Daily, 4H |
| Setup identification | 1H, 15M |
| Entry trigger | 5M |
| Entry precision / stop | 1M |

**Canonical bar used for signal generation:** 5M (entry trigger detection); 15M (setup framing); 1M (stop placement refinement).

**Excluded:** Asia session bars from 8:00 PM – 2:00 AM ET. These bars are loaded for structure reference only (Asian Range High/Low) but generate no signals.

---

## Bias / Higher-Timeframe Context

The strategy requires a directional bias before any setup is evaluated. Bias is **BULLISH**, **BEARISH**, or **NEUTRAL** (no trade). Bias is assessed on the **Daily** and **4H** charts using the following observable rules.

### Step 1 — Daily Swing Structure

Define a **daily swing high** as any daily candle high that is higher than the two candles immediately before and after it (3-bar fractal: `high[i] > high[i-1] and high[i] > high[i+1]`; use confirmed candles only, i.e., `i` is at least two bars back).

Define a **daily swing low** symmetrically: `low[i] < low[i-1] and low[i] < low[i+1]`.

- **Daily BULLISH:** The most recent confirmed daily swing low is **higher** than the prior daily swing low, AND the most recent confirmed daily swing high is **higher** than the prior daily swing high (higher highs and higher lows).
- **Daily BEARISH:** The most recent confirmed daily swing high is **lower** than the prior daily swing high, AND the most recent confirmed daily swing low is **lower** than the prior daily swing low.
- **Daily NEUTRAL:** Neither condition is met (e.g., lower high with higher low = chop). No trades are taken during NEUTRAL.

### Step 2 — 4H Premium/Discount State

Compute the 4H **range** as: the distance from the most recent confirmed 4H swing low to the most recent confirmed 4H swing high (same 3-bar fractal, applied to 4H bars).

```
range_high = most recent confirmed 4H swing high
range_low  = most recent confirmed 4H swing low
equilibrium = (range_high + range_low) / 2
current_close = latest 4H close
```

- **Discount zone:** `current_close < equilibrium` → valid for LONG setups
- **Premium zone:** `current_close > equilibrium` → valid for SHORT setups
- **At equilibrium (`|current_close - equilibrium| / (range_high - range_low) < 0.05`):** No new entries; wait for price to reach premium or discount.

### Step 3 — Bias Assignment

| Daily Structure | 4H Position | Assigned Bias |
|---|---|---|
| BULLISH | Discount | BULLISH (long setups active) |
| BULLISH | Premium | NEUTRAL (wait for discount retracement) |
| BEARISH | Premium | BEARISH (short setups active) |
| BEARISH | Discount | NEUTRAL (wait for premium rally) |
| NEUTRAL | Any | NEUTRAL (no trades) |

### Step 4 — 4H FVG as Delivery Zone (Optional Upgrade)

If a 4H bullish FVG (see definition below) exists within the discount zone, that FVG is the **preferred delivery target** for long entries — setups that trigger from within or immediately below that FVG receive a confluence bonus. Mirror for bearish. This is ICT's "HTF FVG delivery" concept. Applies as an optional confluence in Setup A and Setup B.

---

## Setup A: Inversion FVG (IFVG) Entry

*The primary setup. All three channels agree on this as the highest-frequency, most rule-complete execution model.*

- **Direction:** Both (long in BULLISH bias, short in BEARISH bias)

### Definitions Required

**FVG (Fair Value Gap):**
A three-candle pattern on the **5M chart** where:
- **Bullish FVG:** `candle[i-2].high < candle[i].low` (gap between candle i-2's high and candle i's low; candle i-1 is the middle candle)
- **Bearish FVG:** `candle[i-2].low > candle[i].high`
- Gap size filter: `gap_size = abs(candle[i-2].high - candle[i].low)` must satisfy `10 <= gap_size <= 25` points for ES/NQ. Gaps < 10 points are too small; gaps > 25 points produce unfavorable stop sizes. *Note: dodgysdd states this explicitly; ICT does not give a point threshold — use dodgysdd's value for ES/NQ; for EURUSD use 10–25 pips; for BTC use $200–$500.*
- **Singularity filter:** Only one FVG may exist on the most recent directional leg (the leg that created this FVG). Count FVGs on the leg: if `count_fvgs_on_leg > 1`, mark as STACKED and exclude. *dodgysdd's rule; ICT does not state this explicitly.*
- **Freshness filter:** FVG must have been created within the last **10 bars** on the 5M chart (50 minutes). FVGs older than 10 bars are deprioritized. *Derived from dodgysdd's "3-4 candles" guidance, scaled to allow for typical setup development time.*

**IFVG (Inversion Fair Value Gap):**
A previously identified FVG where price has now **closed through it** in the opposing direction:
- **Bullish IFVG (entry signal for LONG):** A bearish FVG (`candle[i-2].low > candle[i].high`) where price subsequently closes **above** `candle[i-2].low` (the upper boundary of the bearish gap). The FVG has been violated upward; it now acts as support.
- **Bearish IFVG (entry signal for SHORT):** A bullish FVG (`candle[i-2].high < candle[i].low`) where price subsequently closes **below** `candle[i].low` (the lower boundary of the bullish gap). The FVG has been violated downward; it now acts as resistance.
- **Trigger candle:** The candle whose **close** crosses the FVG boundary. Entry is taken at the **close** of this candle, not at the open or during the candle. *All three channels agree: wait for the close.*

### Trigger

1. Bias is **BULLISH** (for long) or **BEARISH** (for short) per the bias rules above.
2. A valid FVG (singular, fresh, correct size) exists on the 5M chart, aligned with the opposing direction (bearish FVG for a bullish setup; bullish FVG for a bearish setup).
3. A liquidity sweep has occurred: price has traded **below** the most recent 5M swing low (for longs) or **above** the most recent 5M swing high (for shorts) within the last **20 bars** on the 5M chart, then reversed. The sweep candle must close **back inside** the range (not close beyond the swept level). *This is the V-shape requirement. Operationalized as: the candle that swept the level closes in the opposite direction — i.e., for a sweep of a low, the sweep candle closes above its open (bullish close after sweeping below the swing low).*
4. After the sweep, a 5M candle closes through the FVG boundary (IFVG trigger).

### Entry Condition

```
entry_triggered = True  if all of the following:
    bias == BULLISH (for long) or BEARISH (for short)
    fvg_is_valid(fvg)           # singular, fresh, correct size
    liquidity_sweep_occurred()  # within last 20 bars, V-shaped
    candle.close crosses fvg_boundary  # the inversion candle has closed
    session_is_active()         # see Filters below
    dol_is_identified()         # see DOL definition below
```

**Entry price:** The **close** of the trigger candle. If the trigger candle's close is more than **50%** of the gap size away from the FVG boundary (i.e., the entry candle has already moved far into premium/discount), **wait** for a retrace back to the FVG zone (within the FVG's `[lower_boundary, upper_boundary]`) and enter there instead. *dodgysdd's "way up high" rule.*

**FVG zone for retrace entry:**
- Bullish IFVG retrace zone: `[bearish_fvg_upper - gap_size, bearish_fvg_upper]` — within the body of the inverted gap.
- Bearish IFVG retrace zone: `[bullish_fvg_lower, bullish_fvg_lower + gap_size]`.

### Stop Loss

**Primary stop:** A candle **close** beyond the IFVG in the opposite direction.
- Long: stop triggered when a 5M candle closes **below** `bearish_fvg_upper - gap_size` (below the lower boundary of the inverted bearish FVG).
- Short: stop triggered when a 5M candle closes **above** `bullish_fvg_lower + gap_size` (above the upper boundary of the inverted bullish FVG).

**Hard stop (structural):** The swing high/low created during the liquidity sweep.
- Long: `hard_stop = sweep_low - 1 tick` (one tick below the price that swept the low).
- Short: `hard_stop = sweep_high + 1 tick`.

**Effective stop:** Use `hard_stop` as the order-entry stop level. Use the `close-beyond-IFVG` condition as an intrabar exit signal that overrides the hard stop if triggered first. *This reflects dodgysdd's "soft stop" language while maintaining a firm bracket order.*

```
stop_distance = entry_price - hard_stop  (long)
stop_distance = hard_stop - entry_price  (short)
```

### Take Profit

**DOL (Draw on Liquidity) Definition:**
Before entry, a DOL must be identified. In descending priority:
1. **Equal highs/lows:** Two or more 5M (or 15M) candles whose highs (or lows) are within **2 points** of each other, separated by at least **5 bars**. These are the highest-probability DOL targets. *dodgysdd cites 3+ candles; use 2 as minimum for automation.*
2. **Data high/low:** The high or low formed by the initial spike on a news candle at 8:30 AM, 10:00 AM, or 2:00 PM ET.
3. **Previous day's high/low:** `prev_day_high` or `prev_day_low`.
4. **Prior session swing:** The London session high or low from the same trading day.

If no DOL is identifiable from the above rules, **do not enter**.

**TP1 (First partial — 50% of position):**
`TP1 = nearest DOL in the direction of trade`
Minimum TP1 distance: `2 × stop_distance` (enforces minimum 2R). If nearest DOL is less than 2R away, look for the next DOL. If no DOL at 2R or beyond exists, do not enter.

**TP2 (Runner — remaining 50% of position):**
`TP2 = next DOL beyond TP1, or the external swing target (prior day high/low, weekly high/low)`
Maximum runner target: `3 × stop_distance`. Beyond 3R, close the runner regardless. *dodgysdd: "2R max" for the full position, but runners to 3R are shown — encode as: close 50% at 2R, close remaining at 3R or next DOL.*

**Post-TP1 stop management:**
After TP1 is hit, move stop to **break-even** (entry price) for the runner.

**Break-even exception (do not move to BE if):** *dodgysdd's explicit rule from `awBzQTJ0jD8`:*
- Price has not yet moved 50% of the distance to TP2.
- Equal highs/lows (the DOL target) have not been reached.
- A BPR (Balanced Price Range — see Confluences) has formed and is holding after entry.

### Confluences (Required)

All of the following must be true for a valid Setup A signal:

1. **HTF Bias active:** `bias == BULLISH or BEARISH` (not NEUTRAL). *All three channels.*
2. **Valid FVG:** Singular, fresh (≤10 bars old), correct size (10–25 pts ES/NQ), on 5M chart. *dodgysdd + ICT.*
3. **Liquidity sweep:** Within last 20 bars on 5M, V-shaped (sweep candle closes back in opposite direction). *All three channels.*
4. **IFVG trigger:** A 5M candle close crosses the FVG boundary in bias direction. *dodgysdd + ICT.*
5. **DOL identified:** At least one qualifying DOL exists at ≥ 2R from entry. *dodgysdd + ICT.*
6. **Session active:** Entry candle falls within allowed session windows (see Filters). *All three channels.*
7. **Discount/Premium alignment:** Entry is in discount (for longs) or premium (for shorts) relative to the 4H range equilibrium. *All three channels.*

### Confluences (Optional / Boost)

Each optional confluence increases conviction. Require at least **2 of 5** for full position size; use 75% position size if fewer than 2 optional confluences are present. *dodgysdd's 75% sizing guidance.*

1. **SMT divergence:** At the sweep candle, the correlated instrument (NQ if trading ES; ES if trading NQ; ETH if trading BTC) does **not** confirm the new high/low. Operationalized: `abs(corr_instrument.swing_high - prior_high) < 2 points` while primary instrument sweeps by more than 2 points. *All three channels.*
2. **4H FVG delivery:** Entry occurs within or immediately below a 4H bullish FVG (long) or above a 4H bearish FVG (short). *ICT + dodgysdd.*
3. **Judas Swing timing:** Sweep occurs between 9:30–10:00 AM ET, and IFVG trigger occurs between 10:00–10:15 AM ET. *dodgysdd + ICT.*
4. **BPR (Balanced Price Range):** A bullish FVG and bearish FVG overlap in the same price zone at the entry area. Zone: `[max(bull_fvg_lower, bear_fvg_lower), min(bull_fvg_upper, bear_fvg_upper)]` if this intersection is non-empty. *dodgysdd.*
5. **Displacement quality:** The IFVG trigger candle's range is greater than `1.5 × ATR(14)` on the 5M chart. This operationalizes "death candle" / "textbook displacement." *All three channels describe the concept; this threshold is a derived approximation — see Open Questions.*

### Filters

**Time filters (all in ET):**

| Window | Status |
|---|---|
| 2:00 AM – 5:00 AM | ACTIVE (London Open Kill Zone) |
| 5:00 AM – 8:30 AM | INACTIVE |
| 8:30 AM – 10:15 AM | ACTIVE (NY AM Kill Zone) |
| 10:15 AM – 12:00 PM | INACTIVE (London close drift; avoid) |
| 12:00 PM – 1:30 PM | INACTIVE (lunch) |
| 1:30 PM – 3:00 PM | ACTIVE (PM session; reduced size, 75% default) |
| 3:00 PM – 4:00 PM | INACTIVE (close approach) |

**Day filters:**
- Monday–Friday only. No weekend bars.
- Friday: ACTIVE only before 12:00 PM ET. After 12:00 PM on Friday, no new entries.

**News filters:**
- FOMC announcement day: INACTIVE all day.
- CPI release day: INACTIVE from 8:00 AM to 10:30 AM ET.
- 8:30 AM news candle itself: Do not enter on the news candle. Use its high/low as DOL reference only. Entry allowed on the **second** candle after 8:30 AM.

**Asset filter:**
- Do not trade ES or NQ in isolation when the two instruments are not both available for SMT monitoring. SMT is optional, but both instruments must be loaded.

### What It Looks Like in Practice

Price on ES is in a BULLISH daily bias. During the NY AM Kill Zone, ES drops below the prior 5M swing low (liquidity sweep), the sweep candle closes bullish. A clean single bearish FVG exists at 10–20 points, formed within the last 5 bars. A 5M candle then closes above the upper boundary of that bearish FVG (IFVG trigger). Equal highs sit 25 points above — the DOL at 3.1R. Long is entered at the close of the trigger candle; stop is at the sweep low minus one tick; 50% is closed at TP1 (equal highs), stop moved to break-even, runner closed at TP2 or 3R.

### Source Agreement

**dodgysdd:** Primary source — IFVG entry is described as the core model; all execution rules (75% size, close-beyond stop, V-shape sweep, singularity filter) originate here.
**ICT:** Corroborates FVG, IFVG, liquidity sweep, DOL framework, kill zone timing. Adds 4H FVG delivery zone concept.
**danielramirezcr:** Corroborates IFVG logic, liquidity sweep prerequisite, MSS + FVG entry. Adds CE (midpoint) as retrace entry level for the runner.

---

## Setup B: HTF FVG Delivery with SMT Confirmation

*A higher-timeframe version of Setup A where the entry occurs inside a 1H or 4H FVG after an SMT divergence confirms the reversal. This is dodgysdd's "HTF Fade" and ICT's "Swing on PD Arrays" collapsed into a single intraday execution model.*

- **Direction:** Both

### Trigger

1. A **1H or 4H FVG** exists above (bearish) or below (bullish) current price.
2. Price **delivers into** that FVG — the 15M close enters the FVG zone.
3. Inside the FVG zone, a **liquidity sweep** occurs: price takes an internal equal high or equal low (formed within the FVG zone after price entered it).
4. **SMT divergence** is present at the sweep: the correlated instrument (NQ/ES pair, or BTC/ETH pair) **fails to confirm** the new high/low made during the sweep (see SMT definition in Setup A Confluences).
5. A **15M candle closes** back through the sweep point — forming a 15M MSS / IFVG on the lower timeframe.

The key distinction from Setup A: the HTF FVG is the delivery zone, and SMT divergence is **required** (not optional) here.

### Entry Condition

```
entry_triggered = True  if all of the following:
    bias == BULLISH (long) or BEARISH (short)
    htf_fvg_exists(timeframe="1H" or "4H")  # see definition
    price_delivered_into_htf_fvg()           # 15M close inside FVG zone
    internal_liquidity_swept()               # equal high/low taken inside FVG
    smt_divergence_confirmed()               # corr. instrument fails to confirm
    ltf_mss_triggered()                      # 15M candle closes back through sweep
    session_is_active()
```

**HTF FVG definition:**
Same three-candle pattern as Setup A, applied to **1H or 4H** bars. Gap size filter: no upper limit on 1H/4H FVG size (these are used as delivery zones, not stops). Lower limit: the FVG must span at least `0.5 × ATR(14)` on the 1H chart.

**"Price delivered into" definition:**
The 15M closing price is within the FVG range: `fvg_lower <= close_15m <= fvg_upper`.

**Internal equal high/low:**
Two or more 5M candle highs within 2 points of each other, OR two or more 5M candle lows within 2 points of each other, formed **after** the 15M candle entered the HTF FVG zone.

**LTF MSS:**
A 15M candle closes below the most recent 15M swing low (bearish MSS, for shorts) or above the most recent 15M swing high (bullish MSS, for longs), where the swing is defined by the 3-bar fractal applied to 15M bars.

**Entry price:**
- Immediate: close of the 15M MSS candle.
- Alternative (if candle moved too far): limit order at the 50% midpoint (Consequent Encroachment) of the FVG created by the MSS candle. *ICT CE concept; danielramirezcr explicitly encodes this.*

### Stop Loss

```
stop_long  = internal_sweep_low - 1 tick   (the low swept inside the HTF FVG)
stop_short = internal_sweep_high + 1 tick
stop_distance = abs(entry_price - stop_level)
```

The "protected high/low" created by the internal sweep is the structural anchor. *dodgysdd + ICT both reference this explicitly.*

### Take Profit

**TP1 (50% of position):** Nearest 15M equal highs/lows below (short) or above (long), at minimum `1.5 × stop_distance`.

**TP2 (runner, 50%):** Next 1H swing high/low in the direction of trade, or `3 × stop_distance`, whichever comes first.

**Post-TP1:** Move stop to break-even.

### Confluences (Required)

1. **HTF bias active** (Daily + 4H alignment as defined in Bias section).
2. **1H or 4H FVG** as delivery zone (price must be inside it at entry).
3. **SMT divergence** at the internal sweep (required, not optional).
4. **Internal liquidity sweep** inside the FVG zone.
5. **15M MSS** candle closes back through internal sweep level.
6. **Session active** (same windows as Setup A).
7. **Premium/Discount alignment** (entry in premium for shorts, discount for longs, relative to 4H range).

### Confluences (Optional / Boost)

1. **Overnight range premium/discount:** Entry at the high of the overnight range (for shorts) or low of the overnight range (for longs). Overnight range = high and low formed from 6:00 PM prior session to 8:30 AM current session. *dodgysdd: "in premium right according to the overnight range."*
2. **Kill zone alignment:** Setup triggers during London Open (2:00–5:00 AM ET) or NY AM (8:30–10:15 AM ET).
3. **Equal highs/lows as DOL:** The external target is a clean set of equal highs or lows at least 20 points away.
4. **Displacement quality:** The 15M MSS candle range > `1.5 × ATR(14)` on 15M.

### Filters

Same session and news filters as Setup A. Additionally:
- **Do not enter Setup B** if the distance from the entry price to the nearest structural stop (the sweep level) is greater than `1.5 × ATR(14)` on the 5M chart — this indicates the sweep was too large and stop risk is unfavorable.
- **Minimum HTF FVG age:** FVG must be confirmed (at least 2 bars old on the 1H chart). Do not enter into a freshly formed 1H FVG within its forming candle.

### What It Looks Like in Practice

NQ is BEARISH on the daily. The 1H chart shows a bearish FVG overhead from yesterday's selloff. In the London Kill Zone, NQ rallies into that FVG. Inside the FVG, price makes a new high that ES does not confirm (SMT). NQ then drops and the 15M candle closes below the internal swing low created during the SMT sweep. Entry is taken at that 15M candle's close; stop is one tick above the internal sweep high; TP1 is the 15M equal lows below, TP2 is the prior day's low.

### Source Agreement

**dodgysdd:** Describes this as the "FVG Delivery with Liquidity Sweep (HTF Fade)" setup; provides the overnight range premium filter and the SMT requirement.
**ICT:** Describes the equivalent as the "Bearish/Bullish Swing Trade on PD Arrays" — 4H premium array + SMT + turtle soup sweep is the core entry.
**danielramirezcr:** Describes this as the "SMT Divergence + Market Structure Change" setup; adds the 15M MSS explicit rule and the CE entry refinement.

---

## Setup C: Judas Swing / 10 AM Reversal IFVG

*Time-specific version of Setup A that triggers on the 9:30–10:00 AM false move. dodgysdd and ICT both describe this; Daniel does not cover this session pattern explicitly.*

- **Direction:** Both (fade the Judas direction)

### Trigger

1. Between **9:30 AM and 10:00 AM ET**, price makes an aggressive directional move (the Judas Swing) on 5M bars that:
   - Sweeps at least one set of equal highs or equal lows (per Setup A sweep definition), AND
   - Creates at least one valid FVG (per Setup A FVG definition) on the 5M chart during that move.
2. By **10:00 AM ET**, price has **not** established a new liquidity sweep on the opposing side — the Judas direction has no follow-through.
3. Between **10:00 AM and 10:15 AM ET**, a 5M candle closes back through the FVG created during the 9:30–10:00 AM move (IFVG trigger), in the opposite direction.

**Judas condition check at 10:00 AM:**
```
judas_is_short_sweep = price swept equal highs between 9:30–10:00
judas_is_long_sweep  = price swept equal lows between 9:30–10:00
# If NEITHER: no Judas swing identified, do not enter
# If both: conflicting signals, do not enter
```

### Entry Condition

```
entry_triggered = True  if all of the following:
    judas_sweep_identified()         # sweep of eq highs or lows, 9:30–10:00 ET
    no_opposing_sweep_by_10am()      # no follow-through on Judas direction
    time >= 10:00 and time <= 10:15  # entry window
    ifvg_triggered()                 # 5M candle close through Judas FVG
    bias_not_neutral()               # daily bias must not be NEUTRAL
    dol_identified()                 # opposing swing target visible
```

Note: Setup C does **not** require bias alignment as strictly as Setup A/B. If the Judas sweep and IFVG are present with a visible DOL, the trade is valid even if the 4H premium/discount alignment is neutral — the 10 AM reversal is a time-model, not purely a bias-following model. However, **if daily bias opposes the fade direction, reduce position size to 50%**. *dodgysdd's "probably not going to get a reversal" rule is encoded as a strict 10:00 AM cutoff.*

### Stop Loss

```
stop_long  = low of the Judas sweep candle - 1 tick
stop_short = high of the Judas sweep candle + 1 tick
```

### Take Profit

**TP1:** Previous day's high (for short fades) or previous day's low (for long fades), or nearest equal highs/lows in the fade direction, at minimum `2 × stop_distance`.

**TP2:** Next significant DOL (weekly high/low, data high/low from 8:30 AM wick), at `3 × stop_distance` maximum.

**Post-TP1:** Move stop to break-even.

**Hard cutoff:** If TP1 is not hit by **12:00 PM ET**, close the position at market. *dodgysdd: "we're probably not going to get a reversal the rest of the day."*

### Confluences (Required)

1. Judas sweep confirmed between 9:30–10:00 AM ET.
2. No opposing-side sweep by 10:00 AM.
3. IFVG trigger candle between 10:00–10:15 AM ET.
4. DOL identified in the fade direction.
5. FVG on the Judas leg is singular (not stacked).

### Confluences (Optional / Boost)

1. SMT divergence at the Judas sweep high/low.
2. 4H candle open at 10:00 AM (the 4H bar boundary at 10:00 is noted by dodgysdd as a timing confluence).
3. Displacement quality: IFVG trigger candle > `1.5 × ATR(14)`.
4. Daily bias confirms the fade direction.

### Filters

- Only active **Monday–Thursday**. On Friday, this setup is not taken (TGIF caution).
- FOMC and CPI: inactive per Setup A news filters.
- Do not take Setup C if a Setup A or Setup B signal has already been taken in the same session (max 1 trade per session rule; see Risk Parameters).

### What It Looks Like in Practice

At 9:35 AM, NQ spikes up and sweeps the previous day's high (equal highs on the 5M), creating a single bearish FVG during the spike. NQ then stalls. By 10:00 AM, no sell-side sweep has occurred. At 10:03 AM, a 5M candle closes back below the lower boundary of the 9:35 AM bullish FVG (IFVG trigger). Short entered at the candle close; stop above the 9:35 AM spike high; TP1 at the prior day's low.

### Source Agreement

**dodgysdd:** Primary source — describes this as a dedicated setup; provides the 10:00 AM cutoff rule, the "no reversal after 10:00" filter, and the Judas swing name.
**ICT:** Describes the equivalent as the "Judas Swing into Inversion FVG" (London version) and references the NY open version; provides the IFVG entry mechanics.
**danielramirezcr:** Does not explicitly describe the 10 AM version. Not a source for this setup's parameters.

---

## Risk Parameters

### Risk Per Trade

**Standard (≥ 2 optional confluences):** `1% of account equity`

**Reduced (< 2 optional confluences, or PM session, or opposing daily bias in Setup C):** `0.75% of account equity`

**Position size formula:**
```python
risk_amount = account_equity * risk_pct          # e.g. 0.01 * 50000 = $500
stop_distance_points = abs(entry - stop)
point_value = 50  # ES = $50/point; NQ = $20/point; adjust per instrument
contracts = floor(risk_amount / (stop_distance_points * point_value))
contracts = max(contracts, 1)  # minimum 1 contract
```

*For MNQ: point_value = 2. For EURUSD: point_value = 10 (per pip, standard lot). Adjust accordingly.*

### Max Concurrent Positions

**1 position per instrument.** ES and NQ can be held simultaneously only if they are not both on the same side for SMT purposes (i.e., do not hold correlated longs on ES and NQ simultaneously — this eliminates the SMT signal). In practice: **1 active trade total across the ES/NQ pair.**

BTC/ETH pair: same rule. 1 active trade total.

Forex: 1 active trade per correlated pair group (EURUSD + GBPUSD count as 1 group).

### Max Daily Loss

**3% of account equity.** After 3% drawdown in a single session, all setup detection is suspended until the next trading day.

```python
daily_loss_limit = account_equity * 0.03
if daily_realized_loss >= daily_loss_limit:
    suspend_signals = True
```

### Max Trades Per Session

**2 per trading session** (London OR NY AM, counted separately). A stopped-out trade counts as 1. A trade that hits TP1 and has a runner still open counts as 1 until the runner closes.

### Re-entry Rule

If a trade is stopped out and the setup re-triggers (same direction, same session), a **re-entry is permitted once** at **50% of the standard position size**. A second re-entry is not permitted in the same session. *ICT's 50% re-entry rule from the swing model, adapted for intraday.*

### Break-Even Rule Summary

| Condition | Action |
|---|---|
| TP1 hit | Move stop to entry price (break-even) |
| Price < 50% to TP1 | Do NOT move to break-even |
| BPR holding and DOL not yet hit | Do NOT move to break-even |
| New MSS formed after entry confirming direction | Do NOT move to break-even |
| Post-TP1, runner only | Trail stop to below each successive higher low (long) or above successive lower high (short) on 5M |

---

## Pseudocode Signature

```python
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

class Direction(Enum):
    LONG = "long"
    SHORT = "short"

class Bias(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

class SetupType(Enum):
    A_IFVG = "Setup_A_IFVG"
    B_HTF_FVG_SMT = "Setup_B_HTF_FVG_SMT"
    C_JUDAS_10AM = "Setup_C_Judas_10AM"

@dataclass
class FVG:
    upper: float          # upper boundary of the gap
    lower: float          # lower boundary of the gap
    midpoint: float       # consequent encroachment = (upper + lower) / 2
    direction: str        # "bullish" or "bearish"
    bar_index: int        # bar index when FVG was created
    timeframe: str        # "5M", "15M", "1H", "4H"
    is_singular: bool     # only one FVG on forming leg

@dataclass
class Signal:
    setup_type: SetupType
    direction: Direction
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    position_size_pct: float   # 0.75 or 1.0
    optional_confluences_hit: int
    dol_target: float
    timestamp: str

def compute_bias(daily_bars, h4_bars) -> Bias:
    """
    Returns BULLISH, BEARISH, or NEUTRAL.
    Uses 3-bar fractal swing detection on daily and 4H bars.
    Checks: higher highs + higher lows (BULLISH), lower highs + lower lows (BEARISH).
    Also checks 4H premium/discount; returns NEUTRAL if price at equilibrium
    or if daily structure is mixed.
    """
    daily_bias = _get_daily_structure(daily_bars)   # "up", "down", or "mixed"
    h4_state   = _get_h4_premium_discount(h4_bars)  # "premium", "discount", "neutral"

    if daily_bias == "up" and h4_state == "discount":
        return Bias.BULLISH
    elif daily_bias == "down" and h4_state == "premium":
        return Bias.BEARISH
    else:
        return Bias.NEUTRAL

def detect_fvgs(bars, timeframe: str, max_age_bars: int = 10,
                min_size: float = 10.0, max_size: float = 25.0) -> List[FVG]:
    """
    Scans bars for valid FVGs.
    Bullish FVG: bars[i-2].high < bars[i].low
    Bearish FVG: bars[i-2].low  > bars[i].high
    Applies singularity filter: only one FVG per directional leg.
    Applies size filter: min_size <= gap_size <= max_size.
    Applies freshness filter: formed within last max_age_bars.
    """
    fvgs = []
    for i in range(2, len(bars)):
        gap_bull = bars[i].low - bars[i-2].high
        gap_bear = bars[i-2].low - bars[i].high
        age = len(bars) - 1 - i
        if age > max_age_bars:
            continue
        if gap_bull > 0 and min_size <= gap_bull <= max_size:
            singular = _check_singularity(bars, i, "bullish")
            fvgs.append(FVG(upper=bars[i].low, lower=bars[i-2].high,
                            midpoint=(bars[i].low + bars[i-2].high) / 2,
                            direction="bullish", bar_index=i,
                            timeframe=timeframe, is_singular=singular))
        if gap_bear > 0 and min_size <= gap_bear <= max_size:
            singular = _check_singularity(bars, i, "bearish")
            fvgs.append(FVG(upper=bars[i-2].low, lower=bars[i].high,
                            midpoint=(bars[i-2].low + bars[i].high) / 2,
                            direction="bearish", bar_index=i,
                            timeframe=timeframe, is_singular=singular))
    return fvgs

def detect_ifvg_trigger(bars, fvg: FVG) -> bool:
    """
    Returns True if the latest closed bar has crossed the FVG boundary,
    inverting it.
    Bullish IFVG (fade of bearish FVG): latest bar close > fvg.upper
    Bearish IFVG (fade of bullish FVG): latest bar close < fvg.lower
    """
    latest = bars[-1]
    if fvg.direction == "bearish":
        return latest.close > fvg.upper   # price closed above bearish FVG = bullish IFVG
    elif fvg.direction == "bullish":
        return latest.close < fvg.lower  # price closed below bullish FVG = bearish IFVG
    return False

def detect_liquidity_sweep(bars, lookback: int = 20,
                            tolerance: float = 2.0) -> Optional[dict]:
    """
    Scans last `lookback` bars for a V-shaped liquidity sweep.
    A sweep is: price trades below a swing low (or above swing high),
    then the sweep candle closes BACK above/below in the opposite direction.
    Returns dict with {"type": "low_sweep"/"high_sweep", "level": price, "bar_index": i}
    or None.
    """
    swing_lows  = _get_swing_lows(bars, lookback, fractal_n=3)
    swing_highs = _get_swing_highs(bars, lookback, fractal_n=3)
    for bar in reversed(bars[-lookback:]):
        for sw_low in swing_lows:
            if bar.low < sw_low - tolerance and bar.close > sw_low:
                return {"type": "low_sweep", "level": bar.low, "bar_index": bar.index}
        for sw_high in swing_highs:
            if bar.high > sw_high + tolerance and bar.close < sw_high:
                return {"type": "high_sweep", "level": bar.high, "bar_index": bar.index}
    return None

def detect_equal_highs_lows(bars, tolerance: float = 2.0,
                              min_separation: int = 5) -> Optional[float]:
    """
    Returns price level of equal highs or lows if found.
    Equal highs: 2+ bars with highs within `tolerance` points, separated by >= min_separation bars.
    Equal lows: same for lows.
    Returns the level (float) or None if none found.
    """
    highs = [(i, b.high) for i, b in enumerate(bars)]
    lows  = [(i, b.low)  for i, b in enumerate(bars)]
    for i, (idx1, h1) in enumerate(highs):
        for idx2, h2 in highs[i+1:]:
            if abs(h1 - h2) <= tolerance and abs(idx2 - idx1) >= min_separation:
                return (h1 + h2) / 2
    for i, (idx1, l1) in enumerate(lows):
        for idx2, l2 in lows[i+1:]:
            if abs(l1 - l2) <= tolerance and abs(idx2 - idx1) >= min_separation:
                return (l1 + l2) / 2
    return None

def check_smt_divergence(primary_bars, corr_bars,
                          tolerance: float = 2.0) -> bool:
    """
    Returns True if SMT divergence present at the most recent swing.
    Primary instrument makes new high/low; correlated instrument does not.
    Uses 3-bar fractal on both bar sets.
    """
    prim_high = _get_recent_swing_high(primary_bars)
    corr_high = _get_recent_swing_high(corr_bars)
    prim_low  = _get_recent_swing_low(primary_bars)
    corr_low  = _get_recent_swing_low(corr_bars)

    # Bearish SMT: primary sweeps high, correlated does not
    if prim_high is not None and corr_high is not None:
        if prim_high > corr_high + tolerance:
            return True
    # Bullish SMT: primary sweeps low, correlated does not
    if prim_low is not None and corr_low is not None:
        if prim_low < corr_low - tolerance:
            return True
    return False

def session_is_active(timestamp) -> bool:
    """
    Returns True if timestamp falls within allowed kill zones.
    Kill zones (ET):
      London: 02:00 – 05:00
      NY AM:  08:30 – 10:15
      PM:     13:30 – 15:00  (reduced size flag also set)
    Excludes: Asia (20:00-02:00), lunch (12:00-13:30), close (15:00-16:00).
    Also excludes: FOMC days, CPI day 08:00-10:30.
    """
    hour, minute = timestamp.hour, timestamp.minute
    t = hour * 60 + minute
    london_open  = (2*60 <= t < 5*60)
    ny_am        = (8*60+30 <= t < 10*60+15)
    pm_session   = (13*60+30 <= t < 15*60)
    return london_open or ny_am or pm_session

def identify_dol(bars, direction: Direction,
                 entry_price: float,
                 min_rr: float = 2.0,
                 stop_distance: float = 0.0) -> Optional[float]:
    """
    Identifies Draw on Liquidity as the nearest qualifying target in `direction`.
    Priority: equal highs/lows > data high/low > prev day high/low > session swing.
    Returns price level if found at distance >= min_rr * stop_distance, else None.
    """
    min_distance = min_rr * stop_distance
    candidates = []
    eq_level = detect_equal_highs_lows(bars)
    if eq_level:
        candidates.append(eq_level)
    # Add prev day high/low (requires daily bars or pre-computed value)
    candidates.append(_get_prev_day_high(bars) if direction == Direction.SHORT else
                      _get_prev_day_low(bars))
    for level in sorted(candidates,
                         key=lambda x: abs(x - entry_price)):
        if x is None:
            continue
        dist = abs(level - entry_price)
        if dist >= min_distance:
            if direction == Direction.LONG and level > entry_price:
                return level
            if direction == Direction.SHORT and level < entry_price:
                return level
    return None

def generate_signal(df_5m, df_15m, df_1h, df_4h, df_daily,
                    df_corr_5m,  # correlated instrument bars (NQ if primary is ES)
                    account_equity: float,
                    current_time,
                    news_calendar: List[str]  # list of active news filters
                    ) -> Optional[Signal]:
    """
    Main signal generator. Evaluates setups A, B, C in order of priority.
    Returns the first valid Signal or None.

    df_5m, df_15m etc. are DataFrames with