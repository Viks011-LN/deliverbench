"""The strategy slot (docs/design/strategy-slot.md).

A strategy is a module bt/strategies/<type>.py, chosen by the config's `signal.type`. It defines:

  PARAMETERS          its parameters' names and defaults, in order (a dict);
  warmup(params)      the days of prices it needs before its first score;
  score(history, params)
                      {symbol: a number or None}, from each symbol's forward-filled closes from the run's first day
                      up to and including today.

The engine finds a strategy by its file, so a new strategy is a file dropped in this folder and nothing else.
Momentum and reversion are strategies like any other. A strategy may also define check(params), which returns a
message for a parameter value it cannot run with, or None; the built-in ones do, to keep their messages.
"""
import importlib
from pathlib import Path

from bt.errors import BacktestError

FOLDER = Path(__file__).resolve().parent


def find_strategy(kind):
    """The strategy module for signal.type `kind`, or None if there is no strategy file of that name."""
    if not isinstance(kind, str) or not kind.isidentifier() or kind.startswith("_"):
        return None
    if not (FOLDER / f"{kind}.py").is_file():
        return None
    return importlib.import_module(f"{__name__}.{kind}")


def strategy_parameters(strategy, signal):
    """Every parameter of the strategy, in its PARAMETERS order: the config's value, or the default."""
    return {name: signal.get(name, default) for name, default in strategy.PARAMETERS.items()}


def configured(signal):
    """(strategy module, its parameters with defaults filled in) for a validated `signal` section."""
    strategy = find_strategy(signal.get("type"))
    if strategy is None:
        raise BacktestError(f"unknown signal type {signal.get('type')!r}")
    return strategy, strategy_parameters(strategy, signal)
