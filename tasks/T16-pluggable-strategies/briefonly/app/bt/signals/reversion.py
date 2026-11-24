"""Mean reversion's score of one series on day t: the call the scoring code used before the strategy slot.

Mean reversion is a strategy like any other now (bt/strategies/reversion.py), and the engine scores it through the
slot. This module keeps reversion_score(series, t, window, entry_z) for the code that still calls it, on the
strategy's own arithmetic, so the two cannot drift apart.
"""
from bt.strategies.reversion import reversion

WINDOW = 20      # days; older constants (the strategy's PARAMETERS are the README's defaults: entry_z 1.0)
ENTRY_Z = 1      # standard deviations


def reversion_score(series, t, window, entry_z):
    """Minus the z-score of today's price against its moving average; 0 inside the entry band. None when the
    window is incomplete or the price did not move at all over it. (t >= window - 1: the engine only asks after
    its warm-up.)"""
    return reversion(series[:t + 1], window, entry_z)
