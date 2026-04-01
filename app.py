from flask import Flask, render_template, jsonify, request, Response, stream_with_context
from analyzer import analyze, get_cot_bias, COT_KEYWORDS
from analyzer_stocks import analyze_stock, OMXS30
from backtest import run_verify, is_etf
from cache import batch_download
import numpy as np
import pandas as pd
import json

app = Flask(__name__)

ETF_TICKERS   = [
    "SPY", "QQQ", "GLD", "SLV", "TLT", "USO",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY",
    "XLC", "XLB", "XLU", "XLRE", "SMH", "XRT", "IGV",
    "IBIT",
]
STOCK_TICKERS = list(OMXS30.keys())

US_STOCKS = {
    # Mag 7
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN":  "Amazon",
    "NVDA":  "Nvidia",
    "META":  "Meta",
    "TSLA":  "Tesla",
    # Tech / Semis / Software
    "AVGO":  "Broadcom",
    "AMD":   "AMD",
    "CRM":   "Salesforce",
    "ORCL":  "Oracle",
    "NOW":   "ServiceNow",
    "PANW":  "Palo Alto Networks",
    "PLTR":  "Palantir",
    # Consumer
    "NFLX":  "Netflix",
    "COST":  "Costco",
    "HD":    "Home Depot",
    "UBER":  "Uber",
    # Healthcare
    "LLY":   "Eli Lilly",
    "UNH":   "UnitedHealth",
    "ABBV":  "AbbVie",
    "ISRG":  "Intuitive Surgical",
    # Financials
    "V":     "Visa",
    "MA":    "Mastercard",
    "JPM":   "JPMorgan",
    "COIN":  "Coinbase",
    # Consumer Staples
    "PG":    "Procter & Gamble",
}
US_STOCK_TICKERS = list(US_STOCKS.keys())


def sanitize(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


@app.route("/")
def index():
    return render_template("base.html",
                           etf_tickers=ETF_TICKERS,
                           stock_tickers=STOCK_TICKERS,
                           us_stock_tickers=US_STOCK_TICKERS)


@app.route("/api/market")
def market_snapshot():
    tickers = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "^VIX": "VIX", "GLD": "Gold", "TLT": "US Bonds"}
    import yfinance as yf
    data = yf.download(list(tickers.keys()), period="5d", interval="1d",
                       progress=False, auto_adjust=True, group_by="ticker")
    results = []
    for ticker, name in tickers.items():
        try:
            if isinstance(data.columns, pd.MultiIndex):
                df = data[ticker].dropna(how="all")
            else:
                df = data
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            c = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            chg = round((c - prev) / prev * 100, 2)
            results.append({"ticker": ticker, "name": name, "price": round(c, 2), "change_pct": chg})
        except Exception:
            pass
    return jsonify(sanitize(results))


def _sse_json(obj):
    """Serialize to SSE data line."""
    return f"data: {json.dumps(sanitize(obj))}\n\n"


def _sse_response(generator):
    """Create a streaming SSE response with proper headers."""
    return Response(
        stream_with_context(generator()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/stream/etf")
def stream_etfs():
    def generate():
        cot_data = {t: get_cot_bias(COT_KEYWORDS[t]) for t in ETF_TICKERS if t in COT_KEYWORDS}
        for t in ETF_TICKERS:
            cot = cot_data.get(t, {"bias": "unavailable", "index": None})
            result = analyze(t, cot=cot)
            yield _sse_json(result)
        yield "data: [DONE]\n\n"
    return _sse_response(generate)


@app.route("/api/stream/stocks")
def stream_stocks():
    def generate():
        for t in STOCK_TICKERS:
            result = analyze_stock(t)
            yield _sse_json(result)
        yield "data: [DONE]\n\n"
    return _sse_response(generate)


@app.route("/api/stream/us-stocks")
def stream_us_stocks():
    def generate():
        for t in US_STOCK_TICKERS:
            result = analyze_stock(t, names=US_STOCKS, currency="USD", bench_ticker="SPY")
            yield _sse_json(result)
        yield "data: [DONE]\n\n"
    return _sse_response(generate)


@app.route("/api/analyze/etf")
def analyze_etfs():
    batch_download(ETF_TICKERS, period="1y")
    cot_data = {t: get_cot_bias(COT_KEYWORDS[t]) for t in ETF_TICKERS if t in COT_KEYWORDS}
    results = sorted([analyze(t, cot=cot_data.get(t, {"bias": "unavailable", "index": None})) for t in ETF_TICKERS],
                     key=lambda r: r.get("score", 0), reverse=True)
    return jsonify(sanitize(results))


@app.route("/api/analyze/stocks")
def analyze_stocks():
    batch_download(STOCK_TICKERS, period="1y")
    results = sorted([analyze_stock(t) for t in STOCK_TICKERS],
                     key=lambda r: r.get("score", 0), reverse=True)
    return jsonify(sanitize(results))


@app.route("/api/analyze/us-stocks")
def analyze_us_stocks():
    batch_download(US_STOCK_TICKERS + ["SPY"], period="1y")
    results = sorted([analyze_stock(t, names=US_STOCKS, currency="USD", bench_ticker="SPY")
                      for t in US_STOCK_TICKERS],
                     key=lambda r: r.get("score", 0), reverse=True)
    return jsonify(sanitize(results))


@app.route("/api/verify")
def verify_ticker():
    ticker = request.args.get("ticker", "").strip().upper()
    period = request.args.get("period", "max").strip()
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
    result = run_verify(ticker, period=period)
    return jsonify(sanitize(result))


@app.route("/api/signal")
def signal_ticker():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
    if is_etf(ticker):
        cot = get_cot_bias(COT_KEYWORDS.get(ticker, ticker))
        result = analyze(ticker, cot=cot)
        result["type"] = "etf"
    else:
        result = analyze_stock(ticker, names={}, currency="USD", bench_ticker="SPY")
        result["type"] = "stock"
    return jsonify(sanitize(result))


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
