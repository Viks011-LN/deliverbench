"""Scoring: the configured strategy turns each stock's price history into a score on a rebalancing day.

The strategy is the module in bt/strategies/ that the config's `signal.type` names, found and run through the
strategy slot (slot.py, docs/design/strategy-slot.md). A positive score is a reason to be long, a negative one
(with shorting allowed) a reason to be short; None leaves the stock out of the ranking. The portfolio code
(bt/portfolio/) takes it from there.

momentum.py and reversion.py keep the older per-series calls (momentum_score, reversion_score) for the code that
still uses them, on the strategies' own arithmetic; stats.py holds the rolling statistics of prices by index.
"""
from bt.signals.slot import get_strategy, parameters, strategy_scores


def compute_scores(prices, symbols, t, signal):
    """Score every symbol on day t with the configured strategy: {symbol: score or None}, in symbol order.
    `prices` are the forward-filled series; a name with no price today scores None whatever its history."""
    strategy = get_strategy(signal)
    return strategy_scores(strategy, parameters(strategy, signal), prices, symbols, t)


__all__ = ["compute_scores"]
