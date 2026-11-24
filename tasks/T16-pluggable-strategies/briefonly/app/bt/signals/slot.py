"""The strategy slot, from the engine's side (docs/design/strategy-slot.md).

The config's `signal.type` names a module in bt/strategies/: the file's name without .py, exactly, case included.
A strategy module defines PARAMETERS (its parameters and their defaults, in order), warmup(params) and
score(history, params). It may also define check_parameters(params), which returns what is wrong with the
parameters' values or None; the config check calls it (bt/config/signal_params.py). Nothing here names a
strategy: a new one is a new file in bt/strategies/.
"""
import importlib
import os
import sys

import bt.strategies
from bt.errors import BacktestError


def find_strategy(kind):
    """The strategy module for a signal type, or None when bt/strategies/ has no module of that name. A type that
    is not a string, or not a Python identifier, names no strategy."""
    if not isinstance(kind, str) or not kind.isidentifier() or kind == "__init__":
        return None
    filename = kind + ".py"
    for folder in bt.strategies.__path__:
        # The name must match exactly, case included, also where the file system ignores case.
        if filename in os.listdir(folder) and os.path.isfile(os.path.join(folder, filename)):
            name = f"{bt.strategies.__name__}.{kind}"
            if name not in sys.modules:
                importlib.invalidate_caches()   # a file added since Python last looked at the folder
            return importlib.import_module(name)
    return None


def get_strategy(signal):
    """The strategy module the `signal` section names. A type with no module is a BacktestError (the config check
    refuses it first, with the config's path)."""
    kind = signal.get("type")
    strategy = find_strategy(kind)
    if strategy is None:
        raise BacktestError(f"unknown signal type {kind!r}")
    return strategy


def parameters(strategy, signal):
    """The strategy's `params`: every name in its PARAMETERS, in that order, with the `signal` section's value
    where it gives one and the default otherwise. A new dict on every call; it does not hold `type`."""
    return {name: signal[name] if name in signal else default for name, default in strategy.PARAMETERS.items()}


def strategy_scores(strategy, params, prices, symbols, t):
    """Score day t: {symbol: score or None}, in symbol order. `prices` are the forward-filled series of the traded
    symbols; the strategy sees each one from the run's first day up to and including day t. A symbol with no
    price on day t scores None whatever the strategy says, and so does one it leaves out."""
    history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
    scored = strategy.score(history, params)
    scores = {}
    for symbol in symbols:
        if prices[symbol][t] is None:
            scores[symbol] = None
        else:
            scores[symbol] = scored.get(symbol)
    return scores
