"""Price series: forward fill and day-on-day returns.

A series is a list aligned with the run's dates; None marks a missing value.
"""


def forward_fill(series, max_gap):
    """Carry the last price forward over at most max_gap missing days in a row; longer gaps stay missing (None)
    from the first day beyond max_gap until the next real price. Before the first price, nothing is filled."""
    filled = []
    last = None
    gap = 0
    for value in series:
        if value is not None:
            last = value
            gap = 0
            filled.append(value)
        elif last is None:
            filled.append(None)
        else:
            gap += 1
            if gap <= max_gap:
                filled.append(last)
            else:
                filled.append(None)
    return filled


def simple_returns(series):
    """Day-on-day returns, aligned with the series (the first is None); None where either day is missing."""
    returns = [None]
    for i in range(1, len(series)):
        before = series[i - 1]
        after = series[i]
        if before is None or after is None:
            returns.append(None)
        else:
            returns.append(after / before - 1.0)
    return returns


def first_price_index(series):
    """Index of the first price in the series, or None if it has none."""
    for i, value in enumerate(series):
        if value is not None:
            return i
    return None
