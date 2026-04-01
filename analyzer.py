import numpy as np
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime

# ── SIGNAL WEIGHTS (must sum to 1.0) ──────────────────────────────────────
# Backtested over 3 years across SPY/QQQ/GLD/SLV/TLT/USO.
# Removed: volume_profile (neg edge), fvg (noise), quarter_end (always on).
# Added: rsi_regime (+0.56% edge), above_sma200 (+0.49% edge).
WEIGHTS = {
    "cot":            0.20,  # regulatory data, not spoofable
    "adx":            0.18,  # strongest backtested edge (+0.44%)
    "golden_cross":   0.12,  # +0.54% edge when combined with trend
    "max_pain":       0.12,  # mechanically enforced near expiry
    "rsi_regime":     0.12,  # RSI < 30 = bullish mean reversion
    "above_sma200":   0.10,  # simple regime filter, +0.49% edge
    "macd":           0.06,  # noisy but useful trigger
    "obv":            0.05,  # volume confirmation
    "delta_volume":   0.05,  # approximation without tick data
}

SIGNAL_THRESHOLDS = {
    "strong_buy": 0.80,
    "watch":      0.60,
    "no_trade":   0.40,
}

COT_KEYWORDS = {
    "SPY": "S&P 500",
    "QQQ": "NASDAQ",
    "GLD": "GOLD",
    "SLV": "SILVER",
    "TLT": "U.S. TREASURY BONDS",
    "USO": "CRUDE OIL",
}


# ── LAYER 1: INSTITUTIONAL FOOTPRINT ──────────────────────────────────────

def get_volume_profile(df: pd.DataFrame, bins: int = 20) -> dict:
    if df["High"].max() == df["Low"].min():
        c = float(df["Close"].iloc[-1])
        return {"poc": c, "vah": c, "val": c}
    df = df.copy()
    df["price_bin"] = pd.cut(df["Close"], bins=bins)
    profile = df.groupby("price_bin", observed=True)["Volume"].sum()
    poc_bin = profile.idxmax()
    poc = (poc_bin.left + poc_bin.right) / 2
    target = profile.sum() * 0.70
    cumulative, value_area_bins = 0, []
    for bin_, vol in profile.sort_values(ascending=False).items():
        cumulative += vol
        value_area_bins.append(bin_)
        if cumulative >= target:
            break
    return {
        "poc": round(float(poc), 2),
        "vah": round(float(max(b.right for b in value_area_bins)), 2),
        "val": round(float(min(b.left for b in value_area_bins)), 2),
    }


def get_fair_value_gaps(df: pd.DataFrame, count: int = 3) -> list:
    fvgs = []
    for i in range(2, len(df)):
        if df["Low"].iloc[i] > df["High"].iloc[i - 2]:
            fvgs.append({"type": "bullish", "level": round((df["Low"].iloc[i] + df["High"].iloc[i - 2]) / 2, 2)})
        elif df["High"].iloc[i] < df["Low"].iloc[i - 2]:
            fvgs.append({"type": "bearish", "level": round((df["High"].iloc[i] + df["Low"].iloc[i - 2]) / 2, 2)})
    return fvgs[-count:] if fvgs else []


def get_max_pain(ticker: str) -> float | None:
    try:
        tk = yf.Ticker(ticker)
        expirations = tk.options
        if not expirations:
            return None
        chain = tk.option_chain(expirations[0])
        calls = chain.calls[["strike", "openInterest"]]
        puts = chain.puts[["strike", "openInterest"]]
        strikes = sorted(set(calls["strike"]).union(set(puts["strike"])))
        pain = {
            s: ((s - calls[calls["strike"] <= s]["strike"]) * calls[calls["strike"] <= s]["openInterest"]).sum()
             + ((puts[puts["strike"] >= s]["strike"] - s) * puts[puts["strike"] >= s]["openInterest"]).sum()
            for s in strikes
        }
        return round(min(pain, key=pain.get), 2)
    except Exception:
        return None


_cot_cache: dict = {}   # {keyword: (timestamp, result)}
COT_CACHE_TTL = 3600    # 1 hour — data only updates weekly on Fridays


def get_cot_bias(symbol_keyword: str) -> dict:
    import time
    now = time.time()
    cached = _cot_cache.get(symbol_keyword)
    if cached and now - cached[0] < COT_CACHE_TTL:
        return cached[1]

    from curl_cffi import requests as cffi_requests
    url = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json"
    params = {
        "$where": f"market_and_exchange_names like '%{symbol_keyword}%'",
        "$limit": 10,
        "$order": "report_date_as_yyyy_mm_dd DESC",
    }
    try:
        r = cffi_requests.get(url, params=params, timeout=10, impersonate="chrome")
        records = r.json()
        if not records:
            result = {"bias": "unavailable", "index": None}
        else:
            nets = [
                int(x.get("noncomm_positions_long_all", 0)) - int(x.get("noncomm_positions_short_all", 0))
                for x in records
            ]
            net = nets[0]
            mn, mx = min(nets), max(nets)
            index = round((net - mn) / (mx - mn) * 100) if mx != mn else 50
            result = {"bias": "bullish" if index > 60 else "bearish" if index < 40 else "neutral", "index": index}
    except Exception:
        result = {"bias": "unavailable", "index": None}

    _cot_cache[symbol_keyword] = (now, result)
    return result


