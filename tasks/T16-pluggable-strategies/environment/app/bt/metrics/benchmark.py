"""The book against its benchmark (the `benchmark` setting): docs/metrics.md defines each figure.

The benchmark's closes are forward-filled as the stocks' are (at most max_fill_gap days). The daily figures pair
the book's return on each day with the benchmark's, on the days the benchmark has a return; every sum below adds
up those pairs oldest first.
"""
import math

from bt.data.series import forward_fill, simple_returns
from bt.metrics.ratios import TRADING_DAYS
from bt.metrics.returns import daily_returns, mean


def total_return(series):
    """From the benchmark's first close in the period to its last; None if it has fewer than two."""
    closes = [value for value in series if value is not None]
    if len(closes) < 2:
        return None
    return closes[-1] / closes[0] - 1.0


def paired_returns(curve, benchmark_returns):
    """(book's returns, benchmark's returns) on the days both exist, oldest first."""
    book = daily_returns(curve)
    ours, theirs = [], []
    for i, r in enumerate(book, start=1):
        b = benchmark_returns[i]
        if b is not None:
            ours.append(r)
            theirs.append(b)
    return ours, theirs


def covariance(xs, ys):
    """Sample covariance (n - 1)."""
    mx = mean(xs)
    my = mean(ys)
    total = 0.0
    for x, y in zip(xs, ys):
        total += (x - mx) * (y - my)
    return total / (len(xs) - 1)


def capture(ours, theirs, up):
    """Up (or down) capture: the book's mean return over the benchmark's on the days the benchmark rose (fell).
    None if there are no such days or the benchmark's mean is 0."""
    days = [(r, b) for r, b in zip(ours, theirs) if (b > 0.0 if up else b < 0.0)]
    if not days:
        return None
    theirs_mean = mean([b for _, b in days])
    if theirs_mean == 0.0:
        return None
    return mean([r for r, _ in days]) / theirs_mean


def benchmark_metrics(curve, series, config, book_total_return):
    """The benchmark section of the report, in print order."""
    returns = simple_returns(forward_fill(series, config["max_fill_gap"]))
    ours, theirs = paired_returns(curve, returns)
    bench_total = total_return(series)
    figures = {
        "symbol": config["benchmark"],
        "total_return": bench_total,
        "excess_return": book_total_return - bench_total if bench_total is not None else None,
        "beta": None,
        "correlation": None,
        "tracking_error": None,
        "information_ratio": None,
        "up_capture": capture(ours, theirs, True),
        "down_capture": capture(ours, theirs, False),
        "days": len(ours),
    }
    if len(ours) < 2:
        return figures
    variance = covariance(theirs, theirs)
    cov = covariance(ours, theirs)
    if variance > 0.0:
        figures["beta"] = cov / variance
        own = covariance(ours, ours)
        if own > 0.0:
            figures["correlation"] = cov / (math.sqrt(own) * math.sqrt(variance))
    active = [r - b for r, b in zip(ours, theirs)]
    spread = covariance(active, active)
    if spread > 0.0:
        figures["tracking_error"] = math.sqrt(spread) * math.sqrt(TRADING_DAYS)
        figures["information_ratio"] = mean(active) * TRADING_DAYS / figures["tracking_error"]
    return figures
