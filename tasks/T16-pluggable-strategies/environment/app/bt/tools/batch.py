"""Several configs on one price file: python -m bt.tools.batch --prices P.csv CONFIG.json [CONFIG.json ...]

One line per config, in the order given: the config's file name, total return, annual volatility, Sharpe, max
drawdown and trades. A config that `python -m bt` would refuse gets its message on its line instead, and the batch
goes on. Each run is exactly that of `python -m bt --prices P.csv --config CONFIG.json`.

Exit status: 0 if every config ran, 1 if any was refused, 2 if the price file cannot be read.
"""
import argparse
import os
import sys

from bt.config import load_config
from bt.data import load_prices
from bt.data.benchmark import split_benchmark
from bt.engine import run_backtest
from bt.errors import BacktestError
from bt.metrics import compute_metrics
from bt.report.formatting import percent, ratio

HEADER = f"{'config':<28}{'return':>10}{'vol':>10}{'sharpe':>8}{'max dd':>10}{'trades':>8}"


def run_config(path, prices_path, dates, symbols, prices):
    """(line, ran) for one config."""
    name = os.path.basename(path)
    try:
        config = load_config(path)
        traded, traded_prices, _ = split_benchmark(prices_path, config, symbols, prices)
    except BacktestError as exc:
        return f"{name:<28}refused: {exc}", False
    except OSError as exc:
        return f"{name:<28}refused: cannot open {exc.filename}: {exc.strerror}", False
    result = run_backtest(dates, traded, traded_prices, config)
    m = compute_metrics(result["curve"], result["stats"], config)
    return (f"{name:<28}{percent(m['total_return']):>10}{percent(m['annual_volatility']):>10}"
            f"{ratio(m['sharpe']):>8}{percent(m['max_drawdown']):>10}{m['trades']:>8}"), True


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.batch", description="Run several configs.")
    parser.add_argument("--prices", required=True)
    parser.add_argument("configs", nargs="+")
    args = parser.parse_args(argv)
    try:
        dates, symbols, prices = load_prices(args.prices)
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    print(HEADER)
    every_one_ran = True
    for path in args.configs:
        line, ran = run_config(path, args.prices, dates, symbols, prices)
        print(line)
        every_one_ran = every_one_ran and ran
    return 0 if every_one_ran else 1


if __name__ == "__main__":
    sys.exit(main())
