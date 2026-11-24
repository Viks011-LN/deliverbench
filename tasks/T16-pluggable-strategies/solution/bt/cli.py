"""The command line: python -m bt (README.md documents every option).

Reads the price file and the config, applies --start/--end, splits off the benchmark column (if the config names
one), warns on stderr about gaps in the prices, runs the backtest and prints the JSON report (or, with --format,
the text summary or the HTML page) on stdout. With --equity it also writes the daily equity curve, and with --trades the trade log.
Problems with the inputs are reported on stderr as "error: ..." with exit status 2, and then nothing is printed
on stdout and no file is written.
"""
import argparse
import json
import sys

from bt.config import load_config
from bt.constants import OUTPUT_FORMATS
from bt.data import apply_window, load_prices
from bt.data.benchmark import split_benchmark
from bt.data.quality import gap_warnings
from bt.engine import run_backtest
from bt.errors import BacktestError
from bt.metrics import compute_metrics
from bt.metrics.benchmark import benchmark_metrics
from bt.report import build_report, render_html, render_summary, write_equity_curve, write_trade_log


def build_parser():
    parser = argparse.ArgumentParser(prog="python -m bt",
                                     description="Backtest a cross-sectional equity strategy on daily closes.")
    parser.add_argument("--prices", required=True, help="CSV of daily closing prices")
    parser.add_argument("--config", required=True, help="JSON config (README.md lists every setting)")
    parser.add_argument("--equity", help="also write the daily equity curve to this CSV file")
    parser.add_argument("--trades", help="also write the trade log to this CSV file")
    parser.add_argument("--start", help="first date to use (YYYY-MM-DD)")
    parser.add_argument("--end", help="last date to use (YYYY-MM-DD)")
    parser.add_argument("--format", choices=OUTPUT_FORMATS, default="json",
                        help="json: the full report (default); text: a one-page summary; html: the summary "
                             "as a web page")
    return parser


def run(args, out, err):
    """Do the work of one command line. Raises BacktestError or OSError on a problem with the inputs."""
    dates, symbols, prices = load_prices(args.prices)
    config = load_config(args.config)
    dates, prices = apply_window(dates, symbols, prices, args.start, args.end)
    symbols, prices, benchmark_prices = split_benchmark(args.prices, config, symbols, prices)
    for line in gap_warnings(dates, symbols, prices, config["max_fill_gap"]):
        print(line, file=err)
    result = run_backtest(dates, symbols, prices, config)
    metrics = compute_metrics(result["curve"], result["stats"], config)
    benchmark = None
    if benchmark_prices is not None:
        benchmark = benchmark_metrics(result["curve"], benchmark_prices, config, metrics["total_return"])
    if args.format == "text":
        out.write(render_summary(dates, config, result, metrics, benchmark))
    elif args.format == "html":
        out.write(render_html(dates, config, result, metrics, benchmark))
    else:
        print(json.dumps(build_report(dates, symbols, config, result, metrics, benchmark), indent=2), file=out)
    if args.equity:
        write_equity_curve(args.equity, result["curve"])
    if args.trades:
        write_trade_log(args.trades, result["trades"])


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        run(args, sys.stdout, sys.stderr)
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    return 0
