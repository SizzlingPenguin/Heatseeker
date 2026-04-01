import numpy as np
import pandas as pd
import yfinance as yf
from analyzer import (
    get_volume_profile, get_fair_value_gaps, compute_adx,
    compute_macd, compute_obv, compute_delta_volume,
    weighted_score, score_to_signal, is_quarter_end_risk,
    compute_rsi, compute_bottom_watch, SIGNAL_THRESHOLDS, WEIGHTS,
)
from analyzer_stocks import STOCK_WEIGHTS
from datetime import datetime, timedelta

TICKERS = ["SPY", "QQQ", "GLD", "SLV", "TLT", "USO"]
LOOKBACK = 252        # 1 year of daily bars needed to compute indicators
FORWARD_DAYS = [5, 10, 20]


def _fired_from_df(df: pd.DataFrame) -> dict:
    """Compute all backtestable signals from a slice of OHLCV data."""
    close = float(df["Close"].iloc[-1])
    sma50  = float(df["Close"].rolling(50).mean().iloc[-1])
    sma200 = float(df["Close"].rolling(200).mean().iloc[-1])
    adx    = compute_adx(df)
    macd   = compute_macd(df)
    obv    = compute_obv(df)
    delta  = compute_delta_volume(df)
    rsi    = float(compute_rsi(df["Close"]).iloc[-1])

    return {
        # COT excluded — no free historical data
        "cot":            None,
        # max_pain excluded — no free historical options data
        "max_pain":       None,
        "adx":            adx > 25,
        "golden_cross":   sma50 > sma200,
        "rsi_regime":     rsi < 30,
        "above_sma200":   close > sma200,
        "macd":           macd["crossed_bullish"],
        "obv":            obv["rising"],
        "delta_volume":   delta,
    }


def run_backtest(ticker: str, years: int = 3) -> dict:
    total_days = LOOKBACK + (years * 252) + max(FORWARD_DAYS)
    df = yf.download(ticker, period=f"{years + 2}y", interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty or len(df) < LOOKBACK + max(FORWARD_DAYS) + 10:
        return {"ticker": ticker, "error": "Insufficient historical data"}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    records = []

    # walk forward: start after LOOKBACK bars, stop before we run out of forward data
    for i in range(LOOKBACK, len(df) - max(FORWARD_DAYS)):
        window = df.iloc[i - LOOKBACK: i].copy().set_index("Date")
        fired  = _fired_from_df(window)
        ws     = weighted_score(fired)
        signal, _ = score_to_signal(ws["score"])

        entry_price = float(df["Close"].iloc[i])
        row = {
            "date":   df["Date"].iloc[i],
            "signal": signal,
            "score":  ws["score"],
        }
        for fwd in FORWARD_DAYS:
            future_price = float(df["Close"].iloc[i + fwd])
            row[f"return_{fwd}d"] = round((future_price - entry_price) / entry_price * 100, 3)
        records.append(row)

    results = pd.DataFrame(records)
    return {"ticker": ticker, "results": results, "error": None}


def summarize(results_df: pd.DataFrame) -> dict:
    summary = {}
    for sig in ["HOT", "BUY", "WATCH", "AVOID"]:
        subset = results_df[results_df["signal"] == sig]
        if subset.empty:
            continue
        entry = {}
        for fwd in FORWARD_DAYS:
            col = f"return_{fwd}d"
            returns = subset[col]
            entry[f"{fwd}d"] = {
                "count":      int(len(returns)),
                "win_rate":   round(float((returns > 0).mean() * 100), 1),
                "avg_return": round(float(returns.mean()), 2),
                "median":     round(float(returns.median()), 2),
                "max_dd":     round(float(returns.min()), 2),
            }
        summary[sig] = entry
    return summary


def _fired_stock_from_df(df: pd.DataFrame, spy_df: pd.DataFrame | None = None) -> dict:
    """Compute stock-algo signals. spy_df enables backtestable relative strength."""
    close = float(df["Close"].iloc[-1])
    sma20  = float(df["Close"].rolling(20).mean().iloc[-1])
    sma50  = float(df["Close"].rolling(50).mean().iloc[-1])
    sma200 = float(df["Close"].rolling(200).mean().iloc[-1])
    adx    = compute_adx(df)
    macd   = compute_macd(df)
    obv    = compute_obv(df)
    delta  = compute_delta_volume(df)
    rsi    = float(compute_rsi(df["Close"]).iloc[-1])

    # Backtestable relative strength vs SPY
    rs = None
    if spy_df is not None and len(df) >= 20 and len(spy_df) >= 20:
        stock_ret = (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-20])) / float(df["Close"].iloc[-20])
        spy_ret = (float(spy_df["Close"].iloc[-1]) - float(spy_df["Close"].iloc[-20])) / float(spy_df["Close"].iloc[-20])
        rs = stock_ret > spy_ret

    return {
        "relative_strength":  rs,
        "earnings_proximity": None,
        "adx_setup":          adx <= 25,
        "golden_cross":       sma50 > sma200,
        "rsi_momentum":       50 <= rsi <= 70,
        "above_sma200":       close > sma200,
        "fast_cross":         sma20 > sma50,
        "macd":               macd["crossed_bullish"],
        "obv":                obv["rising"],
        "delta_volume":       delta,
    }


