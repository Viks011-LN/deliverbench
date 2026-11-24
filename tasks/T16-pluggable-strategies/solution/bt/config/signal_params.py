"""The config's `signal` section: which strategy it names, and its parameters.

`signal.type` names a strategy, a module bt/strategies/<type>.py (docs/design/strategy-slot.md); the section may
give any of that strategy's parameters, and the others take the defaults in its PARAMETERS. validate.py calls
check_signal() before any other setting is checked, so a problem in `signal` is always the one reported.
"""
from bt.errors import ConfigError
from bt.strategies import configured, find_strategy, strategy_parameters


def is_whole(value):
    """A JSON whole number (true and false are not numbers, although Python counts them as ints)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    """A JSON number, whole or not."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def signal_parameters(signal):
    """The configured strategy's parameters, in its order, with defaults filled in."""
    return configured(signal)[1]


def signal_parameter(signal, name):
    """A parameter of the configured signal: the config's value, or the strategy's default when it gives none."""
    return signal_parameters(signal)[name]


def check_signal(where, signal):
    """Refuse a `signal` section the engine cannot run. `where` is the config file's path, which every message
    starts with. The checks run in a fixed order: the section itself, its type, unknown parameters (in the
    config's order), then the values (a strategy's own check, if it has one)."""
    if not isinstance(signal, dict):
        raise ConfigError(f"{where}: signal must be a JSON object")
    kind = signal.get("type")
    strategy = find_strategy(kind)
    if strategy is None:
        raise ConfigError(f"{where}: unknown signal type {kind!r}")
    for key in signal:
        if key != "type" and key not in strategy.PARAMETERS:
            raise ConfigError(f"{where}: signal: {kind} has no parameter {key!r}")
    check = getattr(strategy, "check", None)
    if check is not None:
        problem = check(strategy_parameters(strategy, signal))
        if problem is not None:
            raise ConfigError(f"{where}: {problem}")
