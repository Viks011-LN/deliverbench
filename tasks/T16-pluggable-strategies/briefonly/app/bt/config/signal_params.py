"""The `signal` section: which strategy it names, that strategy's parameters, and the checks on their values.

The config's `signal` section names a strategy by its `type` (a module in bt/strategies/, found through the strategy
slot, bt/signals/slot.py) and may give any of that strategy's parameters; the others take the defaults in the
strategy's PARAMETERS. validate.py calls check_signal() before any other setting is checked, so a problem in
`signal` is always the one reported. Nothing here names a strategy: a strategy's own checks on its values are its
check_parameters() (docs/strategies.md).
"""
from bt.errors import ConfigError
from bt.signals.slot import find_strategy, get_strategy, parameters


def is_whole(value):
    """A JSON whole number (true and false are not numbers, although Python counts them as ints)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    """A JSON number, whole or not."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def signal_parameter(signal, name):
    """A parameter of the configured strategy: the config's value, or the strategy's default when it gives none."""
    return parameters(get_strategy(signal), signal)[name]


def check_signal(where, signal):
    """Refuse a `signal` section the engine cannot run. `where` is the config file's path, which every message
    starts with. The checks run in a fixed order: the section itself, its type, unknown parameters (in the
    config's order), then the values (the strategy's check_parameters(), when it has one)."""
    if not isinstance(signal, dict):
        raise ConfigError(f"{where}: signal must be a JSON object")
    kind = signal.get("type")
    strategy = find_strategy(kind)
    if strategy is None:
        raise ConfigError(f"{where}: unknown signal type {kind!r}")
    for key in signal:
        if key != "type" and key not in strategy.PARAMETERS:
            raise ConfigError(f"{where}: signal: {kind} has no parameter {key!r}")
    check = getattr(strategy, "check_parameters", None)
    if check is not None:
        problem = check(parameters(strategy, signal))
        if problem is not None:
            raise ConfigError(f"{where}: {problem}")
