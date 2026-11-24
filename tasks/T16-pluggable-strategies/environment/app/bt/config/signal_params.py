"""Signal types and their parameters: which types exist, each type's parameter list, and the checks on the values.

The config's `signal` section names a type and may give any of that type's parameters; the others take the
defaults in bt/config/defaults.py (SIGNAL_DEFAULTS). validate.py calls check_signal() before any other setting is
checked, so a problem in `signal` is always the one reported. The report and the summary read parameters with
signal_parameter(), so they show the default where the config leaves a parameter out.

Adding a signal type means a new entry in SIGNAL_TYPES and SIGNAL_PARAMETERS, its defaults in SIGNAL_DEFAULTS and
its checks below (see docs/ARCHITECTURE.md for the other places).
"""
from bt.config.defaults import SIGNAL_DEFAULTS
from bt.errors import ConfigError

SIGNAL_TYPES = ("momentum", "reversion")

SIGNAL_PARAMETERS = {
    "momentum": ("lookback", "skip"),
    "reversion": ("window", "entry_z"),
}


def is_whole(value):
    """A JSON whole number (true and false are not numbers, although Python counts them as ints)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    """A JSON number, whole or not."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def signal_parameter(signal, name):
    """A parameter of the configured signal: the config's value, or the type's default when it gives none."""
    return signal.get(name, SIGNAL_DEFAULTS[signal["type"]][name])


def check_signal(where, signal):
    """Refuse a `signal` section the engine cannot run. `where` is the config file's path, which every message
    starts with. The checks run in a fixed order: the section itself, its type, unknown parameters (in the
    config's order), then the values."""
    if not isinstance(signal, dict):
        raise ConfigError(f"{where}: signal must be a JSON object")
    kind = signal.get("type")
    if kind not in SIGNAL_TYPES:
        raise ConfigError(f"{where}: unknown signal type {kind!r}")
    for key in signal:
        if key != "type" and key not in SIGNAL_PARAMETERS[kind]:
            raise ConfigError(f"{where}: signal: {kind} has no parameter {key!r}")
    if kind == "momentum":
        lookback = signal_parameter(signal, "lookback")
        skip = signal_parameter(signal, "skip")
        if not is_whole(lookback) or lookback < 2:
            raise ConfigError(f"{where}: signal.lookback must be a whole number of at least 2")
        if not is_whole(skip) or not 0 <= skip < lookback:
            raise ConfigError(f"{where}: signal.skip must be a whole number from 0 to lookback - 1")
    elif kind == "reversion":
        window = signal_parameter(signal, "window")
        entry_z = signal_parameter(signal, "entry_z")
        if not is_whole(window) or window < 2:
            raise ConfigError(f"{where}: signal.window must be a whole number of at least 2")
        if not is_number(entry_z) or entry_z < 0:
            raise ConfigError(f"{where}: signal.entry_z must be a number of at least 0")
