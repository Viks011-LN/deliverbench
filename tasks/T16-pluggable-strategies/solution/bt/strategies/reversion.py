"""Mean reversion, as a strategy: minus the z-score of today's close against the last `window` closes, 0 inside
the entry band (bt/signals/reversion.py)."""
from bt.config.signal_params import is_number, is_whole
from bt.signals.reversion import reversion_score

PARAMETERS = {"window": 20, "entry_z": 1.0}


def check(params):
    """The checks on the values, with the messages the desk knows."""
    window = params["window"]
    entry_z = params["entry_z"]
    if not is_whole(window) or window < 2:
        return "signal.window must be a whole number of at least 2"
    if not is_number(entry_z) or entry_z < 0:
        return "signal.entry_z must be a number of at least 0"
    return None


def warmup(params):
    return params["window"]


def score(history, params):
    window = params["window"]
    entry_z = params["entry_z"]
    scores = {}
    for symbol, closes in history.items():
        scores[symbol] = reversion_score(closes, len(closes) - 1, window, entry_z)
    return scores
