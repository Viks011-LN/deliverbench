"""Steady climbers: the best return per unit of risk since the run began.

A name's score is the mean of its daily returns over everything the history holds since its first price, divided
by their sample standard deviation. It needs more than `days` closes since that first price, and none missing;
a name that never moved has no score, and a score smaller than `floor` in size counts as none. A falling name
scores below zero (a short, where shorts are allowed).

A hidden strategy of T16, written for the slot as docs/design/strategy-slot.md describes it. It uses the whole
history from the run's first day, not a fixed window.
"""
import math

PARAMETERS = {"days": 60, "floor": 0.02}


def warmup(params):
    return params["days"]


def score(history, params):
    days = params["days"]
    floor = params["floor"]
    scores = {}
    for symbol, closes in history.items():
        first = None
        for i, close in enumerate(closes):
            if close is not None:
                first = i
                break
        if first is None:
            scores[symbol] = None
            continue
        series = closes[first:]
        if None in series or len(series) <= days:
            scores[symbol] = None
            continue
        returns = [series[i] / series[i - 1] - 1.0 for i in range(1, len(series))]
        mean = 0.0
        for r in returns:
            mean += r
        mean /= len(returns)
        variance = 0.0
        for r in returns:
            variance += (r - mean) * (r - mean)
        variance /= len(returns) - 1
        if variance == 0.0:
            scores[symbol] = None
            continue
        value = mean / math.sqrt(variance)
        scores[symbol] = None if abs(value) < floor else value
    return scores
