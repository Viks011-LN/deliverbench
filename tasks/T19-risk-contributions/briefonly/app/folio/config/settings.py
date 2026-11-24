"""Typed settings, one frozen dataclass per section of defaults.toml.

The fields have no defaults on purpose. config/defaults.toml is the only place
where a default value is written down, and settings_from_dict() refuses both a
key that the dataclass does not know and a field that the file does not set,
so the two cannot drift apart unnoticed.

Each dataclass checks its own ranges in __post_init__ and raises ConfigError
naming the setting as users type it in --set (``limits.sector_max_share``).
"""

from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from folio.domain.money import check_currency, to_decimal
from folio.errors import ConfigError


def _require(condition: bool, name: str, rule: str, value: Any) -> None:
    if not condition:
        shown = str(value) if isinstance(value, Decimal) else repr(value)
        raise ConfigError(f"{name} must be {rule}, got {shown}")


@dataclass(frozen=True)
class ReportSettings:
    money_places: int
    percent_places: int
    show_cash: bool
    top_n: int
    stale_price_days: int

    def __post_init__(self) -> None:
        _require(0 <= self.money_places <= 6, "report.money_places", "between 0 and 6", self.money_places)
        _require(0 <= self.percent_places <= 4, "report.percent_places", "between 0 and 4", self.percent_places)
        _require(self.top_n >= 0, "report.top_n", "0 or more", self.top_n)
        _require(self.stale_price_days >= 0, "report.stale_price_days", "0 or more", self.stale_price_days)


@dataclass(frozen=True)
class RiskSettings:
    var_confidence: float
    var_lookback_days: int
    min_observations: int
    horizon_days: int
    annualisation_days: int
    histogram_step: float

    def __post_init__(self) -> None:
        _require(0.5 <= self.var_confidence < 1, "risk.var_confidence", "at least 0.5 and below 1",
                 self.var_confidence)
        _require(self.var_lookback_days >= 2, "risk.var_lookback_days", "2 or more", self.var_lookback_days)
        _require(2 <= self.min_observations <= self.var_lookback_days, "risk.min_observations",
                 f"between 2 and risk.var_lookback_days ({self.var_lookback_days})", self.min_observations)
        _require(1 <= self.horizon_days <= 250, "risk.horizon_days", "between 1 and 250", self.horizon_days)
        _require(self.annualisation_days > 0, "risk.annualisation_days", "above 0", self.annualisation_days)
        _require(0 < self.histogram_step < 1, "risk.histogram_step", "a fraction between 0 and 1",
                 self.histogram_step)


@dataclass(frozen=True)
class LimitSettings:
    """Limit thresholds. Every ``*_max_share`` is a fraction in (0, 1]: of NAV, except
    ``name_vol_max_share``, which is a fraction of the portfolio's volatility."""

    sector_max_share: Decimal
    name_max_share: Decimal
    currency_max_share: Decimal
    var_max_share: Decimal
    name_vol_max_share: Decimal
    disabled: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            if field.name.endswith("_max_share"):
                value = getattr(self, field.name)
                of = "the portfolio's volatility" if field.name == "name_vol_max_share" else "NAV"
                _require(Decimal(0) < value <= Decimal(1), f"limits.{field.name}",
                         f"a fraction of {of} above 0 and at most 1", value)
        _require(len(set(self.disabled)) == len(self.disabled), "limits.disabled", "a list without repeats",
                 list(self.disabled))


@dataclass(frozen=True)
class FxSettings:
    base_currency: str
    pivot_currency: str
    max_rate_age_days: int

    def __post_init__(self) -> None:
        for name in ("base_currency", "pivot_currency"):
            try:
                check_currency(getattr(self, name))
            except ValueError as exc:
                raise ConfigError(f"fx.{name}: {exc}") from None
        _require(self.max_rate_age_days >= 0, "fx.max_rate_age_days", "0 or more", self.max_rate_age_days)


@dataclass(frozen=True)
class Settings:
    """All settings, one attribute per section of defaults.toml."""

    report: ReportSettings
    risk: RiskSettings
    limits: LimitSettings
    fx: FxSettings


SECTIONS: dict[str, type] = {
    "report": ReportSettings,
    "risk": RiskSettings,
    "limits": LimitSettings,
    "fx": FxSettings,
}


def settings_from_dict(data: dict[str, dict[str, Any]]) -> Settings:
    """Build Settings from merged TOML data, checking names and types."""
    unknown_sections = sorted(set(data) - set(SECTIONS))
    if unknown_sections:
        raise ConfigError(f"unknown settings section [{unknown_sections[0]}]")
    sections = {}
    for section, cls in SECTIONS.items():
        values = data.get(section, {})
        hints = typing.get_type_hints(cls)
        names = [field.name for field in dataclasses.fields(cls)]
        unknown = sorted(set(values) - set(names))
        if unknown:
            raise ConfigError(f"unknown setting {section}.{unknown[0]}: there is no such field in "
                              f"{cls.__name__} (config/settings.py)")
        missing = [name for name in names if name not in values]
        if missing:
            raise ConfigError(f"setting {section}.{missing[0]} has no value; add it to config/defaults.toml")
        kwargs = {name: coerce(values[name], hints[name], f"{section}.{name}") for name in names}
        sections[section] = cls(**kwargs)
    return Settings(**sections)


def coerce(value: Any, target: Any, name: str) -> Any:
    """Convert a TOML value to the field type ``target``, or raise ConfigError.

    TOML already gives us bool, int, float, str and list. The only real
    conversions are float to Decimal (via str, so 0.25 stays exactly 0.25)
    and a comma-separated string to a tuple, which is what --set gives for
    ``--set limits.disabled=var_share,name_share``.
    """
    is_bool = isinstance(value, bool)
    if target is bool:
        if is_bool:
            return value
        raise ConfigError(f"{name} must be true or false, got {value!r}")
    if target is int:
        if isinstance(value, int) and not is_bool:
            return value
        raise ConfigError(f"{name} must be a whole number, got {value!r}")
    if target is float:
        if isinstance(value, (int, float)) and not is_bool:
            return float(value)
        raise ConfigError(f"{name} must be a number, got {value!r}")
    if target is Decimal:
        if isinstance(value, (int, float, str)) and not is_bool:
            try:
                return to_decimal(value, what=name)
            except ValueError:
                pass
        raise ConfigError(f"{name} must be a number, got {value!r}")
    if target is str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise ConfigError(f"{name} must be a non-empty string, got {value!r}")
    if target == tuple[str, ...]:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
        raise ConfigError(f"{name} must be a list of names, got {value!r}")
    raise TypeError(f"no conversion for {name} of type {target!r}")
