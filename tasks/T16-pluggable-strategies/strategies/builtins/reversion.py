"""A changed reversion, written for the slot: the hidden check that the built-in strategies run through their files.

Added at the end of bt/strategies/reversion.py (the reference's and the agent's alike), so these three names come
last and win while the file's other names stay. The same PARAMETERS, defaults and warm-up as the desk's reversion;
the score keeps the z-score's sign (a name far above its average scores high) and the band is half as wide. An
engine that runs its own reversion instead of this file prints something else.
"""
import math

PARAMETERS = {"window": 20, "entry_z": 1.0}


def warmup(params):
    return params["window"]


def score(history, params):
    window = params["window"]
    entry_z = params["entry_z"]
    scores = {}
    for symbol, closes in history.items():
        values = closes[-window:]
        if len(values) < window or None in values:
            scores[symbol] = None
            continue
        mean = 0.0
        for value in values:
            mean += value
        mean /= window
        variance = 0.0
        for value in values:
            variance += (value - mean) * (value - mean)
        variance /= window - 1
        if variance == 0.0:
            scores[symbol] = None
            continue
        z = (values[-1] - mean) / math.sqrt(variance)
        scores[symbol] = 0.0 if abs(z) < entry_z / 2 else z
    return scores
