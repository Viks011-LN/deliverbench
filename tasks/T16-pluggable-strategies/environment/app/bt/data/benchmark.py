"""The benchmark column.

With the `benchmark` setting, one column of the price file is the benchmark (an index the book is measured
against) rather than a stock: it is split off right after the prices are read and the --start/--end window is
applied, so the engine never sees it, never scores it and never trades it. The report then compares the book with
it (bt/metrics/benchmark.py).
"""
from bt.errors import BacktestError


def split_benchmark(prices_path, config, symbols, prices):
    """(traded symbols, their prices, the benchmark's raw prices or None). The benchmark must be a column of the
    price file, and at least one other column must be left to trade."""
    name = config["benchmark"]
    if name is None:
        return symbols, prices, None
    if name not in symbols:
        raise BacktestError(f"benchmark {name!r} is not a column of {prices_path}")
    traded = [symbol for symbol in symbols if symbol != name]
    if not traded:
        raise BacktestError(f"{prices_path}: no column to trade besides the benchmark {name!r}")
    return traded, {symbol: prices[symbol] for symbol in traded}, prices[name]
