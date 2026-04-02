import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from cache import get_ohlcv, get_earnings, batch_download, get_compounder_pct
from analyzer import (
    get_volume_profile, get_fair_value_gaps, compute_adx,
    compute_macd, compute_obv, compute_delta_volume,
    days_since_cross, compute_bottom_watch, weighted_score,
    score_to_signal, is_quarter_end_risk, compute_rsi,
)

# ── OMXS30 CONSTITUENTS ───────────────────────────────────────────────────
OMXS30 = {
    "ERIC-B.ST":  "Ericsson",
    "VOLV-B.ST":  "Volvo",
    "SAND.ST":    "Sandvik",
    "SEB-A.ST":   "SEB",
    "ATCO-A.ST":  "Atlas Copco A",
    "ATCO-B.ST":  "Atlas Copco B",
    "HM-B.ST":    "H&M",
    "INVE-B.ST":  "Investor B",
    "SHB-A.ST":   "Handelsbanken",
    "SWED-A.ST":  "Swedbank",
    "ABB.ST":     "ABB",
    "ALFA.ST":    "Alfa Laval",
    "ASSA-B.ST":  "Assa Abloy",
    "AZN.ST":     "AstraZeneca",
    "BOL.ST":     "Boliden",
    "CAST.ST":    "Castellum",
    "ESSITY-B.ST":"Essity",
    "EVO.ST":     "Evolution",
    "GETI-B.ST":  "Getinge",
    "HEXA-B.ST":  "Hexagon",
    "HUSQ-B.ST":  "Husqvarna",
    "KINV-B.ST":  "Kinnevik",
    "NDA-SE.ST":  "Nordea",
    "NIBE-B.ST":  "NIBE",
    "SAAB-B.ST":  "Saab",
    "SKA-B.ST":   "Skanska",
    "SKF-B.ST":   "SKF",
    "SSAB-A.ST":  "SSAB",
    "TEL2-B.ST":  "Tele2",
}

# Stock-specific weights — tuned for individual stocks (not ETFs).
# Backtested across Mag 7 over 5 years.
# Key differences from ETF algo:
#   - ADX flipped: low ADX (consolidation) = setup, high ADX = late
#   - RSI momentum: 50-70 sweet spot, not oversold mean-reversion
#   - Fast cross added: free signal, already computed
STOCK_WEIGHTS = {
    "relative_strength": 0.28,  # strongest signal (+1.09% edge)
    "adx_direction":     0.22,  # +DI > -DI = bullish direction
    "above_sma200":      0.20,  # regime filter
    "earnings_proximity":0.10,
    "delta_volume":      0.10,  # 3rd best edge (+0.56%)
    "obv":               0.06,
    "macd":              0.04,
}

_bench_cache: dict = {}  # {(ticker, period_days): (timestamp, float | None)}


def _get_bench_returns(bench_ticker: str, period_days: int) -> float | None:
    """Cached benchmark return over period_days. 1hr TTL."""
    import time
    key = (bench_ticker, period_days)
    now = time.time()
    cached = _bench_cache.get(key)
    if cached and now - cached[0] < 3600:
        return cached[1]
    try:
        df = get_ohlcv(bench_ticker, period="3mo")
        if len(df) < period_days:
            result = None
        else:
            result = float(
                (df["Close"].iloc[-1] - df["Close"].iloc[-period_days])
                / df["Close"].iloc[-period_days]
            )
    except Exception:
        result = None
    _bench_cache[key] = (now, result)
    return result


def get_relative_strength(df: pd.DataFrame, period_days: int = 20,
                          bench_ticker: str = "^OMX") -> dict:
    """Returns whether stock is outperforming benchmark over period_days."""
    try:
        if len(df) < period_days:
            return {"outperforming": None, "stock_return": None, "bench_return": None}
        stock_ret = float(
            (df["Close"].iloc[-1] - df["Close"].iloc[-period_days])
            / df["Close"].iloc[-period_days] * 100
        )
        bench_ret = _get_bench_returns(bench_ticker, period_days)
        if bench_ret is None:
            return {"outperforming": None, "stock_return": round(stock_ret, 2), "bench_return": None}
        bench_pct = round(bench_ret * 100, 2)
        return {
            "outperforming": stock_ret > bench_pct,
            "stock_return":  round(stock_ret, 2),
            "bench_return":  bench_pct,
        }
    except Exception:
        return {"outperforming": None, "stock_return": None, "bench_return": None}


def get_earnings_proximity(ticker: str) -> dict:
    """Returns True (safe) if next earnings is more than 14 days away."""
    return get_earnings(ticker)


