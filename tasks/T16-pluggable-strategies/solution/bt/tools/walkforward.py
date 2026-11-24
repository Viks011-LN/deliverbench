"""One config, year by year: python -m bt.tools.walkforward --prices P.csv --config C.json [--min-days N]

Runs the config separately on each calendar year of the price file, as `python -m bt` would with --start and --end
set to that year's first and last day, so each year starts from the initial capital and has its own warm-up. One
line per year: its days, total return, annual volatility, Sharpe, max drawdown and trades. Years with fewer than
--min-days days (default 20) are skipped and say so.
"""
import argparse
import sys

from bt.config import load_config
from bt.data import apply_window, load_prices
from bt.data.benchmark import split_benchmark
from bt.engine import run_backtest
from bt.errors import BacktestError
from bt.metrics import compute_metrics
from bt.report.formatting import percent, ratio


def years_of(dates):
    """(year, first day, last day) for each calendar year of the dates, oldest first."""
    years = []
    for day in dates:
        year = day[:4]
        if years and years[-1][0] == year:
            years[-1] = (year, years[-1][1], day)
        else:
            years.append((year, day, day))
    return years


def year_line(year, first, last, dates, symbols, prices, prices_path, config, min_days):
    count = dates.index(last) - dates.index(first) + 1
    if count < max(min_days, 2):
        return f"{year}  {count:>4} days: skipped"
    days, kept = apply_window(dates, symbols, prices, first, last)
    traded, traded_prices, _ = split_benchmark(prices_path, config, symbols, kept)
    result = run_backtest(days, traded, traded_prices, config)
    m = compute_metrics(result["curve"], result["stats"], config)
    return (f"{year}  {len(days):>4} days{percent(m['total_return']):>10}{percent(m['annual_volatility']):>10}"
            f"{ratio(m['sharpe']):>8}{percent(m['max_drawdown']):>10}{m['trades']:>8}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.walkforward", description="Run a config year by year.")
    parser.add_argument("--prices", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--min-days", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        dates, symbols, prices = load_prices(args.prices)
        config = load_config(args.config)
        print(f"{'year':<6}{'days':>9}{'return':>10}{'vol':>10}{'sharpe':>8}{'max dd':>10}{'trades':>8}")
        for year, first, last in years_of(dates):
            print(year_line(year, first, last, dates, symbols, prices, args.prices, config, args.min_days))
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
