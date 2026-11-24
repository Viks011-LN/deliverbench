"""Validation of a config file's settings.

The checks run in a fixed order and stop at the first problem, which is the one reported ("error: <path>:
<problem>", exit status 2). The order is part of what the desk relies on: the operations team keeps a list of
the messages (docs/operations.md), and a config with two problems always reports the same one.

  1. the config is a JSON object;
  2. every key is a known setting (the first unknown key, in the file's order);
  3. the `signal` section (bt/config/signal_params.py);
  4. `rebalance`;
  5. the whole-number settings, then `allow_short`;
  6. the positive, the non-negative and the optional settings, then `drawdown_scale` and `stop_loss`;
  7. `exclude`, `benchmark` and `cash_rate`.

Whether the benchmark is a column of the price file is checked later, once the prices are read (bt/data/benchmark.py).
"""
from bt.config.defaults import (DEFAULTS, NON_NEGATIVE_SETTINGS, OPTIONAL_POSITIVE_SETTINGS, POSITIVE_SETTINGS,
                                WHOLE_SETTINGS)
from bt.config.signal_params import check_signal, is_number, is_whole
from bt.constants import REBALANCE_FREQUENCIES
from bt.errors import ConfigError


def merged(raw):
    """DEFAULTS with the config's settings laid over them. Sections and lists are copied, so a config never shares
    them with DEFAULTS; the signal section is copied as the config gives it."""
    config = {}
    for key, default in DEFAULTS.items():
        value = raw.get(key, default)
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, list):
            value = list(value)
        config[key] = value
    return config


def validate_config(where, raw):
    """Check a parsed config file and return the complete config (DEFAULTS filled in). `where` is its path."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: the config must be a JSON object")
    for key in raw:
        if key not in DEFAULTS:
            raise ConfigError(f"{where}: unknown setting {key!r}")
    config = merged(raw)

    check_signal(where, config["signal"])

    if config["rebalance"] not in REBALANCE_FREQUENCIES:
        raise ConfigError(f"{where}: rebalance must be one of {', '.join(REBALANCE_FREQUENCIES)}")

    for key, minimum in WHOLE_SETTINGS.items():
        if not is_whole(config[key]) or config[key] < minimum:
            raise ConfigError(f"{where}: {key} must be a whole number of at least {minimum}")
    if not isinstance(config["allow_short"], bool):
        raise ConfigError(f"{where}: allow_short must be true or false")

    for key in POSITIVE_SETTINGS:
        if not is_number(config[key]) or config[key] <= 0:
            raise ConfigError(f"{where}: {key} must be a positive number")
    for key in NON_NEGATIVE_SETTINGS:
        if not is_number(config[key]) or config[key] < 0:
            raise ConfigError(f"{where}: {key} must be a number of at least 0")
    for key in OPTIONAL_POSITIVE_SETTINGS:
        value = config[key]
        if value is not None and (not is_number(value) or value <= 0):
            raise ConfigError(f"{where}: {key} must be a positive number or null")
    scale = config["drawdown_scale"]
    if not is_number(scale) or not 0 < scale <= 1:
        raise ConfigError(f"{where}: drawdown_scale must be above 0 and at most 1")
    stop = config["stop_loss"]
    if stop is not None and (not is_number(stop) or not 0 < stop < 1):
        raise ConfigError(f"{where}: stop_loss must be above 0 and below 1, or null")

    exclude = config["exclude"]
    if not isinstance(exclude, list) or not all(isinstance(symbol, str) for symbol in exclude):
        raise ConfigError(f"{where}: exclude must be a list of symbols")
    if config["benchmark"] is not None and not isinstance(config["benchmark"], str):
        raise ConfigError(f"{where}: benchmark must be a symbol or null")
    if not is_number(config["cash_rate"]):
        raise ConfigError(f"{where}: cash_rate must be a number")
    return config
