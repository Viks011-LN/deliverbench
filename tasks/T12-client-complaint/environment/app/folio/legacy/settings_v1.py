"""Version 1 settings, read from an INI file (folio.ini).

DEPRECATED since folio 0.4. Settings now live in folio/config/defaults.toml,
with overrides in folio.toml and --set (see folio/config/loader.py). The CLI
does not read this module or folio.ini any more. It is kept only because a
few desk scripts still import it; port them with to_v2_overrides() and do not
add settings here.

v1 had a single concentration limit, ``max_share``, applied to sectors and
single names alike. v2 splits it into limits.sector_max_share and
limits.name_max_share.
"""

import configparser
import warnings
from typing import List, Optional

V1_DEFAULTS = """
[general]
base_currency = GBP

[limits]
max_share = 0.20
var_limit = 0.03

[report]
decimals = 2
"""


class SettingsV1(object):
    """Typed view over a v1 INI file."""

    def __init__(self, parser):
        self._parser = parser

    @property
    def base_currency(self):
        return self._parser.get("general", "base_currency").strip().upper()

    @property
    def max_share(self):
        """Concentration limit for any one sector *or* name, as a fraction."""
        value = self._parser.getfloat("limits", "max_share")
        if not 0 < value <= 1:
            raise ValueError("limits.max_share must be in (0, 1], got %r" % value)
        return value

    @property
    def var_limit(self):
        return self._parser.getfloat("limits", "var_limit")

    @property
    def decimals(self):
        return self._parser.getint("report", "decimals")

    def to_v2_overrides(self):
        # type: () -> List[str]
        """The same settings as --set arguments for folio 0.4 and later."""
        return [
            "fx.base_currency=%s" % self.base_currency,
            "limits.sector_max_share=%s" % self.max_share,
            "limits.name_max_share=%s" % self.max_share,
            "limits.var_max_share=%s" % self.var_limit,
            "report.money_places=%d" % self.decimals,
        ]


def load_v1(path=None, text=None):
    # type: (Optional[str], Optional[str]) -> SettingsV1
    """Read v1 settings from ``path`` or ``text`` on top of the v1 defaults."""
    warnings.warn(
        "folio.legacy.settings_v1 is deprecated; settings live in folio/config/defaults.toml",
        DeprecationWarning,
        stacklevel=2,
    )
    parser = configparser.ConfigParser()
    parser.read_string(V1_DEFAULTS)
    if path is not None:
        if not parser.read(path, encoding="utf-8"):
            raise FileNotFoundError(path)
    if text is not None:
        parser.read_string(text)
    return SettingsV1(parser)
