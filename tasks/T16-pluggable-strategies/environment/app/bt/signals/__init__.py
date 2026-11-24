"""Scoring: the configured signal turns each stock's price history into a score on a rebalancing day.

A positive score is a reason to be long, a negative one (with shorting allowed) a reason to be short; None leaves
the stock out of the ranking. The portfolio code (bt/portfolio/) takes it from there.
"""
from bt.errors import BacktestError
from bt.signals.momentum import LOOKBACK, SKIP, momentum_score
from bt.signals.reversion import ENTRY_Z, WINDOW, reversion_score


def compute_scores(prices, symbols, t, signal):
    """Score every symbol on day t with the configured signal: {symbol: score or None}, in symbol order.
    `prices` are the forward-filled series; a name with no price today scores None whatever its history."""
    kind = signal["type"]
    scores = {}
    for symbol in symbols:
        series = prices[symbol]
        if series[t] is None:
            scores[symbol] = None
        elif kind == "momentum":
            scores[symbol] = momentum_score(series, t, signal.get("lookback", LOOKBACK), signal.get("skip", SKIP))
        elif kind == "reversion":
            scores[symbol] = reversion_score(series, t, signal.get("window", WINDOW),
                                             signal.get("entry_z", ENTRY_Z))
        else:
            raise BacktestError(f"unknown signal type {kind!r}")
    return scores


__all__ = ["compute_scores", "momentum_score", "reversion_score"]
