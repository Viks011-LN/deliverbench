"""Breakout: trade a close that leaves the range of the previous `window` closes.

A close above the highest of the previous `window` closes by more than `margin` (a fraction) scores the size of
the breakout; a close below the lowest by more than `margin` scores the size of the breakdown, which is negative
(a short, where shorts are allowed). Every other name has no score, nor has a name with a gap in its window.

A hidden strategy of T16, written for the slot as docs/design/strategy-slot.md describes it. Most names have no
score on most days.
"""

PARAMETERS = {"window": 50, "margin": 0.0}


def warmup(params):
    return params["window"]


def score(history, params):
    window = params["window"]
    margin = params["margin"]
    scores = {}
    for symbol, closes in history.items():
        today = closes[-1]
        past = closes[-window - 1:-1]
        if today is None or None in past:
            scores[symbol] = None
            continue
        high = max(past)
        low = min(past)
        if today > high * (1.0 + margin):
            scores[symbol] = today / high - 1.0
        elif today < low * (1.0 - margin):
            scores[symbol] = today / low - 1.0
        else:
            scores[symbol] = None
    return scores
