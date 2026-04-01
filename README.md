# Heatseeker — Smart Money Tracker

---

## Context for AI Assistants

This project was built iteratively in a single chat session. Read this section first before making any changes.

### What this tool is
A Flask web app that analyzes US ETFs, US stocks, and Swedish OMXS30 stocks for institutional footprints. It answers three questions: where are institutions forced to buy, forced to sell, and defending a price level.

### Three separate analyzers
- `analyzer.py` — **ETF algo**. Uses COT (CFTC API) and Max Pain (options chain) as institutional signals. Tuned for mean-reversion on institutional instruments. ADX > 25 = bullish, RSI < 30 = bullish.
- `analyzer_stocks.py` — **Stock algo**. Tuned for momentum/growth stocks (backtested on Mag 7). Key differences from ETF algo:
  - ADX **flipped**: ADX ≤ 25 = bullish (consolidation = setup, high ADX = late)
  - RSI **momentum**: 50–70 = bullish (sweet spot, not oversold mean-reversion)
  - **Fast Cross** (SMA20/50) scored
  - **Relative Strength** vs benchmark (SPY for US, ^OMX for Swedish)
  - **Earnings Proximity** replaces Max Pain
- Both analyzers share: golden cross, MACD, OBV, delta volume, above SMA200

### Scoring system — critical to understand
The scoring is **weighted and normalized**, not a raw point count. Every signal has a weight (see `WEIGHTS` in `analyzer.py`, `STOCK_WEIGHTS` in `analyzer_stocks.py`). If a signal is unavailable (e.g. COT API down, no options data), its weight is redistributed proportionally across the remaining signals. Score is 0.0–1.0, displayed as a percentage.

```
>= 80%  STRONG BUY
>= 60%  WATCH
>= 40%  NO TRADE
<  40%  AVOID
```

### ETF signal weights
| Signal | Weight | Condition |
|--------|--------|-----------|
| COT | 0.20 | CFTC net long index > 60 |
| ADX | 0.18 | ADX > 25 (trending) |
| Golden Cross | 0.12 | SMA50 > SMA200 |
| Max Pain | 0.12 | Price within 5% of max pain |
| RSI Regime | 0.12 | RSI < 30 (oversold) |
| Above SMA200 | 0.10 | Price > SMA200 |
| MACD | 0.06 | Bullish crossover |
| OBV | 0.05 | Rising |
| Delta Volume | 0.05 | Buyers dominant |

COT is only available for: SPY, QQQ, GLD, SLV, TLT, USO. Sector ETFs skip COT and redistribute weight.

### Stock signal weights
| Signal | Weight | Condition |
|--------|--------|-----------|
| Relative Strength | 0.20 | Outperforming benchmark (20d) |
| Above SMA200 | 0.15 | Price > SMA200 |
| ADX Setup | 0.15 | ADX ≤ 25 (consolidation) |
| Golden Cross | 0.10 | SMA50 > SMA200 |
| Earnings Proximity | 0.10 | > 14 days to earnings |
| RSI Momentum | 0.10 | RSI 50–70 |
| Fast Cross | 0.06 | SMA20 > SMA50 |
| Delta Volume | 0.05 | Buyers dominant |
| OBV | 0.05 | Rising |
| MACD | 0.04 | Bullish crossover |

### Stock algo is tuned for growth/momentum stocks
Backtested across Mag 7 (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA) over 5 years. Signal ordering is correct on US large-cap growth stocks. May be inverted on range-bound, value, or European stocks — use the Verify tab to check before trusting scores on unfamiliar tickers.

### Bottom Watch — isolated layer
`compute_bottom_watch()` in `analyzer.py` is completely separate from the scoring engine. It does NOT affect the weighted score or signal output. It is appended as a standalone `bottom_watch` key in the response. It uses: RSI divergence, RSI oversold (<35), OBV divergence, ATR exhaustion, ADX weakening, price at VAL, COT extreme (<15). Thresholds: 5+/7 = HIGH PROBABILITY, 3+/7 = POSSIBLE, <3 = NONE.

