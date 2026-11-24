"""Scoring: the configured strategy turns each stock's price history into a score on a rebalancing day.

A positive score is a reason to be long, a negative one (with shorting allowed) a reason to be short; None leaves
the stock out of the ranking. The strategies live in bt/strategies/; the arithmetic of the two built-in ones is in
momentum.py, reversion.py and stats.py here. The portfolio code (bt/portfolio/) takes it from there.
"""
from bt.signals.momentum import momentum_score
from bt.signals.reversion import reversion_score
from bt.strategies import configured


def compute_scores(prices, symbols, t, signal):
    """Score every symbol on day t with the configured strategy: {symbol: score or None}, in symbol order.
    `prices` are the forward-filled series; a name with no price today scores None whatever its history."""
    strategy, params = configured(signal)
    history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
    scored = strategy.score(history, params)
    scores = {}
    for symbol in symbols:
        scores[symbol] = None if prices[symbol][t] is None else scored.get(symbol)
    return scores


__all__ = ["compute_scores", "momentum_score", "reversion_score"]
