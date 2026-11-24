"""Momentum's score of one series on day t: the call the scoring code used before the strategy slot.

Momentum is a strategy like any other now (bt/strategies/momentum.py), and the engine scores it through the slot.
This module keeps momentum_score(series, t, lookback, skip) for the code that still calls it (the 2021 runner in
bt/legacy/), on the strategy's own arithmetic, so the two cannot drift apart.
"""
from bt.strategies.momentum import momentum

LOOKBACK = 60    # days; the 2021 runner's default (the strategy's PARAMETERS are the README's defaults)
SKIP = 5         # days


def momentum_score(series, t, lookback, skip):
    """Return from `lookback` days ago to `skip` days ago; None when either price is missing.
    (t >= lookback: the engine only asks after its warm-up.)"""
    return momentum(series[:t + 1], lookback, skip)