### Caching layer
`cache.py` provides in-memory caching to reduce redundant API calls:
- **OHLCV data**: 1 hour TTL (daily bars don't change intraday)
- **Earnings dates**: 24 hour TTL
- **Max Pain**: 1 hour TTL (open interest shifts are gradual)
- **COT**: 1 hour TTL (data updates weekly on Fridays)
- **Batch download**: `yf.download()` with multiple tickers in one call

### SSE streaming
All three analysis tabs (ETFs, US Stocks, Swedish Stocks) use Server-Sent Events. Cards appear one by one as each ticker completes analysis, sorted by score descending. This scales to any number of tickers without blocking the UI.

### Days-since-change
All trend signals include a `days_Xd` field showing how many consecutive days the current state has been active. Computed via `days_since_cross()` helper. ADX direction uses +DI vs -DI as a vectorized proxy.

### Frontend architecture — do not monolith
```
templates/base.html           — shell, tabs, script includes
templates/tab_home.html       — welcome page + market snapshot
templates/tab_etf.html        — ETF grid
templates/tab_us_stocks.html  — US stocks grid
templates/tab_stocks.html     — Swedish stocks grid
templates/tab_verify.html     — backtest + signal analysis
static/css/main.css           — all styles
static/js/cards.js            — shared helpers: bottomWatch(), trendSection(), levelsSection(), scoreBar()
static/js/home.js             — market snapshot loader
static/js/etf.js              — renderEtfCard(), loadEtfs() via SSE
static/js/us_stocks.js        — renderUsStockCard(), loadUsStocks() via SSE
static/js/stocks.js           — renderStockCard(), loadStocks() via SSE
static/js/verify.js           — backtest runner, signal analysis, card renderer
```

When adding a new feature: edit the relevant small file only. Never rewrite base.html or main.css entirely.

### Verify tab
The Verify tab has two functions:
- **Run Backtest**: full-history walk-forward backtest on any ticker. Auto-detects ETF vs stock. Shows signal distribution, forward returns (5d/10d/20d), win rates, max drawdown, signal ordering check, and bottom watch backtest.
- **Signal Analysis**: runs the live analysis (same as the tab cards) on any ticker. Auto-detects ETF vs stock algo.

### Backtest optimization
`run_verify()` precomputes all indicators (RSI, ADX, MACD, OBV, SMAs) once over the full price series, then reads values by index in the loop. Volume profile is recomputed every 20 bars. This is ~10x faster than recomputing on every 252-bar window. For stocks, SPY data is fetched once and aligned by date for backtestable relative strength.

### Backtest runner (CLI)
`backtest_runner.py` is a standalone CLI tool for the ETF algo only. Not part of the web app.
```bash
python backtest_runner.py             # 3-year backtest
python backtest_runner.py --years 5   # 5-year backtest
python backtest_runner.py --csv       # save results to CSV
```

### COT implementation
COT data is fetched from the CFTC Socrata SODA API via `curl_cffi` with Chrome impersonation. Python's standard `requests` library and `http.client` hang on the CFTC server due to TLS incompatibility. `curl_cffi` (installed as a yfinance dependency) uses native TLS and works. COT is only fetched for ETFs with known CFTC keywords (SPY, QQQ, GLD, SLV, TLT, USO).

### Known limitations to preserve
- Delta volume is an OHLCV approximation, not true tick delta
- COT is weekly — too slow for short-term trades
- Max Pain is only reliable in the final week before options expiry
- MACD crossover is noisy — treat as trigger only, not standalone signal
- Swedish stock volume is thinner than US ETFs — signals less reliable on small caps
- Stock algo is momentum-biased — may be inverted on range-bound/value stocks
- `curl_cffi` (yfinance dependency) is not thread-safe — all analysis runs sequentially

### Intended hold period
Signals are calibrated for **1–4 week medium-term swing trades** on daily bars. Not suitable for intraday or long-term (6m+) holds without modification.

### What has NOT been built yet
- Email/SMS alerts on signal changes
- Score history chart per ticker
- Open Interest per price level
- Tick-level delta volume
- Swedish stock-specific algo tuning
- Max Pain for individual US stocks (Mag 7)

---

## The Core Thesis

Institutions cannot hide large capital movements. Their size creates friction — a $500M position takes days to build, leaving detectable footprints in volume, price structure, and public data. This tool reads the footprints their size forces them to leave, and identifies levels before retail traders catch on.

Your edge: a $500 position fills in milliseconds. A $500M position takes days. That asymmetry is the entire basis of this system.

---

## Tickers Covered

### US ETFs (20)
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

### US Stocks (Mag 7)
AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA — benchmarked against SPY

### Swedish Stocks (OMXS30)
29 constituents — benchmarked against ^OMX

---

## Data Sources

| Data | Source | Cost | Update Frequency | Cache TTL |
|------|--------|------|-----------------|-----------|
| OHLCV price data | yfinance | Free | Daily | 1 hour |
| Options chain | yfinance | Free | Real-time | 1 hour |
| COT report | CFTC SODA API | Free | Weekly (Fridays) | 1 hour |
| Earnings dates | yfinance | Free | As announced | 24 hours |

---

## Setup & Running

```bash
pip install flask yfinance pandas numpy requests
python app.py
# Open http://localhost:5000
```

---

## File Structure

```
Heatseeker/
├── app.py                — Flask server, SSE streaming, all API routes
├── analyzer.py           — ETF algo (COT, Max Pain, mean-reversion signals)
├── analyzer_stocks.py    — Stock algo (momentum/growth signals, configurable benchmark)
├── cache.py              — OHLCV, earnings, max pain, batch download caching
├── backtest.py           — Backtest engine (ETF + stock, precomputed indicators)
├── backtest_runner.py    — Standalone CLI backtest tool (ETF only)
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html         — Shell, tabs, script includes
│   ├── tab_home.html     — Welcome page + market snapshot
│   ├── tab_etf.html      — US ETF grid
│   ├── tab_us_stocks.html — US stocks grid
│   ├── tab_stocks.html   — Swedish stocks grid
│   └── tab_verify.html   — Backtest + signal analysis
└── static/
    ├── css/
    │   └── main.css      — All styles
    └── js/
        ├── cards.js      — Shared card rendering helpers
        ├── home.js       — Market snapshot loader
        ├── etf.js        — ETF card renderer + SSE loader
        ├── us_stocks.js  — US stock card renderer + SSE loader
        ├── stocks.js     — Swedish stock card renderer + SSE loader
        └── verify.js     — Backtest runner + signal analysis
```

---

## Future Improvements

- Add Open Interest data per price level (requires exchange API)
- Replace delta volume approximation with tick-level data feed
- Add email/SMS alert when a ticker crosses from WATCH to STRONG BUY
- Add a score history chart per ticker to track signal evolution over time
- Tune a separate algo for Swedish/European value stocks
- Add Max Pain for Mag 7 stocks (deep options markets)
- Add VIX as a market regime filter
