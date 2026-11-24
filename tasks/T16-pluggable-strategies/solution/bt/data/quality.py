"""Warnings about the price file, printed on stderr before a run.

They do not stop the run. The desk reads them because a gap longer than max_fill_gap forces the sale of a
position at its last price, and a name with no price at all can never be held.
"""


def missing_runs(series):
    """(first index, last index) of every run of missing values after the first price, in order."""
    runs = []
    seen_price = False
    start = None
    for i, value in enumerate(series):
        if value is None:
            if seen_price and start is None:
                start = i
        else:
            if start is not None:
                runs.append((start, i - 1))
                start = None
            seen_price = True
    if start is not None:
        runs.append((start, len(series) - 1))
    return runs


def gap_warnings(dates, symbols, prices, max_gap):
    """One line per symbol with no price in the period, and per gap longer than max_gap, in symbol order."""
    lines = []
    for symbol in symbols:
        series = prices[symbol]
        if all(value is None for value in series):
            lines.append(f"warning: {symbol} has no price in the period")
            continue
        for first, last in missing_runs(series):
            days = last - first + 1
            if days > max_gap:
                lines.append(f"warning: {symbol} has no price from {dates[first]} to {dates[last]} "
                             f"({days} days, more than max_fill_gap)")
    return lines
