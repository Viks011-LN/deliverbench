"""What a price file holds, name by name: python -m bt.tools.prices_info PRICES.csv [--max-fill-gap N]

One line per symbol: its first and last price date, how many prices it has, how many days are missing after its
first price, its longest gap, how many gaps are longer than the fill gap (each would force a sale), its last price
and its annualised volatility (the sample standard deviation of its day-on-day returns, over the days that have
both prices). Errors in the file are reported as `python -m bt` reports them.
"""
import argparse
import math
import sys

from bt.data.prices import load_prices
from bt.data.quality import missing_runs
from bt.data.series import simple_returns
from bt.errors import BacktestError
from bt.metrics.returns import sample_std

TRADING_DAYS = 252
HEADER = f"{'symbol':<8}{'first':>12}{'last':>12}{'prices':>8}{'missing':>9}{'longest':>9}{'beyond':>8}" \
         f"{'last price':>12}{'vol':>9}"


def describe(dates, symbol, series, max_gap):
    """The facts about one symbol's series, as a dict."""
    seen = [i for i, value in enumerate(series) if value is not None]
    if not seen:
        return {"symbol": symbol, "first": None, "last": None, "prices": 0, "missing": 0, "longest": 0,
                "beyond": 0, "last_price": None, "vol": None}
    runs = missing_runs(series)
    lengths = [last - first + 1 for first, last in runs]
    returns = [r for r in simple_returns(series) if r is not None]
    return {
        "symbol": symbol,
        "first": dates[seen[0]],
        "last": dates[seen[-1]],
        "prices": len(seen),
        "missing": sum(lengths),
        "longest": max(lengths) if lengths else 0,
        "beyond": sum(1 for length in lengths if length > max_gap),
        "last_price": series[seen[-1]],
        "vol": sample_std(returns) * math.sqrt(TRADING_DAYS) if len(returns) >= 2 else None,
    }


def line(facts):
    vol = "n/a" if facts["vol"] is None else f"{facts['vol'] * 100:.1f}%"
    price = "n/a" if facts["last_price"] is None else f"{facts['last_price']:.2f}"
    return (f"{facts['symbol']:<8}{facts['first'] or '-':>12}{facts['last'] or '-':>12}{facts['prices']:>8}"
            f"{facts['missing']:>9}{facts['longest']:>9}{facts['beyond']:>8}{price:>12}{vol:>9}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.prices_info", description="Describe a price file.")
    parser.add_argument("prices")
    parser.add_argument("--max-fill-gap", type=int, default=5, help="the fill gap to count longer gaps against")
    args = parser.parse_args(argv)
    try:
        dates, symbols, prices = load_prices(args.prices)
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    print(f"{args.prices}: {len(dates)} days from {dates[0]} to {dates[-1]}, {len(symbols)} symbols")
    print(HEADER)
    for symbol in symbols:
        print(line(describe(dates, symbol, prices[symbol], args.max_fill_gap)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
