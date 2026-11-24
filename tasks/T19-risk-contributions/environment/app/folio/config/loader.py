"""Load settings in layers.

1. ``folio/config/defaults.toml``, shipped with the code. Every key lives here.
2. ``folio.toml`` in the working folder if there is one, or the file given
   with ``--config``.
3. ``--set section.key=value`` overrides from the command line, in order.

Later layers win. Layers 2 and 3 may only change keys that exist in layer 1,
so a misspelt key is an error rather than a line that silently does nothing.
"""

from __future__ import annotations

import difflib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from folio.config.settings import Settings, settings_from_dict
from folio.errors import ConfigError

DEFAULTS_PATH = Path(__file__).with_name("defaults.toml")
LOCAL_NAME = "folio.toml"


@dataclass(frozen=True)
class Override:
    section: str
    key: str
    value: Any
    text: str

    @property
    def name(self) -> str:
        return f"{self.section}.{self.key}"


def read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"settings file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from None


def parse_override(text: str) -> Override:
    """Parse one ``--set`` argument such as ``limits.sector_max_share=0.3``."""
    name, sep, raw = text.partition("=")
    if not sep:
        raise ConfigError(f"--set {text!r}: expected section.key=value")
    section, dot, key = name.strip().partition(".")
    if not dot or not section or not key or "." in key:
        raise ConfigError(f"--set {text!r}: the name must be section.key, e.g. limits.sector_max_share")
    return Override(section, key, parse_value(raw.strip()), text)


def parse_value(raw: str) -> Any:
    """Read ``raw`` as a TOML value, falling back to a plain string.

    So ``0.3`` is a float, ``true`` a boolean, ``["a", "b"]`` a list, and
    ``GBP`` the string "GBP" without the quotes TOML would want.
    """
    if not raw:
        return ""
    try:
        return tomllib.loads(f"value = {raw}")["value"]
    except tomllib.TOMLDecodeError:
        return raw


def merge_layer(merged: dict[str, dict[str, Any]], layer: dict[str, Any], origin: str) -> None:
    """Copy ``layer`` into ``merged`` in place, refusing keys ``merged`` lacks."""
    for section, values in layer.items():
        if section not in merged:
            raise ConfigError(f"{origin}: unknown section [{section}]{_did_you_mean(section, merged)}")
        if not isinstance(values, dict):
            raise ConfigError(f"{origin}: {section} must be a table of settings")
        for key, value in values.items():
            if key not in merged[section]:
                hint = _did_you_mean(key, merged[section], prefix=f"{section}.")
                raise ConfigError(f"{origin}: unknown setting {section}.{key}{hint}")
            merged[section][key] = value


def _did_you_mean(word: str, choices: Iterable[str], prefix: str = "") -> str:
    close = difflib.get_close_matches(word, sorted(choices), n=1)
    return f" (did you mean {prefix}{close[0]}?)" if close else ""


def load_settings(
    overrides: Sequence[str] = (),
    config_path: str | Path | None = None,
    cwd: Path | None = None,
) -> Settings:
    """Merge the three layers and return typed Settings.

    ``cwd`` is where folio.toml is looked for; it defaults to the process's
    working folder and exists so tests do not depend on where they run.
    """
    merged = read_toml(DEFAULTS_PATH)
    if config_path is not None:
        local = Path(config_path)
        merge_layer(merged, read_toml(local), str(local))
    else:
        local = (cwd or Path.cwd()) / LOCAL_NAME
        if local.is_file():
            merge_layer(merged, read_toml(local), str(local))
    for text in overrides:
        override = parse_override(text)
        merge_layer(merged, {override.section: {override.key: override.value}}, f"--set {text}")
    return settings_from_dict(merged)
