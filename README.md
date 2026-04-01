# Heatseeker — Smart Money Tracker

---

## Context for AI Assistants

This project was built iteratively in a single chat session. Read this section first before making any changes.

### What this tool is
A Flask web app that analyzes US ETFs and Swedish OMXS30 stocks for institutional footprints. It answers three questions: where are institutions forced to buy, forced to sell, and defending a price level.

### Scoring system — critical to understand
The scoring is **weighted and normalized**, not a raw point count. Every signal has a weight (see `WEIGHTS` dict in `analyzer.py`). If a signal is unavailable (e.g. COT API down, no options data), its weight is redistributed proportionally across the remaining signals. Score is 0.0–1.0, displayed as a percentage.

```
>= 80%  STRONG BUY
>= 60%  WATCH
>= 40%  NO TRADE
<  40%  AVOID
```

### Two separate analyzers
- `analyzer.py` — ETFs. Uses COT (CFTC API) and Max Pain (options chain) as institutional signals
- `analyzer_stocks.py` — Swedish stocks. COT and Max Pain don't exist for stocks. Replaced by:
  - **Relative Strength** vs OMXS30 index (^OMX via yfinance)
  - **Earnings Proximity** — flags if earnings are within 14 days (risk flag)

### Bottom Watch — isolated layer
`compute_bottom_watch()` in `analyzer.py` is completely separate from the scoring engine. It does NOT affect the weighted score or signal output. It is appended as a standalone `bottom_watch` key in the response. It uses: RSI divergence, RSI oversold (<35), OBV divergence, ATR exhaustion, ADX weakening, price at VAL, COT extreme (<15). Thresholds: 5+/7 = HIGH PROBABILITY, 3+/7 = POSSIBLE, <3 = NONE.

### Days-since-change
All trend signals include a `days_Xd` field showing how many consecutive days the current state has been active. Computed via `days_since_cross()` helper. ADX direction uses +DI vs -DI as a vectorized proxy (avoids recomputing ADX per day).

### Frontend architecture — do not monolith
The frontend was refactored away from a single large `index.html` after it became too slow to edit. Do not merge files back together.

```
templates/base.html        — shell only, includes tabs and script tags
templates/tab_etf.html     — ETF grid HTML
templates/tab_stocks.html  — stocks grid HTML
static/css/main.css        — all styles
static/js/cards.js         — shared helpers: bottomWatch(), trendSection(), levelsSection(), scoreBar()
static/js/etf.js           — renderEtfCard(), loadEtfs()
static/js/stocks.js        — renderStockCard(), loadStocks()
```

When adding a new feature: edit the relevant small file only. Never rewrite base.html or main.css entirely.

### Backtest is a separate program
`backtest_runner.py` is a standalone CLI tool. It is NOT part of the web app. The backtest route was intentionally removed from `app.py`. Run it separately:
```bash
python backtest_runner.py
python backtest_runner.py --years 5 --csv
```
Backtest excludes COT and Max Pain (no free historical data). Weights are redistributed across the 8 available signals.

