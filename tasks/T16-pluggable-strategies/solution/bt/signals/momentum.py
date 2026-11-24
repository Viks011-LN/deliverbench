"""Momentum: buy what has risen, over a lookback that skips the most recent days.

The score of a stock on day t is its return from `lookback` days ago to `skip` days ago. Skipping the last few
days avoids the short-term reversal effect, which works against momentum over a week or two.
"""

LOOKBACK = 60    # days
SKIP = 5         # days


def momentum_score(series, t, lookback, skip):
    """Return from `lookback` days ago to `skip` days ago; None when either price is missing.
    (t >= lookback: the engine only asks after its warm-up.)"""
    start = series[t - lookback]
    end = series[t - skip]
    if start is None or end is None:
        return None
    return end / start - 1.0
