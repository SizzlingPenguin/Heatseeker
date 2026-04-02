# Heatseeker — Smart Money Tracker

---

## Context for AI Assistants

This project was built iteratively. Read this section first before making any changes.

### What this tool is
A Flask web app that analyzes US ETFs, US stocks, and Swedish OMXS30 stocks for institutional footprints. It answers three questions: where are institutions forced to buy, forced to sell, and defending a price level.

### Unified hybrid algo
Both ETFs and stocks use the same core signal philosophy. The ETF algo adds COT and Max Pain as bonus institutional signals on top.

- `analyzer.py` — **ETF algo**. Core signals + COT (CFTC API) + Max Pain (options chain).
- `analyzer_stocks.py` — **Stock algo**. Core signals + Relative Strength vs benchmark + Earnings Proximity.
- Both share: ADX direction, above SMA200, delta volume, OBV, MACD.

### Scoring system — critical to understand
The scoring is **weighted and normalized**, not a raw point count. Every signal has a weight. If a signal is unavailable (e.g. COT API down, no options data), its weight is redistributed proportionally across the remaining signals. Score is 0.0–1.0, displayed as a percentage.

```
>= 80%  HOT        (running hot, may be near peak — Extended warning if >10 days)
>= 60%  BUY        (best entry tier, confirmed setup)
>= 40%  WATCH      (setup forming, monitor)
<  40%  AVOID      (signals against you)
```

### ETF signal weights
| Signal | Weight | Condition |
|--------|--------|-----------|
| COT | 0.15 | CFTC net long index > 60 |
| Relative Strength | 0.22 | Outperforming SPY (20d) |
| ADX Direction | 0.15 | +DI > -DI (bullish direction) |
| Above SMA200 | 0.15 | Price > SMA200 |
| Max Pain | 0.08 | Price within 5% of max pain |
| Delta Volume | 0.10 | Buyers dominant |
| OBV | 0.06 | Rising |
| Earnings Proximity | 0.05 | > 14 days to earnings |
| MACD | 0.04 | Bullish crossover |

COT is only available for: SPY, QQQ, GLD, SLV, TLT, USO. Other ETFs skip COT and redistribute weight.

### Stock signal weights
| Signal | Weight | Condition |
|--------|--------|-----------|
| Relative Strength | 0.28 | Outperforming benchmark (20d) |
| ADX Direction | 0.22 | +DI > -DI (bullish direction) |
| Above SMA200 | 0.20 | Price > SMA200 |
| Earnings Proximity | 0.10 | > 14 days to earnings |
| Delta Volume | 0.10 | Buyers dominant |
| OBV | 0.06 | Rising (shows magnitude: strong/moderate/weak) |
| MACD | 0.04 | Bullish crossover |

### Stock algo is tuned for growth/momentum stocks
Backtested across Mag 7 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA) over 5 years. Signal ordering is correct on US large-cap growth stocks. May be inverted on range-bound, value, or European stocks — use the Verify tab to check before trusting scores on unfamiliar tickers.

### Display-only indicators (not scored)
- RSI value + label (oversold/momentum/overbought)
- Golden Cross (SMA50/SMA200)
- Fast Cross (SMA20/SMA50)
- Fair Value Gaps
- Quarter End Risk
- Volume Profile (POC/VAH/VAL) → Entry Zone, Target, Invalidation levels

### Bottom Watch — RSI(200) gated
`compute_bottom_watch()` in `analyzer.py` is separate from the scoring engine. It does NOT affect the weighted score.

**Gate:** RSI(200) < 45 must be true (long-term oversold for months). If gate is closed, bottom watch shows "NO BOTTOM SIGNAL" regardless of other conditions.

**When gate is open, 5 signals are checked:**
| Signal | Condition |
|--------|-----------|
| RSI Recovering | RSI(14) > 50 (short-term bounce started) |
| OBV Divergence | Price lower but OBV higher (accumulation) |
| Price at VAL | Price at/below Value Area Low |
| ATR Exhaustion | Volatility contracted 20%+ from recent spike |
| VIX Extreme | VIX > 30 (market-wide fear) |

Thresholds: 3+/5 = HIGH PROBABILITY, 1+/5 = POSSIBLE, 0/5 = NO SIGNAL.