### Python environment
The machine has no standard Python install. The only Python found was inside QGIS (`C:\Program Files\QGIS 3.28.5\apps\Python39\`) which has a broken SSL module and cannot install packages. A proper Python 3.11+ install from python.org is required before the app can run.

### Known limitations to preserve
- Delta volume is an OHLCV approximation, not true tick delta
- COT is weekly — too slow for short-term trades
- Max Pain is only reliable in the final week before options expiry
- MACD crossover is noisy — treat as trigger only, not standalone signal
- Swedish stock volume is thinner than US ETFs — signals less reliable on small caps

### Intended hold period
Signals are calibrated for **1–4 week medium-term swing trades** on daily bars. Not suitable for intraday or long-term (6m+) holds without modification.

### What has NOT been built yet
- Backtesting for Swedish stocks
- Email/SMS alerts on signal changes
- Score history chart per ticker
- Open Interest per price level
- Tick-level delta volume

---
A market analysis tool that answers three core questions about institutional behavior:
- Where are institutions **forced to buy**?
- Where are institutions **forced to sell**?
- Where are they **defending** a price level?

---

## The Core Thesis

Institutions cannot hide large capital movements. Their size creates friction — a $500M position
takes days to build, leaving detectable footprints in volume, price structure, and public data.
This tool does not copy institutional tooling. It reads the footprints their size forces them to leave,
and identifies levels before retail traders catch on.

Your edge: a $500 position fills in milliseconds. A $500M position takes days. That asymmetry is
the entire basis of this system.

---

## Tickers Covered

| Ticker | Why |
|--------|-----|
| SPY    | Deepest options market, strongest max pain effect, COT data via S&P 500 futures |
| QQQ    | Nasdaq institutional flows, tech sector bellwether |
| GLD    | Gold COT is one of the most reliable institutional signals available |
| SLV    | Silver COT, high sensitivity to institutional positioning shifts |
| TLT    | Bonds move on Fed policy — highly institutional, low noise |
| USO    | Oil COT is heavily watched by institutions and commercials |

ETFs are preferred over individual stocks because:
- COT data exists for the underlying futures
- Institutional flows are cleaner and less distorted by company-specific news
- Index rebalancing is mechanical and calendar-predictable
- Max pain on SPY/QQQ is actively defended by market makers every expiry

---

## System Architecture

The tool runs two independent layers and combines them into a single score.

```
INPUT: ticker + 1 year of daily OHLCV data
            |
    ┌───────┴────────┐
    │                │
LAYER 1          LAYER 2
Institutional    Trend &
Footprint        Momentum
(0–5 pts)        (0–5 pts)
    │                │
    └───────┬────────┘
            │
    Combined Score (0–10)
            │
    Signal Output
```

---

## Layer 1: Institutional Footprint
*Answers: where are they forced to act?*

### Volume Profile — POC, VAH, VAL
- Splits the past year of price into 20 bins by close price
- Calculates total volume traded at each price level
- **POC (Point of Control):** price level with the highest traded volume = institutional cost basis zone
- **VAH (Value Area High):** upper boundary of the 70% volume zone = institutional distribution zone
- **VAL (Value Area Low):** lower boundary of the 70% volume zone = institutional accumulation zone
- Price returning to POC = institutions defending their position
- Price at VAL = forced buy zone. Price at VAH = forced sell zone.

### COT Report (Commitment of Traders)
- Source: CFTC public API (free, published weekly)
- Tracks net positioning of Non-Commercial traders (large speculators)
- Net position is normalized to a 0–100 index against recent history
- Index > 60 = bullish bias. Index < 40 = bearish bias.
- Not spoofable — this is regulatory filing data, not order book data
- Limitation: weekly cadence, too slow for short-term trades

### Fair Value Gaps (FVG)
- Detects price gaps between candle N-2 high and candle N low (bullish FVG)
- Or between candle N-2 low and candle N high (bearish FVG)
- FVGs act as price magnets — institutions often return to fill them
- Bullish FVGs below current price = forced buy zones

### Options Max Pain
- Calculates the price at which the maximum number of options contracts expire worthless
- Market makers are mechanically forced to hedge toward this price near expiry
- Most reliable in the final week before options expiration
- Source: yfinance options chain (nearest expiry)

### Quarter-End Risk Flag
- Flags the 2-week window before each quarter end (March, June, September, December)
- Institutions window-dress portfolios: sell losers, buy winners
- Distribution risk is elevated during this window
- Simple calendar logic, no data feed required

### Institutional Score Breakdown
| Signal | Condition | Points |
|--------|-----------|--------|
| COT bias | Net long positioning (index > 60) | +1 |
| Price at POC | Close within 1% of POC | +1 |
| Bullish FVG present | Unfilled bullish gap detected | +1 |
| Max pain proximity | Close within 2% of max pain | +1 |
| No quarter-end risk | Outside the 2-week distribution window | +1 |

---

## Layer 2: Trend & Momentum Confirmation
*Answers: has the move actually started?*

### ADX (Average Directional Index)
- Measures trend strength, not direction
- Calculated using Wilder's smoothing (EMA-based)
- ADX > 25 = trend has enough strength to trade
- ADX < 20 = market is ranging, smart money is not committing — skip all signals
- This is the most important filter in the trend layer

### Golden Cross (SMA 50 / SMA 200)
- SMA 50 above SMA 200 = long-term bullish structure confirmed
- Institutions use this as a baseline trend filter
- Lagging by nature — confirms trend already in progress

### Fast Cross (SMA 20 / SMA 50)
- SMA 20 above SMA 50 = medium-term momentum aligned
- Stacking this with the golden cross reduces false signals significantly

### MACD Crossover
- 12/26/9 standard settings
- Signals when MACD line crosses above signal line on the most recent candle
- Used as a momentum trigger, not a standalone signal
- Known limitation: noisy on lower timeframes, best on daily

### OBV (On-Balance Volume)
- Tracks cumulative volume in the direction of price movement
- OBV rising with price = volume confirms the move (institutional accumulation)
- Price rising + OBV flat or falling = distribution warning (institutions selling into retail buying)
- Distribution warning is flagged separately on the card

### Delta Volume
- Approximates buying vs selling pressure per candle
- Uses candle close position within the high-low range as a proxy
- Positive cumulative delta over last 5 candles = buyers in control
- Note: true delta requires tick-level data. This is an approximation using OHLCV.

### Trend Score Breakdown
| Signal | Condition | Points |
|--------|-----------|--------|
| Golden Cross | SMA 50 > SMA 200 | +1 |
| Fast Cross | SMA 20 > SMA 50 | +1 |
| ADX confirmed | ADX > 25 | +1 |
| MACD crossed | Bullish crossover on latest candle | +1 |
| OBV rising | OBV higher than 5 candles ago | +1 |

---

## Combined Scoring & Signals

```
Combined Score = Institutional Score (0–5) + Trend Score (0–5)

8–10  →  STRONG BUY   Institutions positioned + trend confirmed + momentum firing
6–7   →  WATCH        Institutional levels identified, trend not fully confirmed
4–5   →  NO TRADE     Mixed signals, layers contradict each other
0–3   →  AVOID        Institutions at forced sell zone or trend breaking down
```

---

## Key Levels Output

| Level | Source | Meaning |
|-------|--------|---------|
| Entry Zone | VAL to POC | Where institutions are likely accumulating |
| Target | VAH | Where institutions are likely distributing |
| Invalidation | 1% below VAL | Price here means the thesis is wrong, exit |

---

## How to Use This Tool

1. Run the tool at the start of your trading session
2. Focus only on tickers scoring 6 or above
3. Use the Entry Zone as your area of interest — do not chase price above POC
4. Check the COT bias and ADX together — both must agree for high-conviction trades
5. If OBV shows a distribution warning, reduce position size regardless of score
6. Respect the Invalidation level — if price closes below it, the institutional thesis is broken
7. Re-run before each session. COT updates weekly (Fridays), everything else is daily.

---

## What This Tool Does Not Do

- It does not provide buy/sell execution signals — it provides analysis zones
- It does not account for breaking news, earnings, or macro shocks
- It does not replace risk management — always define your position size before entering
- The MACD and delta volume signals are lagging/approximate — treat them as confirmation only
- COT data is weekly and reflects futures positioning, not direct ETF flows

---

## Data Sources

| Data | Source | Cost | Update Frequency |
|------|--------|------|-----------------|
| OHLCV price data | yfinance | Free | Daily |
| Options chain | yfinance | Free | Real-time |
| COT report | CFTC public API | Free | Weekly (Fridays) |

---

## Setup & Running

```bash
# Install dependencies
pip install flask yfinance pandas numpy requests

# Run the tool
python app.py

# Open in browser
http://localhost:5000
```

---

## File Structure

```
Heatseeker/
├── app.py                — Flask server, ETF + stock API routes
├── analyzer.py           — ETF indicator logic (both layers)
├── analyzer_stocks.py    — Swedish stock algo (relative strength + earnings)
├── backtest.py           — Backtest engine (imported by runner)
├── backtest_runner.py    — Standalone CLI backtest tool
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html         — Shared header, tabs, script includes
│   ├── tab_etf.html      — US ETF grid
│   └── tab_stocks.html   — Swedish stocks grid
└── static/
    ├── css/
    │   └── main.css      — All styles
    └── js/
        ├── cards.js      — Shared card rendering helpers
        ├── etf.js        — ETF card renderer + load logic
        └── stocks.js     — Stock card renderer + load logic
```

## Running the Backtest (Standalone)

```bash
python backtest_runner.py             # 3-year backtest
python backtest_runner.py --years 5   # 5-year backtest
python backtest_runner.py --csv       # save results to backtest_results.csv
```

---

## Future Improvements

- Add Open Interest data per price level (requires exchange API)
- Replace delta volume approximation with tick-level data feed
- Add backtesting module to validate score thresholds historically
- Add email/SMS alert when a ticker crosses from WATCH to STRONG BUY
- Expand to sector ETFs (XLF, XLE, XLK) once SPY/QQQ logic is validated
- Add a score history chart per ticker to track signal evolution over time
