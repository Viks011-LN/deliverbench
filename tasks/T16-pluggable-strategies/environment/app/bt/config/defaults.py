"""Every setting of the config file, with its default. README.md documents each one.

A config file is a JSON object that gives some of these settings; the loader lays it over DEFAULTS. The `signal`
section is kept as the config gives it: its parameters' defaults are in SIGNAL_DEFAULTS, and the parts of the
program that need a parameter read it with bt.config.signal_params.signal_parameter (or with the scoring
module's own default, for the older parts).
"""

DEFAULTS = {
    "initial_capital": 1000000.0,
    "signal": {"type": "momentum"},
    "top_n": 3,
    "allow_short": False,
    "max_weight": 0.4,
    "min_price": 0.0,
    "min_history": 0,
    "exclude": [],
    "rebalance": "monthly",
    "rebalance_band": 0.0,
    "vol_target": None,
    "vol_window": 20,
    "max_leverage": 1.5,
    "drawdown_limit": None,
    "drawdown_scale": 0.5,
    "stop_loss": None,
    "max_turnover": None,
    "commission_bps": 5.0,
    "min_commission": 0.0,
    "slippage_bps": 2.0,
    "borrow_bps": 50.0,
    "cash_rate": 0.0,
    "max_fill_gap": 5,
    "benchmark": None,
    "risk_free_rate": 0.0,
}

# The parameters of each signal type, with their defaults, in the order the report and the summary show them.
SIGNAL_DEFAULTS = {
    "momentum": {"lookback": 60, "skip": 5},
    "reversion": {"window": 20, "entry_z": 1.0},
}

# How validate.py checks the plain settings (the `signal` section has its own checks in signal_params.py).
WHOLE_SETTINGS = {"top_n": 1, "vol_window": 2, "max_fill_gap": 0, "min_history": 0}   # whole numbers, minimum
POSITIVE_SETTINGS = ("initial_capital", "max_weight", "max_leverage")
NON_NEGATIVE_SETTINGS = ("min_price", "rebalance_band", "commission_bps", "min_commission", "slippage_bps",
                         "borrow_bps", "risk_free_rate")
OPTIONAL_POSITIVE_SETTINGS = ("vol_target", "drawdown_limit", "max_turnover")
