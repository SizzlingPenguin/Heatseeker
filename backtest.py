import numpy as np
import pandas as pd
import yfinance as yf
from analyzer import (
    get_volume_profile, get_fair_value_gaps, compute_adx,
    compute_macd, compute_obv, compute_delta_volume,
    weighted_score, score_to_signal, is_quarter_end_risk,
    compute_rsi, SIGNAL_THRESHOLDS, WEIGHTS,
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
    for sig in ["STRONG BUY", "WATCH", "NO TRADE", "AVOID"]:
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


def run_verify(ticker: str) -> dict:
    """Auto-detect ETF vs stock and run full-history backtest."""
    ticker = ticker.upper().strip()
    etf = is_etf(ticker)
    # Use max available history
    df = yf.download(ticker, period="max", interval="1d",
                     progress=False, auto_adjust=True)
    if df.empty or len(df) < LOOKBACK + max(FORWARD_DAYS) + 10:
        return {"ticker": ticker, "type": "etf" if etf else "stock",
                "error": "Insufficient historical data"}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()

    # Fetch SPY for stock relative strength
    spy_full = None
    if not etf:
        spy_raw = yf.download("SPY", period="max", interval="1d",
                              progress=False, auto_adjust=True)
        if not spy_raw.empty:
            if isinstance(spy_raw.columns, pd.MultiIndex):
                spy_raw.columns = spy_raw.columns.get_level_values(0)
            spy_full = spy_raw.reset_index()

    total_days = len(df)
    start_date = str(df["Date"].iloc[LOOKBACK])[:10]
    end_date = str(df["Date"].iloc[-max(FORWARD_DAYS) - 1])[:10]

    records = []
    for i in range(LOOKBACK, len(df) - max(FORWARD_DAYS)):
        window = df.iloc[i - LOOKBACK:i].copy().set_index("Date")
        if etf:
            fired = _fired_from_df(window)
            ws = weighted_score(fired)
        else:
            # Align SPY window by date
            spy_window = None
            if spy_full is not None:
                date_val = df["Date"].iloc[i]
                spy_slice = spy_full[spy_full["Date"] <= date_val]
                if len(spy_slice) >= LOOKBACK:
                    spy_window = spy_slice.iloc[-LOOKBACK:].copy().set_index("Date")
            fired = _fired_stock_from_df(window, spy_df=spy_window)
            ws = _stock_weighted_score(fired)
        signal, _ = score_to_signal(ws["score"])
        entry_price = float(df["Close"].iloc[i])
        row = {"date": str(df["Date"].iloc[i])[:10], "signal": signal, "score": ws["score"]}
        for fwd in FORWARD_DAYS:
            future_price = float(df["Close"].iloc[i + fwd])
            row[f"return_{fwd}d"] = round((future_price - entry_price) / entry_price * 100, 3)
        records.append(row)

    results = pd.DataFrame(records)
    summary = summarize(results)

    # Signal ordering check
    ordering = []
    for sig in ["STRONG BUY", "WATCH", "NO TRADE", "AVOID"]:
        sub = results[results["signal"] == sig]["return_20d"]
        if len(sub) > 0:
            ordering.append({"signal": sig, "avg_20d": round(float(sub.mean()), 2),
                             "count": int(len(sub))})

    return {
        "ticker": ticker,
        "type": "etf" if etf else "stock",
        "total_bars": total_days,
        "backtest_bars": len(records),
        "start_date": start_date,
        "end_date": end_date,
        "summary": summary,
        "ordering": ordering,
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