def is_quarter_end_risk() -> bool:
    today = datetime.today()
    ends = [datetime(today.year, m, 1) for m in [4, 7, 10]] + [datetime(today.year + 1, 1, 1)]
    return any(0 <= (e - today).days <= 14 for e in ends)


# ── LAYER 2: TREND & MOMENTUM ──────────────────────────────────────────────

def compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    up, down = h.diff(), -l.diff()
    plus_di  = 100 * up.where((up > down) & (up > 0), 0.0).ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * down.where((down > up) & (down > 0), 0.0).ewm(span=period, adjust=False).mean() / atr
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    return round(dx.ewm(span=period, adjust=False).mean().iloc[-1], 2)


def compute_macd(df: pd.DataFrame) -> dict:
    c = df["Close"]
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    above = macd > signal
    # days since last crossover
    days_since = 0
    for i in range(len(above) - 1, 0, -1):
        if above.iloc[i] == above.iloc[i - 1]:
            days_since += 1
        else:
            break
    return {
        "crossed_bullish": bool(macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]),
        "bullish": bool(macd.iloc[-1] > signal.iloc[-1]),
        "macd": round(float(macd.iloc[-1]), 4),
        "signal": round(float(signal.iloc[-1]), 4),
        "days_since_cross": days_since,
    }


def compute_obv(df: pd.DataFrame) -> dict:
    obv = (np.sign(df["Close"].diff()) * df["Volume"]).fillna(0).cumsum()
    rising = bool(obv.iloc[-1] > obv.iloc[-5])
    return {"rising": rising, "distribution_warning": bool(df["Close"].iloc[-1] > df["Close"].iloc[-5] and not rising)}


def compute_delta_volume(df: pd.DataFrame) -> bool:
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    buy_vol = df["Volume"] * ((df["Close"] - df["Low"]) / rng)
    return bool((buy_vol - (df["Volume"] - buy_vol)).fillna(0).iloc[-5:].sum() > 0)


def days_since_cross(series_a: pd.Series, series_b: pd.Series) -> int:
    """Returns how many consecutive days series_a has been above/below series_b."""
    above = series_a > series_b
    count = 0
    for i in range(len(above) - 1, 0, -1):
        if above.iloc[i] == above.iloc[i - 1]:
            count += 1
        else:
            break
    return count


