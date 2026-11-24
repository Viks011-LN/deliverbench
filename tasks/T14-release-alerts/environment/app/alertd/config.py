"""Settings.

alertd/defaults.toml declares every setting alertd reads, with its default. A config file (config/alerts.toml unless
--config names another) holds the desk's own values:

- A config file need only set the keys it changes; every other key takes its default from alertd/defaults.toml.
- Every key in a config file must be declared in alertd/defaults.toml. An unknown key is an error, never ignored, so
  a misspelt setting cannot quietly fall back to its default.
- A value must be of its default's type: a number (an integer or a decimal, either is accepted), a string, true or
  false, or a list of strings. No number alertd has is negative.
- A key is named by its place in the file: ``threshold_pct = 2.0`` under ``[price_move]`` is
  ``price_move.threshold_pct``, and deeper tables add to the name in the same way (``[a.b]`` then ``c = 1`` is
  ``a.b.c``).

A rule reads its own section (Settings.section): the settings under its kind, as nested dicts. Shared settings
(the suppressions') are under ``alerts``."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

from alertd.errors import ConfigError
from alertd.timeutil import parse_clock

DEFAULTS_FILE = Path(__file__).with_name("defaults.toml")
DEFAULT_CONFIG = Path("config") / "alerts.toml"

# Settings whose text must also make sense (checked when a file is loaded, defaults included).
VALIDATORS = {
    "alerts.quiet_start": lambda value: parse_clock(value, "alerts.quiet_start"),
    "alerts.quiet_end": lambda value: parse_clock(value, "alerts.quiet_end"),
}


def flatten(table: dict, prefix: str = "") -> dict:
    """{"a": {"b": 1}} -> {"a.b": 1}. Lists and values are leaves; an empty table adds nothing."""
    flat = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict):
            flat.update(flatten(value, key + "."))
        else:
            flat[key] = value
    return flat


def unflatten(flat: dict) -> dict:
    """{"a.b": 1} -> {"a": {"b": 1}}."""
    nested: dict = {}
    for key, value in flat.items():
        parts = key.split(".")
        node = nested
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = copy.deepcopy(value)
    return nested


def type_of(value: object) -> str:
    """The type a setting has, as config files are checked: number, string, boolean, list or table."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "table"
    return type(value).__name__


def read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML ({exc})") from None


def check_value(key: str, value: object, default: object, where: str) -> None:
    """Refuse a value that does not fit its declared default."""
    want, got = type_of(default), type_of(value)
    if want != got:
        raise ConfigError(f"{where}: {key} must be a {want}, got {value!r}")
    if want == "number" and value < 0:
        raise ConfigError(f"{where}: {key} must not be negative, got {value!r}")
    if want == "list" and not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}: {key} must be a list of strings, got {value!r}")
    if key in VALIDATORS:
        try:
            VALIDATORS[key](value)
        except ValueError as exc:
            raise ConfigError(f"{where}: {exc}") from None


def load_defaults() -> dict:
    """Every declared setting with its default, by its dotted key."""
    defaults = flatten(read_toml(DEFAULTS_FILE))
    for key, value in defaults.items():
        check_value(key, value, value, "alertd/defaults.toml")
    return defaults


class Settings:
    """The settings in force: the defaults, with a config file's values over them."""

    def __init__(self, values: dict, sources: dict, path: Path | None = None):
        self._values = values      # dotted key -> value
        self._sources = sources    # dotted key -> "default" or the config file's path
        self.path = path

    def get(self, key: str):
        try:
            return copy.deepcopy(self._values[key])
        except KeyError:
            raise KeyError(f"no setting {key!r} is declared in alertd/defaults.toml") from None

    def source(self, key: str) -> str:
        return self._sources[key]

    def keys(self) -> list[str]:
        return sorted(self._values)

    def section(self, name: str) -> dict:
        """The settings under ``name`` as nested dicts ({} if there are none)."""
        prefix = name + "."
        return unflatten({key[len(prefix):]: value for key, value in self._values.items() if key.startswith(prefix)})

    def set_in_file(self) -> list[str]:
        """The keys the config file sets."""
        return sorted(key for key, source in self._sources.items() if source != "default")


def load_settings(path: str | Path | None = None, *, required: bool = False) -> Settings:
    """The defaults, with the config file at ``path`` over them.

    With no path, config/alerts.toml is used if it exists (relative to the folder alertd runs from), and the
    defaults alone if it does not. A path that was named must exist (``required`` makes the default one a must too).
    """
    defaults = load_defaults()
    values, sources = dict(defaults), {key: "default" for key in defaults}
    if path is None:
        path, named = DEFAULT_CONFIG, required
        if not path.exists() and not named:
            return Settings(values, sources, None)
    path = Path(path)
    where = str(path)
    for key, value in flatten(read_toml(path)).items():
        if key not in defaults:
            raise ConfigError(f"{where}: unknown key {key} (every key must be declared in alertd/defaults.toml)")
        check_value(key, value, defaults[key], where)
        values[key] = value
        sources[key] = where
    return Settings(values, sources, path)
