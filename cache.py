"""Shared data cache — reduces redundant yfinance API calls."""
import time
import pandas as pd
import yfinance as yf

# {ticker: (timestamp, DataFrame)}
_ohlcv_cache: dict = {}
OHLCV_TTL = 3600  # 1 hour — daily bars don't change intraday

# {ticker: (timestamp, dict)}
_earnings_cache: dict = {}
EARNINGS_TTL = 86400  # 24 hours — earnings dates rarely change

# {ticker: (timestamp, float|None)}
_max_pain_cache: dict = {}
MAX_PAIN_TTL = 3600  # 1 hour


# {ticker: (timestamp, float)}
_compounder_cache: dict = {}
COMPOUNDER_TTL = 86400  # 24 hours — doesn't change often


def get_compounder_pct(ticker: str) -> float | None:
    """% of time above SMA200 over full history. Requires 20+ years of data."""
    now = time.time()
    cached = _compounder_cache.get(ticker)
    if cached and now - cached[0] < COMPOUNDER_TTL:
        return cached[1]

    try:
        df = yf.download(ticker, period="max", interval="1d",
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # Require 20 years (~5000 trading days)
        if len(df) < 5000:
            _compounder_cache[ticker] = (now, None)
            return None
        sma200 = df["Close"].rolling(200).mean()
        valid = sma200.dropna()
        pct = float((df["Close"].loc[valid.index] > valid).mean())
        _compounder_cache[ticker] = (now, round(pct, 3))
        return round(pct, 3)
    except Exception:
        _compounder_cache[ticker] = (now, None)
        return None


def get_ohlcv(ticker: str, period: str = "1y", force: bool = False) -> pd.DataFrame:
    now = time.time()
    cached = _ohlcv_cache.get(ticker)
    if not force and cached and now - cached[0] < OHLCV_TTL:
        return cached[1]

    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # Handle duplicate column names after flattening
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    _ohlcv_cache[ticker] = (now, df)
    return df


def clear_cache():
    """Clear all caches to force fresh data."""
    _ohlcv_cache.clear()
    _earnings_cache.clear()
    _max_pain_cache.clear()


def batch_download(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Download multiple tickers in one yfinance call, populate cache."""
    now = time.time()
    # Find which tickers need fetching
    needed = [t for t in tickers if t not in _ohlcv_cache or now - _ohlcv_cache[t][0] >= OHLCV_TTL]
    cached = {t: _ohlcv_cache[t][1] for t in tickers if t not in needed}

    if needed:
        raw = yf.download(needed, period=period, interval="1d",
                          progress=False, auto_adjust=True, group_by="ticker")
        if isinstance(raw.columns, pd.MultiIndex):
            if len(needed) == 1:
                # Single ticker: columns are (Price,) level
                df = raw.copy()
                df.columns = df.columns.get_level_values(0)
                _ohlcv_cache[needed[0]] = (now, df)
                cached[needed[0]] = df
            else:
                # Multiple tickers: columns are (Ticker, Price) level
                for t in needed:
                    try:
                        df = raw[t].dropna(how="all").copy()
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = df.columns.get_level_values(0)
                        _ohlcv_cache[t] = (now, df)
                        cached[t] = df
                    except (KeyError, Exception):
                        pass
        else:
            # Single ticker without MultiIndex
            _ohlcv_cache[needed[0]] = (now, raw)
            cached[needed[0]] = raw

    return cached


def get_earnings(ticker: str) -> dict:
    """Cached earnings proximity lookup."""
    from datetime import datetime
    now = time.time()
    cached = _earnings_cache.get(ticker)
    if cached and now - cached[0] < EARNINGS_TTL:
        return cached[1]

    result = {"safe": None, "days_to_earnings": None}
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is not None and not cal.empty and "Earnings Date" in cal.index:
            ed = cal.loc["Earnings Date"].iloc[0]
            days = (pd.Timestamp(ed).date() - datetime.today().date()).days
            result = {"safe": days > 14, "days_to_earnings": days}
    except Exception:
        pass

    _earnings_cache[ticker] = (now, result)
    return result


def get_max_pain(ticker: str) -> float | None:
    """Cached max pain lookup."""
    now = time.time()
    cached = _max_pain_cache.get(ticker)
    if cached and now - cached[0] < MAX_PAIN_TTL:
        return cached[1]

    result = None
    try:
        tk = yf.Ticker(ticker)
        expirations = tk.options
        if expirations:
            chain = tk.option_chain(expirations[0])
            calls = chain.calls[["strike", "openInterest"]]
            puts = chain.puts[["strike", "openInterest"]]
            strikes = sorted(set(calls["strike"]).union(set(puts["strike"])))
            pain = {
                s: ((s - calls[calls["strike"] <= s]["strike"]) * calls[calls["strike"] <= s]["openInterest"]).sum()
                 + ((puts[puts["strike"] >= s]["strike"] - s) * puts[puts["strike"] >= s]["openInterest"]).sum()
                for s in strikes
            }
            result = round(min(pain, key=pain.get), 2)
    except Exception:
        pass

    _max_pain_cache[ticker] = (now, result)
    return result
