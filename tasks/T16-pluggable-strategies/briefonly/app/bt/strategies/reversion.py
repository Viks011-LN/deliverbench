"""Mean reversion: buy what is cheap against its own recent average, sell what is dear.

A stock's score today is minus the z-score of today's close against the last `window` closes (today's included),
with their mean and their sample standard deviation:

    z = (close[today] - mean) / standard deviation
    score = -z, or 0 when |z| < entry_z

A stock far below its average scores high. Inside the entry band the score is 0, which keeps the stock out of the
book. The score is None when a close in the window is missing, and when the price did not move at all over the
window. Its warm-up is `window` days.

The arithmetic is the one the golden files were made with: the mean by Python's sum(), then the squares added up
oldest first. (bt/signals/stats.py has the same statistics by index, for the code that still uses them.)

A strategy for the slot (docs/design/strategy-slot.md), like any other; docs/strategies.md has more.
"""
import math

PARAMETERS = {"window": 20, "entry_z": 1.0}


def warmup(params):
    """It looks at the last `window` days."""
    return params["window"]


def is_whole(value):
    """A JSON whole number (true and false are not numbers, although Python counts them as ints)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    """A JSON number, whole or not."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_parameters(params):
    """What is wrong with the parameters' values (the config check reports it after the config's path), or None.
    The window first, then the entry band."""
    window = params["window"]
    entry_z = params["entry_z"]
    if not is_whole(window) or window < 2:
        return "signal.window must be a whole number of at least 2"
    if not is_number(entry_z) or entry_z < 0:
        return "signal.entry_z must be a number of at least 0"
    return None


def reversion(closes, window, entry_z):
    """Minus the z-score of the last close against the last `window` closes; 0 inside the entry band. None when
    one of those closes is missing or they are all the same. (There are at least `window` closes: the engine
    scores only after the warm-up.)"""
    chunk = closes[-window:]
    for value in chunk:
        if value is None:
            return None
    mean = sum(chunk) / window
    total = 0.0
    for value in chunk:
        deviation = value - mean
        total += deviation * deviation
    std = math.sqrt(total / (window - 1))
    if std == 0.0:
        return None
    z = (closes[-1] - mean) / std
    if abs(z) < entry_z:
        return 0.0
    return -z


def score(history, params):
    """Every symbol's reversion score."""
    window = params["window"]
    entry_z = params["entry_z"]
    return {symbol: reversion(closes, window, entry_z) for symbol, closes in history.items()}
