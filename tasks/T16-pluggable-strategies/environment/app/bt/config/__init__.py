"""The config file: its settings and their defaults (defaults.py), loading (loader.py) and validation
(validate.py, and signal_params.py for the `signal` section)."""
from bt.config.defaults import DEFAULTS
from bt.config.loader import load_config

__all__ = ["DEFAULTS", "load_config"]
