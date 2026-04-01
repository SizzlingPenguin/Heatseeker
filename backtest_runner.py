"""
Heatseeker Backtest Runner
──────────────────────────
Standalone script. Run from terminal:

    python backtest_runner.py           # 3-year backtest (default)
    python backtest_runner.py --years 5 # 5-year backtest
    python backtest_runner.py --csv     # also save results to backtest_results.csv
"""

import argparse
import pandas as pd
from backtest import run_all_backtests, TICKERS, FORWARD_DAYS


def fmt(val, is_pct=False):
    if val is None:
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val}{'%' if is_pct else ''}"


def print_table(summary: dict, title: str):
    signals = ["HOT", "BUY", "WATCH", "AVOID"]
    col_w   = 14

    print(f"\n{'-' * 80}")
    print(f"  {title}")
    print(f"{'-' * 80}")

    header = f"  {'Signal':<16}"
    for fwd in FORWARD_DAYS:
        header += f"  {'':>2}{fwd}d Avg{'':>2}{fwd}d Win%{'':>2}{fwd}d MaxDD"
    print(header)
    print(f"  {'-'*16}" + (f"  {'-'*8}{'-'*8}{'-'*9}" * len(FORWARD_DAYS)))

    for sig in signals:
        s = summary.get(sig)
        if not s:
            continue
        row = f"  {sig:<16}"
        for fwd in FORWARD_DAYS:
            d = s[f"{fwd}d"]
            row += f"  {fmt(d['avg_return'], True):>8}{fmt(d['win_rate'], True):>8}{fmt(d['max_dd'], True):>9}"
        print(row)


def to_csv(all_results: dict, path: str):
    rows = []
    for ticker, summary in all_results["by_ticker"].items():
        if "error" in summary:
            continue
        for sig, periods in summary.items():
            for fwd, stats in periods.items():
                rows.append({
                    "ticker": ticker, "signal": sig, "period": fwd,
                    **stats
                })
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"\n  Results saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Heatseeker Backtest Runner")
    parser.add_argument("--years", type=int, default=3, help="Lookback years (default: 3)")
    parser.add_argument("--csv",   action="store_true",  help="Save results to CSV")
    args = parser.parse_args()

    print(f"\n  HEATSEEKER BACKTEST - {args.years} year{'s' if args.years > 1 else ''}")
    print(f"  Tickers: {', '.join(TICKERS)}")
    print(f"  Signals: 8/10 (COT and Max Pain excluded - no free historical data)")
    print(f"  Running... this takes ~30 seconds\n")

    results = run_all_backtests(years=args.years)

    if results.get("error"):
        print(f"  ERROR: {results['error']}")
        return

    print_table(results["overall"], "OVERALL - All Tickers Combined")

    for ticker in TICKERS:
        summary = results["by_ticker"].get(ticker, {})
        if "error" in summary:
            print(f"\n  {ticker}: {summary['error']}")
        else:
            print_table(summary, ticker)

    if args.csv:
        to_csv(results, "backtest_results.csv")

    print(f"\n{'-' * 80}\n")


if __name__ == "__main__":
    main()
