"""A changed momentum, written for the slot: the hidden check that the built-in strategies run through their files.

Added at the end of bt/strategies/momentum.py (the reference's and the agent's alike), so these three names come
last and win while the file's other names stay. The same PARAMETERS, defaults and warm-up as the desk's momentum,
so every check an engine keeps on these parameters still holds; the score is turned round (a contrarian momentum:
what fell between `lookback` and `skip` days ago scores high). An engine that runs its own momentum instead of this
file prints something else.
"""

PARAMETERS = {"lookback": 60, "skip": 5}


def warmup(params):
    return params["lookback"]


def score(history, params):
    lookback = params["lookback"]
    skip = params["skip"]
    scores = {}
    for symbol, closes in history.items():
        t = len(closes) - 1
        start = closes[t - lookback]
        end = closes[t - skip]
        if start is None or end is None:
            scores[symbol] = None
            continue
        scores[symbol] = 1.0 - end / start
    return scores