def _stock_weighted_score(fired: dict) -> dict:
    """Weighted score using STOCK_WEIGHTS."""
    available = {k: v for k, v in fired.items() if v is not None}
    unavailable = sorted(k for k, v in fired.items() if v is None)
    total_w = sum(STOCK_WEIGHTS[k] for k in available)
    if total_w == 0:
        return {"score": 0.0, "pct": 0, "unavailable": unavailable}
    score = sum(STOCK_WEIGHTS[k] / total_w for k, v in available.items() if v is True)
    return {
        "score": round(score, 4),
        "pct": round(score * 100, 1),
        "unavailable": unavailable,
        "available_count": len(available),
    }


def run_backtest_stock(ticker: str, years: int = 3) -> dict:
    """Backtest using the stock algo."""
    df = yf.download(ticker, period=f"{years + 2}y", interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty or len(df) < LOOKBACK + max(FORWARD_DAYS) + 10:
        return {"ticker": ticker, "error": "Insufficient historical data"}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    records = []
    for i in range(LOOKBACK, len(df) - max(FORWARD_DAYS)):
        window = df.iloc[i - LOOKBACK:i].copy().set_index("Date")
        fired = _fired_stock_from_df(window)
        ws = _stock_weighted_score(fired)
        signal, _ = score_to_signal(ws["score"])
        entry_price = float(df["Close"].iloc[i])
        row = {"date": df["Date"].iloc[i], "signal": signal, "score": ws["score"]}
        for fwd in FORWARD_DAYS:
            future_price = float(df["Close"].iloc[i + fwd])
            row[f"return_{fwd}d"] = round((future_price - entry_price) / entry_price * 100, 3)
        records.append(row)
    results = pd.DataFrame(records)
    return {"ticker": ticker, "results": results, "error": None}


def is_etf(ticker: str) -> bool:
    """Heuristic: known ETF list or yfinance quoteType."""
    if ticker.upper() in TICKERS:
        return True
    try:
        info = yf.Ticker(ticker).info
        return info.get("quoteType", "").upper() == "ETF"
    except Exception:
        return False


def run_verify(ticker: str, period: str = "max") -> dict:
    """Auto-detect ETF vs stock and run full-history backtest."""
    ticker = ticker.upper().strip()
    etf = is_etf(ticker)
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty or len(df) < LOOKBACK + max(FORWARD_DAYS) + 10:
        return {"ticker": ticker, "type": "etf" if etf else "stock",
                "error": "Insufficient historical data"}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()

    spy_full = None
    if not etf:
        spy_raw = yf.download("SPY", period=period, interval="1d",
                              progress=False, auto_adjust=True)
        if not spy_raw.empty:
            if isinstance(spy_raw.columns, pd.MultiIndex):
                spy_raw.columns = spy_raw.columns.get_level_values(0)
            spy_full = spy_raw.reset_index()

    total_days = len(df)
    start_date = str(df["Date"].iloc[LOOKBACK])[:10]
    end_date = str(df["Date"].iloc[-max(FORWARD_DAYS) - 1])[:10]

    # ── Precompute all indicators once over full series ──
    close = df["Close"]
    high, low = df["High"], df["Low"]
    volume = df["Volume"]

    sma20  = close.rolling(20).mean()
    sma50  = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    # RSI
    rsi_series = compute_rsi(close)

    # ADX + DI
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_series = tr.ewm(span=14, adjust=False).mean()
    up, dn = high.diff(), -low.diff()
    plus_di  = 100 * up.where((up > dn) & (up > 0), 0.0).ewm(span=14, adjust=False).mean() / atr_series
    minus_di = 100 * dn.where((dn > up) & (dn > 0), 0.0).ewm(span=14, adjust=False).mean() / atr_series
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    adx_series = dx.ewm(span=14, adjust=False).mean()

    # MACD
    macd_line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_above = macd_line > macd_signal

    # OBV
    obv_series = (np.sign(close.diff()) * volume).fillna(0).cumsum()

    # Delta volume
    rng = (high - low).replace(0, np.nan)
    buy_vol = volume * ((close - low) / rng)
    sell_vol = volume - buy_vol
    delta_cum = (buy_vol - sell_vol).fillna(0)

    # SPY precompute for relative strength
    spy_close = None
    if spy_full is not None:
        spy_close = spy_full.set_index("Date")["Close"]

    records = []
    for i in range(LOOKBACK, len(df) - max(FORWARD_DAYS)):
        idx = i - 1  # last bar in the window (iloc-based on df)

        c     = float(close.iloc[idx])
        s20   = float(sma20.iloc[idx])
        s50   = float(sma50.iloc[idx])
        s200  = float(sma200.iloc[idx])
        adx   = float(adx_series.iloc[idx])
        rsi   = float(rsi_series.iloc[idx])
        obv_now = float(obv_series.iloc[idx])
        obv_5   = float(obv_series.iloc[idx - 5]) if idx >= 5 else obv_now
        obv_rising = obv_now > obv_5
        delta_pos = float(delta_cum.iloc[max(idx-4, 0):idx+1].sum()) > 0

        # MACD crossed bullish
        macd_crossed = bool(macd_above.iloc[idx] and not macd_above.iloc[idx - 1]) if idx > 0 else False
        macd_bull = bool(macd_above.iloc[idx])

        gc = s50 > s200
        fc = s20 > s50
        above_sma = c > s200

        if etf:
            fired = {
                "cot": None,
                "max_pain": None,
                "adx": adx > 25,
                "golden_cross": gc,
                "rsi_regime": rsi < 30,
                "above_sma200": above_sma,
                "macd": macd_crossed,
                "obv": obv_rising,
                "delta_volume": delta_pos,
            }
            ws = weighted_score(fired)
        else:
            # Relative strength vs SPY
            rs = None
            if spy_close is not None and idx >= 20:
                date_val = df["Date"].iloc[idx]
                spy_at = spy_close[spy_close.index <= date_val]
                if len(spy_at) >= 20:
                    stock_ret = (c - float(close.iloc[idx - 20])) / float(close.iloc[idx - 20])
                    spy_ret = (float(spy_at.iloc[-1]) - float(spy_at.iloc[-20])) / float(spy_at.iloc[-20])
                    rs = stock_ret > spy_ret

            fired = {
                "relative_strength": rs,
                "earnings_proximity": None,
                "adx_setup": adx <= 25,
                "golden_cross": gc,
                "rsi_momentum": 50 <= rsi <= 70,
                "above_sma200": above_sma,
                "fast_cross": fc,
                "macd": macd_crossed,
                "obv": obv_rising,
                "delta_volume": delta_pos,
            }
            ws = _stock_weighted_score(fired)

        signal, _ = score_to_signal(ws["score"])

        # Bottom watch (using precomputed values)
        obv_20 = float(obv_series.iloc[idx - 20]) if idx >= 20 else obv_now
        close_20 = float(close.iloc[idx - 20]) if idx >= 20 else c
        rsi_oversold = rsi < 35

        # RSI divergence
        if idx >= 20:
            price_ll = c < float(close.iloc[idx-20:idx+1].min()) * 1.01
            rsi_window = rsi_series.iloc[idx-20:idx]
            rsi_hl = rsi > float(rsi_window.min()) if len(rsi_window) > 0 else False
            rsi_divergence = price_ll and rsi_hl
        else:
            rsi_divergence = False

        obv_divergence = c < close_20 and obv_now > obv_20

        # ATR exhaustion
        if idx >= 10:
            atr_spike = float(atr_series.iloc[idx-10:idx-5].max())
            atr_exhaustion = float(atr_series.iloc[idx]) < atr_spike * 0.80
        else:
            atr_exhaustion = False

        # Volume profile (recompute every 20 bars for speed)
        if i % 20 == 0 or i == LOOKBACK:
            window_df = df.iloc[i - LOOKBACK:i].copy().set_index("Date")
            vp = get_volume_profile(window_df)
        at_val = c <= vp["val"] * 1.02

        bw_signals = {
            "price_at_val": at_val,
            "rsi_divergence": rsi_divergence,
            "rsi_oversold": rsi_oversold,
            "obv_divergence": obv_divergence,
            "atr_exhaustion": atr_exhaustion,
            "adx_weakening": adx < 25,
            "cot_extreme": False,
        }
        bw_count = sum(1 for v in bw_signals.values() if v)
        if bw_count >= 5:
            bw_label = "HIGH PROBABILITY BOTTOM"
        elif bw_count >= 3:
            bw_label = "POSSIBLE BOTTOM"
        else:
            bw_label = "NO BOTTOM SIGNAL"

        entry_price = float(df["Close"].iloc[i])
        row = {
            "date": str(df["Date"].iloc[i])[:10],
            "signal": signal,
            "score": ws["score"],
            "bottom_label": bw_label,
        }
        for fwd in FORWARD_DAYS:
            future_price = float(df["Close"].iloc[i + fwd])
            row[f"return_{fwd}d"] = round((future_price - entry_price) / entry_price * 100, 3)
        records.append(row)

    results = pd.DataFrame(records)
    summary = summarize(results)

    # Signal ordering check
    ordering = []
    for sig in ["HOT", "BUY", "WATCH", "AVOID"]:
        sub = results[results["signal"] == sig]["return_20d"]
        if len(sub) > 0:
            ordering.append({"signal": sig, "avg_20d": round(float(sub.mean()), 2),
                             "count": int(len(sub))})

    # Bottom watch summary
    bottom_summary = {}
    for label in ["HIGH PROBABILITY BOTTOM", "POSSIBLE BOTTOM", "NO BOTTOM SIGNAL"]:
        sub = results[results["bottom_label"] == label]
        if sub.empty:
            continue
        entry = {}
        for fwd in FORWARD_DAYS:
            col = f"return_{fwd}d"
            returns = sub[col]
            entry[f"{fwd}d"] = {
                "count":      int(len(returns)),
                "win_rate":   round(float((returns > 0).mean() * 100), 1),
                "avg_return": round(float(returns.mean()), 2),
                "median":     round(float(returns.median()), 2),
                "max_dd":     round(float(returns.min()), 2),
            }
        bottom_summary[label] = entry

    return {
        "ticker": ticker,
        "type": "etf" if etf else "stock",
        "total_bars": total_days,
        "backtest_bars": len(records),
        "start_date": start_date,
        "end_date": end_date,
        "summary": summary,
        "ordering": ordering,
        "bottom_watch": bottom_summary,
        "error": None,
    }


def run_all_backtests(years: int = 3) -> dict:
    all_results = []
    ticker_summaries = {}

    for ticker in TICKERS:
        bt = run_backtest(ticker, years=years)
        if bt["error"]:
            ticker_summaries[ticker] = {"error": bt["error"]}
            continue
        df = bt["results"]
        ticker_summaries[ticker] = summarize(df)
        df["ticker"] = ticker
        all_results.append(df)

    if not all_results:
        return {"error": "No data", "by_ticker": ticker_summaries}

    combined = pd.concat(all_results, ignore_index=True)
    return {
        "overall": summarize(combined),
        "by_ticker": ticker_summaries,
        "error": None,
    }
