"""Channel position: where today's close sits in the range of the previous `days` closes.

A close at the top of its range scores +0.5 and one at the bottom -0.5; a close beyond the range (a breakout)
scores beyond those. A name inside the neutral zone around the middle (|score| below `neutral`) has no score, nor
has a name with a gap in its window, or whose window never moved.

Written for the strategy slot (docs/design/strategy-slot.md); examples/README.md says how to try it.
"""

PARAMETERS = {"days": 40, "neutral": 0.1}


def warmup(params):
    """It looks back over the previous `days` closes, before today's."""
    return params["days"]


def score(history, params):
    days = params["days"]
    neutral = params["neutral"]
    scores = {}
    for symbol, closes in history.items():
        today = closes[-1]
        window = closes[-days - 1:-1]
        if today is None or None in window:
            scores[symbol] = None
            continue
        high = max(window)
        low = min(window)
        if high == low:
            scores[symbol] = None
            continue
        position = (today - low) / (high - low) - 0.5
        if abs(position) < neutral:
            scores[symbol] = None
        else:
            scores[symbol] = position
    return scores
