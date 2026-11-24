"""The errors bt reports to the user.

Every problem with the inputs is a BacktestError. The command line catches it, prints "error: <message>" on
stderr and exits with status 2; nothing is printed on stdout and no equity file is written. Anything else that
goes wrong is a bug and is left to Python's own traceback.
"""


class BacktestError(Exception):
    """A problem with the inputs. main() reports it on stderr and exits with status 2."""


class PriceFileError(BacktestError):
    """A problem with the price file: its layout, a date or a price."""


class ConfigError(BacktestError):
    """A problem with the config file: not JSON, an unknown setting, or a value the engine cannot use."""


class WindowError(BacktestError):
    """--start and --end leave fewer than two days of prices."""
