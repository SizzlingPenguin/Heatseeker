"""Compare Heatseeker combined score vs individual signals."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import yfinance as yf
from analyzer import compute_adx, compute_macd, compute_obv, compute_delta_volume, compute_rsi
from backtest import _fired_stock_from_df, _stock_weighted_score, LOOKBACK, FORWARD_DAYS
from analyzer import score_to_signal

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

spy_df = yf.download("SPY", period="5y", interval="1d", progress=False, auto_adjust=True)
if isinstance(spy_df.columns, pd.MultiIndex):
    spy_df.columns = spy_df.columns.get_level_values(0)
spy_df = spy_df.reset_index()

records = []

for ticker in TICKERS:
    print(f"  {ticker}...", end=" ", flush=True)
    df = yf.download(ticker, period="5y", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    if len(df) < LOOKBACK + 20 + 10:
        print("skip")
        continue

    for i in range(LOOKBACK, len(df) - 20):
        window = df.iloc[i - LOOKBACK:i].copy().set_index("Date")
        date_val = df["Date"].iloc[i]
        spy_slice = spy_df[spy_df["Date"] <= date_val]
        spy_window = spy_slice.iloc[-LOOKBACK:].copy().set_index("Date") if len(spy_slice) >= LOOKBACK else None

        fired = _fired_stock_from_df(window, spy_df=spy_window)
        ws = _stock_weighted_score(fired)
        sig, _ = score_to_signal(ws["score"])

        fwd20 = round((float(df["Close"].iloc[i + 20]) - float(df["Close"].iloc[i])) / float(df["Close"].iloc[i]) * 100, 3)
        row = {"signal": sig, "return_20d": fwd20}
        for k, v in fired.items():
            if v is not None:
                row[k] = v
        records.append(row)
    print("done")

rdf = pd.DataFrame(records)

print(f"\n{'=' * 75}")
print(f"  COMBINED ALGO vs INDIVIDUAL SIGNALS -- Mag 7 (5yr, {len(rdf)} bars)")
print(f"{'=' * 75}")

# Combined algo
print(f"\n  COMBINED ALGO (weighted score)")
print(f"  {'Tier':<8} {'Avg 20d':>8} {'Win%':>7} {'Count':>7}")
print(f"  {'-'*8} {'-'*8} {'-'*7} {'-'*7}")
for sig in ["HOT", "BUY", "WATCH", "AVOID"]:
    sub = rdf[rdf["signal"] == sig]["return_20d"]
    if len(sub) > 0:
        print(f"  {sig:<8} {sub.mean():>+7.2f}% {(sub > 0).mean()*100:>6.1f}% {len(sub):>7}")

# Spread
buy = rdf[rdf["signal"] == "BUY"]["return_20d"]
avoid = rdf[rdf["signal"] == "AVOID"]["return_20d"]
combo_spread = buy.mean() - avoid.mean() if len(buy) > 0 and len(avoid) > 0 else 0
combo_wr = (buy > 0).mean() * 100 if len(buy) > 0 else 0

# Individual signals
print(f"\n  INDIVIDUAL SIGNALS (True vs False)")
print(f"  {'Signal':<22} {'ON Avg':>8} {'ON WR':>7} {'OFF Avg':>8} {'OFF WR':>7} {'Edge':>7} {'N_on':>7}")
print(f"  {'-'*22} {'-'*8} {'-'*7} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")

signal_edges = []
for col in ["relative_strength", "adx_setup", "golden_cross", "rsi_momentum",
            "above_sma200", "fast_cross", "macd", "obv", "delta_volume"]:
    if col not in rdf.columns:
        continue
    on = rdf[rdf[col] == True]["return_20d"]
    off = rdf[rdf[col] == False]["return_20d"]
    if len(on) > 0 and len(off) > 0:
        edge = on.mean() - off.mean()
        signal_edges.append((col, edge))
        print(f"  {col:<22} {on.mean():>+7.2f}% {(on>0).mean()*100:>6.1f}% {off.mean():>+7.2f}% {(off>0).mean()*100:>6.1f}% {edge:>+6.2f}% {len(on):>7}")

print(f"\n  SUMMARY")
print(f"  {'-'*50}")
print(f"  Combined algo BUY tier:  avg={buy.mean():+.2f}%  wr={combo_wr:.1f}%")
print(f"  Combined algo spread:    {combo_spread:+.2f}% (BUY - AVOID)")
best_sig = max(signal_edges, key=lambda x: x[1])
print(f"  Best individual signal:  {best_sig[0]} edge={best_sig[1]:+.2f}%")
print(f"  Combined beats best individual: {'YES' if combo_spread > best_sig[1] else 'NO'}")
print(f"\n{'=' * 75}")