Backtested: HIGH PROBABILITY = +4.53% avg 20d return (440 trades), POSSIBLE = +3.03% (2421 trades). Correct ordering across 7 tickers over full history.

### Compounder detection
`get_compounder_pct()` in `cache.py` computes % of time a stock has been above SMA200 over its full history. Requires 20+ years of data. Cached for 24 hours. Stocks with 85%+ get a 🏆 COMPOUNDER badge on the card. These stocks are "buy and hold" quality where the algo's timing signals are less relevant.

### Star rating
Cards show stars based on signal tier + price proximity to entry zone:
- ⭐⭐⭐ BUY/HOT + price in entry zone (VAL to POC)
- ⭐⭐ BUY/HOT + price within 3% of entry zone
- ⭐ WATCH + price in entry zone
- ⭐ (silver) BUY/HOT/WATCH + price within ~5% of entry zone
- 2-3 star cards have pulsating gold borders

### Signal age
Each card shows how many consecutive days the current signal tier has been active. HOT signals with age > 10 days show "⚠ Extended" warning.

### Caching layer
`cache.py` provides in-memory caching to reduce redundant API calls:
- **OHLCV data**: 1 hour TTL (daily bars don't change intraday)
- **Earnings dates**: 24 hour TTL
- **Max Pain**: 1 hour TTL
- **COT**: 1 hour TTL (data updates weekly on Fridays)
- **Benchmark returns**: 1 hour TTL
- **Compounder %**: 24 hour TTL
- **Batch download**: `yf.download()` with multiple tickers in one call
- Refresh button clears cache for fresh data

### SSE streaming
All three analysis tabs (ETFs, US Stocks, Swedish Stocks) use Server-Sent Events. Cards appear one by one as each ticker completes analysis, sorted by score descending.

### COT implementation
COT data is fetched from the CFTC Socrata SODA API via `curl_cffi` with Chrome impersonation. Python's standard `requests` library hangs on the CFTC server due to TLS incompatibility. COT is only fetched for ETFs with known CFTC keywords (SPY, QQQ, GLD, SLV, TLT, USO).

### Frontend architecture — do not monolith
```
templates/base.html           — shell, tabs, script includes
templates/tab_home.html       — welcome page + market snapshot
templates/tab_etf.html        — ETF grid
templates/tab_us_stocks.html  — US stocks grid
templates/tab_stocks.html     — Swedish stocks grid
templates/tab_verify.html     — backtest + signal analysis
static/css/main.css           — all styles (including print CSS for PDF)
static/js/cards.js            — shared helpers: signalBadge(), bottomWatch(), trendSection(), levelsSection(), scoreBar(), exportPdf(), computeStars()
static/js/home.js             — market snapshot + export snapshot
static/js/etf.js              — renderEtfCard(), loadEtfs() via SSE
static/js/us_stocks.js        — renderUsStockCard(), loadUsStocks() via SSE
static/js/stocks.js           — renderStockCard(), loadStocks() via SSE
static/js/verify.js           — backtest runner, signal analysis, card renderer
static/snapshot/index.html    — standalone read-only snapshot template
```

When adding a new feature: edit the relevant small file only. Never rewrite base.html or main.css entirely.

### Verify tab
- **Run Backtest**: full-history walk-forward backtest on any ticker. Auto-detects ETF vs stock. Period slider (3mo to max). Shows signal distribution, forward returns (5d/10d/20d), win rates, max drawdown, signal ordering check, and bottom watch backtest.
- **Signal Analysis**: runs the live analysis (same as the tab cards) on any ticker. Auto-detects ETF vs stock algo.

### Backtest optimization
`run_verify()` precomputes all indicators (RSI, ADX, MACD, OBV, SMAs) once over the full price series, then reads values by index in the loop. Volume profile is recomputed every 20 bars. ~10x faster than recomputing on every 252-bar window. For stocks, SPY data is fetched once and aligned by date for backtestable relative strength.

### Known limitations to preserve
- Delta volume is an OHLCV approximation, not true tick delta
- COT is weekly — too slow for short-term trades
- Max Pain is only reliable in the final week before options expiry
- MACD crossover is noisy — treat as trigger only, not standalone signal
- Swedish stock volume is thinner than US — signals less reliable on small caps
- Stock algo is momentum-biased — may be inverted on range-bound/value stocks
- `curl_cffi` (yfinance dependency) is not thread-safe — all analysis runs sequentially
- Earnings proximity is almost always unavailable (yfinance calendar unreliable)

### Intended hold period
Signals are calibrated for **1–4 week medium-term swing trades** on daily bars. Not suitable for intraday or long-term (6m+) holds without modification.

---

## Tickers Covered

### US ETFs (21)
| Ticker | Sector | COT |
|--------|--------|-----|
| SPY | S&P 500 | ✅ |
| QQQ | Nasdaq 100 | ✅ |
| GLD | Gold | ✅ |
| SLV | Silver | ✅ |
| TLT | US Bonds | ✅ |
| USO | Oil | ✅ |
| XLK | Technology | — |
| XLF | Financials | — |
| XLE | Energy | — |
| XLV | Healthcare | — |
| XLI | Industrials | — |
| XLP | Consumer Staples | — |
| XLY | Consumer Discretionary | — |
| XLC | Communications | — |
| XLB | Materials | — |
| XLU | Utilities | — |
| XLRE | Real Estate | — |
| SMH | Semiconductors | — |
| XRT | Retail | — |
| IGV | Software | — |
| IBIT | Bitcoin | — |

### US Stocks (27)
Mag 7 + 20 growth/momentum stocks across tech, healthcare, financials, consumer sectors. Benchmarked against SPY.

### Swedish Stocks (29)
OMXS30 constituents. Benchmarked against ^OMX.

---

## Data Sources

| Data | Source | Cost | Update Frequency | Cache TTL |
|------|--------|------|-----------------|-----------|
| OHLCV price data | yfinance | Free | Daily | 1 hour |
| Options chain | yfinance | Free | Real-time | 1 hour |
| COT report | CFTC SODA API | Free | Weekly (Fridays) | 1 hour |
| Earnings dates | yfinance | Free | As announced | 24 hours |
| VIX | yfinance | Free | Daily | 1 hour |

---

## Setup & Running

```bash
pip install flask yfinance pandas numpy requests
python app.py
# Open http://localhost:5000
# Or double-click start.bat
```

---

## File Structure

```
Heatseeker/
├── app.py                — Flask server, SSE streaming, all API routes
├── analyzer.py           — ETF algo (hybrid: core signals + COT + Max Pain)
├── analyzer_stocks.py    — Stock algo (core signals + RS + earnings)
├── cache.py              — OHLCV, earnings, max pain, compounder, batch download caching
├── backtest.py           — Backtest engine (ETF + stock, precomputed indicators)
├── backtest_runner.py    — Standalone CLI backtest tool (ETF only)
├── start.bat             — Windows launcher (kills old process, opens browser)
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html         — Shell, tabs, script includes
│   ├── tab_home.html     — Welcome page + market snapshot + export
│   ├── tab_etf.html      — US ETF grid
│   ├── tab_us_stocks.html — US stocks grid
│   ├── tab_stocks.html   — Swedish stocks grid
│   └── tab_verify.html   — Backtest + signal analysis
└── static/
    ├── favicon.svg       — Crosshair icon
    ├── css/
    │   └── main.css      — All styles + print CSS
    ├── js/
    │   ├── cards.js      — Shared card rendering helpers
    │   ├── home.js       — Market snapshot + export snapshot
    │   ├── etf.js        — ETF card renderer + SSE loader
    │   ├── us_stocks.js  — US stock card renderer + SSE loader
    │   ├── stocks.js     — Swedish stock card renderer + SSE loader
    │   └── verify.js     — Backtest runner + signal analysis
    └── snapshot/
        └── index.html    — Standalone read-only snapshot template
```

---

## Future Improvements

- Tune a separate mean-reversion algo for Swedish/European value stocks
- Add Max Pain for Mag 7 stocks (deep options markets)
- Add VIX as a market regime filter for the main scoring
- Email/SMS alerts on signal changes
- Score history chart per ticker
- Build standalone Windows executable (PyInstaller)
