"""Momentum: buy what has risen, over a lookback that skips the most recent days.

A stock's score today is its return from `lookback` days ago to `skip` days ago:

    score = close[today - skip] / close[today - lookback] - 1

Skipping the last few days avoids the short-term reversal effect, which works against momentum over a week or
two. The score is None when either close is missing. It looks back `lookback` days (its warm-up).

A strategy for the slot (docs/design/strategy-slot.md), like any other; docs/strategies.md has more.
"""

PARAMETERS = {"lookback": 60, "skip": 5}


def warmup(params):
    """It looks back `lookback` days."""
    return params["lookback"]


def is_whole(value):
    """A JSON whole number (true and false are not numbers, although Python counts them as ints)."""
    return isinstance(value, int) and not isinstance(value, bool)


def check_parameters(params):
    """What is wrong with the parameters' values (the config check reports it after the config's path), or None.
    The lookback first, then the skip."""
    lookback = params["lookback"]
    skip = params["skip"]
    if not is_whole(lookback) or lookback < 2:
        return "signal.lookback must be a whole number of at least 2"
    if not is_whole(skip) or not 0 <= skip < lookback:
        return "signal.skip must be a whole number from 0 to lookback - 1"
    return None


def momentum(closes, lookback, skip):
    """The return from `lookback` days before the last close to `skip` days before it; None when either close is
    missing. (The closes reach back more than `lookback` days: the engine scores only after the warm-up.)"""
    start = closes[-1 - lookback]
    end = closes[-1 - skip]
    if start is None or end is None:
        return None
    return end / start - 1.0


def score(history, params):
    """Every symbol's momentum."""
    lookback = params["lookback"]
    skip = params["skip"]
    return {symbol: momentum(closes, lookback, skip) for symbol, closes in history.items()}
