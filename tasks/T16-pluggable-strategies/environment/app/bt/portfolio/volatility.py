"""Volatility scaling: size the book so that its estimated annual volatility meets vol_target.

Each name's volatility is the sample standard deviation of its daily returns over the last vol_window days,
newest first: the same window the risk desk's spreadsheet uses, added up in the same order, so the two agree to
the last digit when they are compared.
"""
import math

from bt.constants import TRADING_DAYS


def trailing_vol(returns, end, window):
    """Sample standard deviation (n - 1) of the `window` returns ending at index `end`, added up from the newest
    to the oldest; None if one of them is missing."""
    total = 0.0
    for i in range(end, end - window, -1):
        value = returns[i]
        if value is None:
            return None
        total += value
    mean = total / window
    squares = 0.0
    for i in range(end, end - window, -1):
        deviation = returns[i] - mean
        squares += deviation * deviation
    return math.sqrt(squares / (window - 1))


def volatility_scale(weights, vols, vol_target, max_leverage):
    """The factor that brings the book's annual volatility to vol_target, treating the names as uncorrelated,
    capped at max_leverage. 1.0 when there is no target, no book, or a volatility cannot be estimated."""
    if vol_target is None or not weights:
        return 1.0
    variance = 0.0
    for symbol in weights:
        vol = vols[symbol]
        if vol is None:
            return 1.0
        exposure = weights[symbol] * vol
        variance += exposure * exposure
    if variance == 0.0:
        return 1.0
    book_vol = math.sqrt(variance) * math.sqrt(TRADING_DAYS)
    scale = vol_target / book_vol
    if scale > max_leverage:
        scale = max_leverage
    return scale
