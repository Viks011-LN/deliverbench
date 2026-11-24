"""Pullback: buy a long-run riser that has dipped lately, sell a long-run faller that has bounced.

The trend is the return over `lookback` days that ended `recent` days ago; the move is the return over the last
`recent` days. The score is the trend minus `tilt` times the move, so a riser that pulled back scores high and a
faller that bounced scores low (negative: a short, where shorts are allowed). A name with a missing price at any
of the three days has no score.

A hidden strategy of T16, written for the slot as docs/design/strategy-slot.md describes it. Its warm-up is
longer than its `lookback`: it reaches back lookback + recent days.
"""

PARAMETERS = {"lookback": 90, "recent": 10, "tilt": 2.0}


def warmup(params):
    return params["lookback"] + params["recent"]


def score(history, params):
    lookback = params["lookback"]
    recent = params["recent"]
    tilt = params["tilt"]
    scores = {}
    for symbol, closes in history.items():
        t = len(closes) - 1
        then = closes[t - recent - lookback]
        middle = closes[t - recent]
        now = closes[t]
        if then is None or middle is None or now is None:
            scores[symbol] = None
            continue
        trend = middle / then - 1.0
        move = now / middle - 1.0
        scores[symbol] = trend - tilt * move
    return scores