def analyze_stock(ticker: str, names: dict | None = None,
                  currency: str = "SEK", bench_ticker: str = "^OMX") -> dict:
    if names is None:
        names = OMXS30
    df = get_ohlcv(ticker, period="1y")
    if df.empty or len(df) < 30:
        return {"ticker": ticker, "name": names.get(ticker, ticker), "error": "Insufficient data"}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else close
    daily_change = round((close - prev_close) / prev_close * 100, 2)
    vp    = get_volume_profile(df)
    fvgs  = get_fair_value_gaps(df)
    qe    = is_quarter_end_risk()
    rs    = get_relative_strength(df, bench_ticker=bench_ticker)
    ep    = get_earnings_proximity(ticker)

    sma20  = df["Close"].rolling(20).mean()
    sma50  = df["Close"].rolling(50).mean()
    sma200 = df["Close"].rolling(200).mean()
    adx    = compute_adx(df)
    macd   = compute_macd(df)
    obv    = compute_obv(df)
    delta  = compute_delta_volume(df)

    golden_cross  = bool(sma50.iloc[-1] > sma200.iloc[-1])
    fast_cross    = bool(sma20.iloc[-1] > sma50.iloc[-1])
    adx_confirmed = adx > 25

    days_golden = days_since_cross(sma50, sma200)
    days_fast   = days_since_cross(sma20, sma50)

    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    up, dn = h.diff(), -l.diff()
    plus_di  = 100 * up.where((up > dn) & (up > 0), 0.0).ewm(span=14, adjust=False).mean() / atr
    minus_di = 100 * dn.where((dn > up) & (dn > 0), 0.0).ewm(span=14, adjust=False).mean() / atr
    days_adx = days_since_cross(plus_di, minus_di)

    rsi_series = compute_rsi(df["Close"])
    rsi_value  = round(float(rsi_series.iloc[-1]), 1)
    above_sma  = bool(close > sma200.iloc[-1])

    # Precompute series for signal age
    macd_line = df["Close"].ewm(span=12, adjust=False).mean() - df["Close"].ewm(span=26, adjust=False).mean()
    macd_signal_line = macd_line.ewm(span=9, adjust=False).mean()
    obv_series = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()

    adx_bullish = bool(plus_di.iloc[-1] > minus_di.iloc[-1])

    fired = {
        "relative_strength":  rs["outperforming"],
        "earnings_proximity": ep["safe"],
        "adx_direction":      adx_bullish,
        "above_sma200":       above_sma,
        "macd":               macd["crossed_bullish"],
        "obv":                obv["rising"],
        "delta_volume":       delta,
    }

    # use stock weights
    available   = {k: v for k, v in fired.items() if v is not None}
    unavailable = sorted(k for k, v in fired.items() if v is None)
    total_w     = sum(STOCK_WEIGHTS[k] for k in available)
    score       = sum(STOCK_WEIGHTS[k] / total_w for k, v in available.items() if v is True) if total_w else 0.0
    ws = {
        "score": round(score, 4),
        "pct":   round(score * 100, 1),
        "unavailable": unavailable,
        "available_count": len(available),
    }

    signal, signal_class = score_to_signal(ws["score"])

    # Signal age: count consecutive days with the same signal tier
    signal_age = 0
    for lb in range(2, min(31, len(df) - 5)):
        idx = -lb
        p_close = float(df["Close"].iloc[idx])
        p_rsi = float(rsi_series.iloc[idx])
        p_fired = {
            "relative_strength": fired["relative_strength"],
            "earnings_proximity": fired["earnings_proximity"],
            "adx_direction": adx_bullish,
            "above_sma200": p_close > float(sma200.iloc[idx]),
            "macd":         bool(macd_line.iloc[idx] > macd_signal_line.iloc[idx] and macd_line.iloc[idx-1] <= macd_signal_line.iloc[idx-1]),
            "obv":          bool(obv_series.iloc[idx] > obv_series.iloc[idx-5]),
            "delta_volume": delta,
        }
        p_avail = {k: v for k, v in p_fired.items() if v is not None}
        p_tw = sum(STOCK_WEIGHTS[k] for k in p_avail)
        p_score = sum(STOCK_WEIGHTS[k] / p_tw for k, v in p_avail.items() if v) if p_tw else 0.0
        p_sig, _ = score_to_signal(p_score)
        if p_sig == signal:
            signal_age += 1
        else:
            break

    bottom = compute_bottom_watch(df, vp, None, adx)

    compounder_pct = get_compounder_pct(ticker)
    is_compounder = compounder_pct is not None and compounder_pct >= 0.85

    pfx = "$" if currency == "USD" else ""
    sfx = "" if currency == "USD" else f" {currency}"

    return {
        "ticker":             ticker,
        "name":               names.get(ticker, ticker),
        "price":              round(close, 2),
        "daily_change":       daily_change,
        "currency":           currency,
        "signal":             signal,
        "signal_class":       signal_class,
        "signal_age":         signal_age,
        "score":              ws["score"],
        "score_pct":          ws["pct"],
        "unavailable_signals":ws["unavailable"],
        "available_signals":  ws["available_count"],
        "institutional": {
            "poc": vp["poc"], "vah": vp["vah"], "val": vp["val"],
            "relative_strength": rs,
            "earnings_proximity": ep,
            "quarter_end_risk": qe,
            "fvgs": fvgs[-2:] if fvgs else [],
        },
        "trend": {
            "adx": adx, "adx_confirmed": adx_confirmed, "days_adx": days_adx,
            "golden_cross": golden_cross, "days_golden": days_golden,
            "fast_cross": fast_cross, "days_fast": days_fast,
            "macd_bullish": macd["bullish"], "macd_crossed": macd["crossed_bullish"],
            "days_macd": macd["days_since_cross"],
            "obv_rising": obv["rising"],
            "obv_magnitude": obv["magnitude"],
            "distribution_warning": obv["distribution_warning"],
            "delta_positive": delta,
            "rsi": rsi_value,
            "above_sma200": above_sma,
            "sma20": round(float(sma20.iloc[-1]), 2),
            "sma50": round(float(sma50.iloc[-1]), 2),
            "sma200": round(float(sma200.iloc[-1]), 2),
        },
        "levels": {
            "entry_zone": f"{pfx}{vp['val']} – {pfx}{vp['poc']}{sfx}",
            "target":     f"{pfx}{vp['vah']}{sfx}",
            "invalidation": f"{pfx}{round(vp['val'] * 0.99, 2)}{sfx}",
        },
        "bottom_watch": bottom,
        "compounder": {"pct": compounder_pct, "is_compounder": is_compounder},
        "error": None,
    }
