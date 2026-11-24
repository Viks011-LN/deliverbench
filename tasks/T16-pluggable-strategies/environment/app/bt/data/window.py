"""The --start and --end options: the run keeps only the days between them (both included).

The window is applied to the raw prices, before forward fill, so a name that is missing on the first day of the
window is not filled from a price before it: for the run, history begins on the window's first day.
"""
from bt.errors import WindowError


def apply_window(dates, symbols, prices, start=None, end=None):
    """Keep the days from start to end (YYYY-MM-DD strings, either may be None). Returns (dates, prices).
    Fewer than two days left is an error."""
    if not start and not end:
        return dates, prices
    first = start or dates[0]
    last = end or dates[-1]
    keep = [i for i, day in enumerate(dates) if first <= day <= last]
    if len(keep) < 2:
        raise WindowError(f"fewer than two days between {first} and {last}")
    kept_dates = [dates[i] for i in keep]
    kept_prices = {symbol: [prices[symbol][i] for i in keep] for symbol in symbols}
    return kept_dates, kept_prices
