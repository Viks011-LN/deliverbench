"""Momentum, as a strategy: the return from `lookback` days ago to `skip` days ago (bt/signals/momentum.py)."""
from bt.config.signal_params import is_whole
from bt.signals.momentum import momentum_score

PARAMETERS = {"lookback": 60, "skip": 5}


def check(params):
    """The checks on the values, with the messages the desk knows."""
    lookback = params["lookback"]
    skip = params["skip"]
    if not is_whole(lookback) or lookback < 2:
        return "signal.lookback must be a whole number of at least 2"
    if not is_whole(skip) or not 0 <= skip < lookback:
        return "signal.skip must be a whole number from 0 to lookback - 1"
    return None


def warmup(params):
    return params["lookback"]


def score(history, params):
    lookback = params["lookback"]
    skip = params["skip"]
    scores = {}
    for symbol, closes in history.items():
        scores[symbol] = momentum_score(closes, len(closes) - 1, lookback, skip)
    return scores
