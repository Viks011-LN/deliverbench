"""Rolling statistics over a price series, for the scoring code.

These are the scoring code's own: the volatility scaling has its own rolling standard deviation over returns
(bt/portfolio/volatility.py), and the metrics their own mean and standard deviation (bt/metrics/returns.py).
Each adds up its numbers in its own order, and the golden files depend on every one of them.
"""
import math


def window_values(values, end, window):
    """The `window` values ending at index `end` (inclusive). The caller makes sure the window fits
    (end >= window - 1): the engine only asks after its warm-up."""
    return values[end - window + 1:end + 1]


def rolling_mean(values, end, window):
    """Mean of the `window` values ending at index `end` (inclusive), or None if one of them is missing."""
    chunk = window_values(values, end, window)
    for value in chunk:
        if value is None:
            return None
    return sum(chunk) / window


def rolling_std(values, end, window):
    """Sample standard deviation (n - 1) over the same window as rolling_mean, or None where that is None."""
    mean = rolling_mean(values, end, window)
    if mean is None:
        return None
    total = 0.0
    for i in range(end - window + 1, end + 1):
        deviation = values[i] - mean
        total += deviation * deviation
    return math.sqrt(total / (window - 1))


def zscore(value, mean, std):
    """How many standard deviations `value` lies from `mean`."""
    return (value - mean) / std