# ── BOTTOM WATCH (isolated, does not affect scoring) ──────────────────────

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.where(delta < 0, 0.0)).ewm(span=period, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_bottom_watch(df: pd.DataFrame, vp: dict, cot_index: int | None, adx: float) -> dict:
    close = df["Close"]
    low   = df["Low"]
    current_price = float(close.iloc[-1])

    # 1. Price at or below VAL
    at_val = current_price <= vp["val"] * 1.02

    # 2. RSI divergence: price lower low, RSI higher low over last 20 bars
    rsi = compute_rsi(close)
    window = 20
    price_ll = float(close.iloc[-1]) < float(close.iloc[-window:].min()) * 1.01
    rsi_hl   = float(rsi.iloc[-1]) > float(rsi.iloc[-window:-1].min())
    rsi_divergence = price_ll and rsi_hl
    rsi_value = round(float(rsi.iloc[-1]), 1)
    rsi_oversold = rsi_value < 35

    # 3. OBV divergence: price lower low, OBV not confirming
    obv = (np.sign(close.diff()) * df["Volume"]).fillna(0).cumsum()
    obv_divergence = bool(
        float(close.iloc[-1]) < float(close.iloc[-window]) and
        float(obv.iloc[-1])   > float(obv.iloc[-window])
    )

    # 4. ATR exhaustion: ATR spiked then contracted
    h, l, c = df["High"], df["Low"], close
    tr  = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    atr_spike       = float(atr.iloc[-10:-5].max())
    atr_now         = float(atr.iloc[-1])
    atr_exhaustion  = atr_now < atr_spike * 0.80  # contracted 20%+ from recent spike

    # 5. ADX weakening: trend losing strength
    adx_weakening = adx < 25

    # 6. COT extreme: large specs maximally short
    cot_extreme = cot_index is not None and cot_index < 15

    signals = {
        "price_at_val":    at_val,
        "rsi_divergence":  rsi_divergence,
        "rsi_oversold":    rsi_oversold,
        "obv_divergence":  obv_divergence,
        "atr_exhaustion":  atr_exhaustion,
        "adx_weakening":   adx_weakening,
        "cot_extreme":     cot_extreme,
    }

    fired_count = sum(1 for v in signals.values() if v)
    total       = len(signals)

    if fired_count >= 5:
        label, label_class = "HIGH PROBABILITY BOTTOM", "bottom-high"
    elif fired_count >= 3:
        label, label_class = "POSSIBLE BOTTOM", "bottom-possible"
    else:
        label, label_class = "NO BOTTOM SIGNAL", "bottom-none"

    return {
        "label":       label,
        "label_class": label_class,
        "score":       f"{fired_count}/{total}",
        "rsi":         rsi_value,
        "signals":     signals,
    }


# ── WEIGHTED SCORE ENGINE ──────────────────────────────────────────────────

def weighted_score(fired: dict) -> dict:
    """
    fired: {signal_name: True/False/None}
    None = signal unavailable, excluded from scoring and weight redistributed.
    Returns score 0.0–1.0 and per-signal breakdown.
    """
    available = {k: v for k, v in fired.items() if v is not None}
    unavailable = {k for k, v in fired.items() if v is None}

    total_available_weight = sum(WEIGHTS[k] for k in available)
    if total_available_weight == 0:
        return {"score": 0.0, "pct": 0, "unavailable": list(unavailable)}

    score = sum(WEIGHTS[k] / total_available_weight for k, v in available.items() if v is True)
    return {
        "score": round(score, 4),
        "pct": round(score * 100, 1),
        "unavailable": sorted(unavailable),
        "available_count": len(available),
        "total_signals": len(fired),
    }


def score_to_signal(score: float) -> tuple[str, str]:
    if score >= SIGNAL_THRESHOLDS["strong_buy"]:
        return "STRONG BUY", "strong-buy"
    if score >= SIGNAL_THRESHOLDS["watch"]:
        return "WATCH", "watch"
    if score >= SIGNAL_THRESHOLDS["no_trade"]:
        return "NO TRADE", "no-trade"
    return "AVOID", "avoid"


# ── PUBLIC API ─────────────────────────────────────────────────────────────

def analyze(ticker: str, cot: dict | None = None) -> dict:
    df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
    if df.empty or len(df) < 30:
        return {"ticker": ticker, "error": "Insufficient data"}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = float(df["Close"].iloc[-1])
    vp    = get_volume_profile(df)
    fvgs  = get_fair_value_gaps(df)
    max_pain = get_max_pain(ticker)
    if cot is None:
        cot = get_cot_bias(COT_KEYWORDS.get(ticker, ticker))
    qe    = is_quarter_end_risk()

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

    # vectorized ADX streak using +DI vs -DI direction as proxy
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

    fired = {
        "cot":            (True if cot["bias"] == "bullish" else False) if cot["bias"] != "unavailable" else None,
        "max_pain":       (abs(close - max_pain) / close < 0.02) if max_pain else None,
        "adx":            adx_confirmed,
        "golden_cross":   golden_cross,
        "rsi_regime":     rsi_value < 30,
        "above_sma200":   above_sma,
        "macd":           macd["crossed_bullish"],
        "obv":            obv["rising"],
        "delta_volume":   delta,
    }

    ws = weighted_score(fired)
    signal, signal_class = score_to_signal(ws["score"])
    bottom = compute_bottom_watch(df, vp, cot["index"], adx)

    return {
        "ticker": ticker,
        "price": round(close, 2),
        "signal": signal,
        "signal_class": signal_class,
        "score": ws["score"],
        "score_pct": ws["pct"],
        "unavailable_signals": ws["unavailable"],
        "available_signals": ws["available_count"],
        "fired": fired,
        "institutional": {
            "poc": vp["poc"], "vah": vp["vah"], "val": vp["val"],
            "max_pain": max_pain,
            "cot_bias": cot["bias"], "cot_index": cot["index"],
            "quarter_end_risk": qe,
            "fvgs": fvgs[-2:] if fvgs else [],
        },
        "trend": {
            "adx": adx, "adx_confirmed": adx_confirmed, "days_adx": days_adx,
            "golden_cross": golden_cross, "days_golden": days_golden,
            "fast_cross": fast_cross, "days_fast": days_fast,
            "macd_bullish": macd["bullish"], "macd_crossed": macd["crossed_bullish"], "days_macd": macd["days_since_cross"],
            "obv_rising": obv["rising"],
            "distribution_warning": obv["distribution_warning"],
            "delta_positive": delta,
            "rsi": rsi_value,
            "above_sma200": above_sma,
            "sma20": round(float(sma20.iloc[-1]), 2),
            "sma50": round(float(sma50.iloc[-1]), 2),
            "sma200": round(float(sma200.iloc[-1]), 2),
        },
        "levels": {
            "entry_zone": f"${vp['val']} – ${vp['poc']}",
            "target": f"${vp['vah']}",
            "invalidation": f"${round(vp['val'] * 0.99, 2)}",
        },
        "bottom_watch": bottom,
        "error": None,
    }
