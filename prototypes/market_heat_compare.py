"""
Market-Heat prototype — mimics the scoring from market-heat/heatmap.py
for backtesting comparison against Heatseeker.

Scoring: 7 indicators, weighted +/- scores, combined with ADX phase matrix.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import yfinance as yf
from analyzer import compute_rsi, score_to_signal

LOOKBACK = 252
FORWARD_DAYS = [5, 10, 20]


def compute_market_heat_signals(df):
    close = df["Close"]
    high, low, volume = df["High"], df["Low"], df["Volume"]

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9).mean()
    macd_state = "Buy" if float(macd.iloc[-1]) > float(macd_signal.iloc[-1]) else "Sell"

    # Gold-Line
    ema30 = close.ewm(span=30).mean()
    ema60 = close.ewm(span=60).mean()
    spread = float(ema30.iloc[-1]) - float(ema60.iloc[-1])
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr60 = float(tr.rolling(60).mean().iloc[-1])
    threshold = atr60 * 0.30
    gold_state = "Buy" if spread > threshold else "Sell" if spread < -threshold else "Neutral"

    # ADX
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(14).mean()
    adx_val = float(adx.iloc[-1])

    # OBV
    delta = close.diff()
    obv = (np.sign(delta) * volume).cumsum()
    obv_sma = obv.rolling(20).mean()
    obv_state = "Accumulating" if float(obv.iloc[-1]) > float(obv_sma.iloc[-1]) else "Distributing"

    # SMA200 distance
    sma200_dist = (float(close.iloc[-1]) - float(sma200.iloc[-1])) / float(sma200.iloc[-1]) * 100
    sma200_label = "Overextended" if sma200_dist > 10 else "Oversold" if sma200_dist < -10 else "Normal"

    # Swing detection (20-bar lookback)
    lows_arr = close.values
    highs_arr = high.values
    swing_lows, swing_highs = [], []
    lb = 20
    for i in range(lb, len(lows_arr) - lb):
        if lows_arr[i] == min(lows_arr[i - lb:i + lb + 1]):
            swing_lows.append(lows_arr[i])
        if highs_arr[i] == max(highs_arr[i - lb:i + lb + 1]):
            swing_highs.append(highs_arr[i])
    hl = swing_lows[-1] > swing_lows[-2] if len(swing_lows) >= 2 else None
    hh = swing_highs[-1] > swing_highs[-2] if len(swing_highs) >= 2 else None
    if hl is True and hh is True:
        swing = "Uptrend"
    elif hl is False and hh is False:
        swing = "Downtrend"
    else:
        swing = "Choppy"

    return {
        "sma2050": "Bullish" if float(sma20.iloc[-1]) > float(sma50.iloc[-1]) else "Bearish",
        "sma50200": "Bullish" if float(sma50.iloc[-1]) > float(sma200.iloc[-1]) else "Bearish",
        "macd": macd_state,
        "gold": gold_state,
        "obv": obv_state,
        "sma200_label": sma200_label,
        "swing": swing,
        "adx": adx_val,
    }


def compute_mh_signal(e):
    """Exact replica of market-heat's compute_signal."""
    score = 0
    score += 0.5 if e["sma2050"] == "Bullish" else -0.5
    score += 0.75 if e["sma50200"] == "Bullish" else -0.75
    score += 0.75 if e["macd"] == "Buy" else -0.75
    score += 0.75 if e["gold"] == "Buy" else (-0.75 if e["gold"] == "Sell" else 0)
    score += 1.5 if e["obv"] == "Accumulating" else -1.5
    score += -1.0 if e["sma200_label"] == "Overextended" else (1.0 if e["sma200_label"] == "Oversold" else 0)
    score += 1.25 if e["swing"] == "Uptrend" else (-1.25 if e["swing"] == "Downtrend" else 0)

    adx_val = e["adx"]
    if adx_val >= 50:     phase = "Exhaustion"
    elif adx_val >= 30:   phase = "Confirmed"
    elif adx_val >= 20:   phase = "Emerging"
    else:                 phase = "No Trend"

    if score >= 3:
        sig = {"Emerging": "Strong Buy", "Confirmed": "Buy", "Exhaustion": "Fading"}.get(phase, "Watch")
    elif score >= 1.5:
        sig = {"Emerging": "Spec. Buy", "Confirmed": "Buy", "Exhaustion": "Fading"}.get(phase, "Watch")
    elif score <= -2.5:
        sig = "Avoid"
    else:
        sig = "No Buy"

    return sig


