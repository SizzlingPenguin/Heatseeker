from flask import Flask, render_template, jsonify, request
from analyzer import analyze, get_cot_bias, COT_KEYWORDS
from analyzer_stocks import analyze_stock, OMXS30
from backtest import run_verify
import numpy as np

app = Flask(__name__)

ETF_TICKERS   = ["SPY", "QQQ", "GLD", "SLV", "TLT", "USO"]
STOCK_TICKERS = list(OMXS30.keys())

US_STOCKS = {
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN":  "Amazon",
    "NVDA":  "Nvidia",
    "META":  "Meta",
    "TSLA":  "Tesla",
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


@app.route("/api/analyze/etf")
def analyze_etfs():
    cot_data = {t: get_cot_bias(COT_KEYWORDS.get(t, t)) for t in ETF_TICKERS}
    results = [analyze(t, cot=cot_data[t]) for t in ETF_TICKERS]
    return jsonify(sanitize(results))


@app.route("/api/analyze/stocks")
def analyze_stocks():
    results = [analyze_stock(t) for t in STOCK_TICKERS]
    return jsonify(sanitize(results))


@app.route("/api/analyze/us-stocks")
def analyze_us_stocks():
    results = [analyze_stock(t, names=US_STOCKS, currency="USD", bench_ticker="SPY")
               for t in US_STOCK_TICKERS]
    return jsonify(sanitize(results))


@app.route("/api/verify")
def verify_ticker():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
    result = run_verify(ticker)
    return jsonify(sanitize(result))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
