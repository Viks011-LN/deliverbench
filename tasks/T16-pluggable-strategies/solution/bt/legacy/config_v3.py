"""Configs from bt 3.x, before the `signal` section.

A 3.x config named its signal as a string (`"signal": "momentum"`) and gave the signal's parameters at the top
level (`"lookback": 60`), next to a few settings that have since been renamed. migrate() turns one into today's
layout; `python -m bt.tools.migrate OLD.json` prints the result. Nothing in bt reads a 3.x config any more.
"""

# Which 3.x top-level keys were signal parameters, and of which signal.
V3_SIGNAL_PARAMETERS = {
    "lookback": "momentum",
    "skip": "momentum",
    "window": "reversion",
    "entry_z": "reversion",
}

# 3.x settings that were renamed in 4.0.
V3_RENAMED = {
    "capital": "initial_capital",
    "frequency": "rebalance",
    "cost_bps": "commission_bps",
    "max_position": "max_weight",
    "fill_days": "max_fill_gap",
}

V3_DEFAULT_SIGNAL = "momentum"


class MigrationError(ValueError):
    """The old config cannot be turned into today's layout without guessing."""


def migrate(old):
    """Today's config for a 3.x config (a dict): `signal` first, then the other settings in the old file's order,
    renamed where they were renamed. Parameters that belong to another signal than the one named are refused."""
    if not isinstance(old, dict):
        raise MigrationError("a 3.x config is a JSON object")
    kind = old.get("signal", V3_DEFAULT_SIGNAL)
    if isinstance(kind, dict):
        raise MigrationError("this config already has a signal section; it is not a 3.x config")
    signal = {"type": kind}
    settings = {}
    for key, value in old.items():
        if key == "signal":
            continue
        if key in V3_SIGNAL_PARAMETERS:
            if V3_SIGNAL_PARAMETERS[key] != kind:
                raise MigrationError(f"{key!r} is a {V3_SIGNAL_PARAMETERS[key]} parameter, but the signal is {kind!r}")
            signal[key] = value
        else:
            settings[V3_RENAMED.get(key, key)] = value
    return {"signal": signal, **settings}