def map_to_tiers(sig):
    """Map market-heat signals to 4 comparable tiers."""
    if sig in ("Strong Buy", "Buy"):
        return "TOP"
    elif sig in ("Spec. Buy", "Watch"):
        return "MID"
    elif sig in ("Fading", "No Buy"):
        return "LOW"
    else:
        return "AVOID"


def run():
    from backtest import _fired_stock_from_df, _stock_weighted_score

    TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

    spy_df = yf.download("SPY", period="5y", interval="1d", progress=False, auto_adjust=True)
    if isinstance(spy_df.columns, pd.MultiIndex):
        spy_df.columns = spy_df.columns.get_level_values(0)
    spy_df = spy_df.reset_index()

    hs_records = []
    mh_records = []

    for ticker in TICKERS:
        print(f"  {ticker}...", end=" ", flush=True)
        df = yf.download(ticker, period="5y", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()

        if len(df) < LOOKBACK + max(FORWARD_DAYS) + 50:
            print("skip")
            continue

        for i in range(LOOKBACK, len(df) - max(FORWARD_DAYS)):
            window = df.iloc[i - LOOKBACK:i].copy().set_index("Date")
            entry_price = float(df["Close"].iloc[i])
            fwd = {}
            for f in FORWARD_DAYS:
                fwd[f"return_{f}d"] = round((float(df["Close"].iloc[i + f]) - entry_price) / entry_price * 100, 3)

            # Market-heat
            try:
                mh_sigs = compute_market_heat_signals(window)
                mh_sig = compute_mh_signal(mh_sigs)
                mh_tier = map_to_tiers(mh_sig)
                mh_records.append({"ticker": ticker, "signal": mh_tier, **fwd})
            except Exception:
                pass

            # Heatseeker
            try:
                date_val = df["Date"].iloc[i]
                spy_slice = spy_df[spy_df["Date"] <= date_val]
                spy_window = spy_slice.iloc[-LOOKBACK:].copy().set_index("Date") if len(spy_slice) >= LOOKBACK else None
                fired = _fired_stock_from_df(window, spy_df=spy_window)
                ws = _stock_weighted_score(fired)
                hs_signal, _ = score_to_signal(ws["score"])
                hs_records.append({"ticker": ticker, "signal": hs_signal, **fwd})
            except Exception:
                pass

        print("done")

    return hs_records, mh_records


def print_ordering(name, records, tiers):
    df = pd.DataFrame(records)
    if df.empty:
        print(f"  {name}: no data")
        return
    print(f"\n  {name} ({len(df)} bars)")
    print(f"  {'Signal':<12} {'20d Avg':>8} {'20d WR':>7} {'Count':>7}")
    print(f"  {'-'*12} {'-'*8} {'-'*7} {'-'*7}")
    for sig in tiers:
        sub = df[df["signal"] == sig]["return_20d"]
        if len(sub) > 0:
            print(f"  {sig:<12} {sub.mean():>+7.2f}% {(sub > 0).mean()*100:>6.1f}% {len(sub):>7}")


if __name__ == "__main__":
    import time

    print("=" * 65)
    print("  HEATSEEKER vs MARKET-HEAT -- Mag 7 (5yr)")
    print("=" * 65)

    t0 = time.time()
    hs, mh = run()
    print(f"\n  Completed in {time.time()-t0:.0f}s")

    print_ordering("HEATSEEKER", hs, ["HOT", "BUY", "WATCH", "AVOID"])
    print_ordering("MARKET-HEAT", mh, ["TOP", "MID", "LOW", "AVOID"])

    print(f"\n{'=' * 65}")
