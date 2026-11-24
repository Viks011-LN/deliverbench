"""Errors that folio reports to the user.

Anything derived from FolioError is an expected failure (a bad input file, a
bad setting, a missing price) and the CLI prints its message without a
traceback. Anything else escaping a command is a bug.
"""

from __future__ import annotations


class FolioError(Exception):
    """Base class for expected, user-facing failures."""


class ConfigError(FolioError):
    """A setting is unknown, has the wrong type or is out of range."""


class DataError(FolioError):
    """An input file is missing or malformed.

    ``source`` and ``line`` are optional. When given they prefix the message
    as ``source:line:`` so that editors can jump straight to the problem.
    """

    def __init__(self, message: str, *, source: str | None = None, line: int | None = None):
        self.reason = message
        self.source = source
        self.line = line
        super().__init__(self._compose(message, source, line))

    @staticmethod
    def _compose(message: str, source: str | None, line: int | None) -> str:
        if source is None:
            return message
        if line is None:
            return f"{source}: {message}"
        return f"{source}:{line}: {message}"


class MissingPriceError(DataError):
    """No usable price or FX rate for the date asked for."""


class ValuationError(FolioError):
    """The portfolio cannot be valued as asked (nothing held, NAV not positive...)."""


class RiskError(FolioError):
    """Not enough history for a risk figure."""
