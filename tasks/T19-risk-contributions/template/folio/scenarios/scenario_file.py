"""Read the scenario file, scenarios.toml in the data folder.

    [scenarios.equity-sell-off]
    description = "Equities fall 20%, equity funds 15%"
    kind = { equity = -20 }
    sector = { Diversified = -15 }

Each table under [scenarios] is one scenario, and its name is what you type
after ``run``. Price and FX shocks are in percent, the way people say them
(-20 is a 20% fall); yield shifts are in basis points. docs/scenarios.md
describes every key.

Checking happens in two steps. read_scenarios() checks what the file alone
can show: known keys, numbers where numbers belong, sensible ranges.
check_against() then looks the names up in instruments.csv, so that a
misspelt sector is an error instead of a shock that moves nothing, which in
a stress test looks just like a harmless scenario. Both raise ConfigError
naming the file and the scenario.

Scenarios come back sorted by name, so no output depends on the order of the
tables in the file.
"""

from __future__ import annotations

import difflib
import tomllib
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, NoReturn, Sequence

from folio.domain.instruments import Universe
from folio.domain.money import to_decimal
from folio.errors import ConfigError
from folio.scenarios.shocks import (
    PRICE_TARGETS,
    FxShock,
    HistoricalSpec,
    PriceShock,
    Scenario,
    YieldShift,
)

FILE_NAME = "scenarios.toml"
SCENARIO_KEYS = ("description", *PRICE_TARGETS, "fx", "yield_bp", "historical")
HISTORICAL_KEYS = ("days", "scope")

# A plausible entry for each table of percentages, used in error messages.
_EXAMPLES = {"kind": "equity", "sector": "Energy", "instrument": "ADZM", "fx": "USD"}


def read_scenarios(path: str | Path) -> tuple[Scenario, ...]:
    """Read the scenario file at ``path`` and check it on its own; see the module docstring."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"scenario file not found: {path} (see docs/scenarios.md, "
                          f"or pass --scenarios FILE)") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from None
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror}") from None
    return parse_scenarios(document, source=path.name)


def parse_scenarios(document: dict[str, Any], source: str = "<scenarios>") -> tuple[Scenario, ...]:
    """Build the scenarios from an already parsed TOML ``document``; ``source`` names it in errors."""
    unknown = sorted(key for key in document if key != "scenarios")
    if unknown:
        raise ConfigError(f"{source}: unknown top-level key {unknown[0]!r}; each scenario is a "
                          f"[scenarios.<name>] table")
    tables = document.get("scenarios")
    if not isinstance(tables, dict) or not tables:
        raise ConfigError(f"{source}: no scenarios; add a [scenarios.<name>] table")
    return tuple(_ScenarioReader(source, name).read(tables[name]) for name in sorted(tables))


class _ScenarioReader:
    """Typed access to one scenario's table; every error names the file and the scenario."""

    def __init__(self, source: str, name: str):
        self.source = source
        self.name = name

    def fail(self, message: str) -> NoReturn:
        raise ConfigError(f"{self.source}: scenario {self.name}: {message}")

    def read(self, table: Any) -> Scenario:
        if not isinstance(table, dict):
            self.fail("expected a table of shocks, such as kind = { equity = -20 } under [scenarios.NAME]")
        unknown = sorted(key for key in table if key not in SCENARIO_KEYS)
        if unknown:
            self.fail(f"unknown key {unknown[0]!r}{did_you_mean(unknown[0], SCENARIO_KEYS)}; "
                      f"expected {', '.join(SCENARIO_KEYS)}")
        description = table.get("description", "")
        if not isinstance(description, str):
            self.fail(f"description must be a string, got {description!r}")
        try:
            return Scenario(
                name=self.name,
                description=" ".join(description.split()),
                prices=tuple(PriceShock(target, key, change)
                             for target in PRICE_TARGETS for key, change in self.percentages(table, target)),
                fx=tuple(FxShock(currency, change) for currency, change in self.percentages(table, "fx")),
                yields=self.yield_shifts(table.get("yield_bp")),
                historical=self.historical(table.get("historical")),
            )
        except ValueError as exc:
            self.fail(str(exc))

    def percentages(self, table: dict[str, Any], key: str) -> list[tuple[str, Decimal]]:
        """``key = { name = percent, ... }`` as (name, fraction) pairs, in name order."""
        if key not in table:
            return []
        entries = table[key]
        if not isinstance(entries, dict) or not entries:
            self.fail(f"{key} must be a table of percentages, such as {key} = {{ {_EXAMPLES[key]} = -10 }}")
        return [(name, self.number(entries[name], f"{key}.{name}", "a percentage") / 100)
                for name in sorted(entries)]

    def yield_shifts(self, value: Any) -> tuple[YieldShift, ...]:
        """``yield_bp = 100`` shifts every bond; ``yield_bp = { GBP = 150 }`` the bonds of one currency."""
        if value is None:
            return ()
        if not isinstance(value, dict):
            return (YieldShift(self.number(value, "yield_bp", "a number of basis points, or a table "
                                                              "of them by currency")),)
        if not value:
            self.fail("yield_bp is an empty table; give one number, or basis points by currency")
        return tuple(YieldShift(self.number(value[currency], f"yield_bp.{currency}", "a number of basis points"),
                                currency)
                     for currency in sorted(value))

    def historical(self, value: Any) -> HistoricalSpec | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            self.fail('historical must be a table, such as historical = { days = 5, scope = "book" }')
        unknown = sorted(key for key in value if key not in HISTORICAL_KEYS)
        if unknown:
            self.fail(f"unknown key historical.{unknown[0]}; expected {', '.join(HISTORICAL_KEYS)}")
        if "days" not in value:
            self.fail("historical needs days, the length of the move in business days")
        return HistoricalSpec(value["days"], value.get("scope", "book"))

    def number(self, value: Any, where: str, what: str) -> Decimal:
        # TOML gives int or float; a string such as "-20" is refused so that
        # every number in the file is written the same way.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.fail(f"{where} must be {what}, got {value!r}")
        try:
            return to_decimal(value, what=where)
        except ValueError as exc:
            self.fail(str(exc))


def check_against(scenarios: Iterable[Scenario], universe: Universe, base_currency: str,
                  source: str = FILE_NAME) -> None:
    """Refuse sectors and instrument ids that ``universe`` lacks, and shocks to the base currency.

    Instruments that exist but are not held are fine: the shock simply has
    nothing to move today. The base currency is the unit every value is
    measured in, so it cannot move against itself; for a weaker pound, raise
    the other currencies instead.
    """
    known = {"sector": universe.sectors(), "instrument": universe.ids()}
    for scenario in scenarios:
        where = f"{source}: scenario {scenario.name}"
        for shock in scenario.prices:
            names = known.get(shock.target)
            if names is not None and shock.key not in names:
                raise ConfigError(f"{where}: {shock.target} {shock.key!r} is not in instruments.csv"
                                  f"{did_you_mean(shock.key, names)}")
        for shock in scenario.fx:
            if shock.currency == base_currency:
                raise ConfigError(f"{where}: fx.{shock.currency}: {shock.currency} is the base currency; "
                                  f"move the other currencies against it instead")


def find(scenarios: Sequence[Scenario], name: str, source: str = FILE_NAME) -> Scenario:
    """The scenario called ``name``, or a ConfigError suggesting the closest name."""
    for scenario in scenarios:
        if scenario.name == name:
            return scenario
    names = [scenario.name for scenario in scenarios]
    raise ConfigError(f"{source} has no scenario {name!r}{did_you_mean(name, names)}; "
                      f"the list command shows them all")


def did_you_mean(word: str, choices: Iterable[str]) -> str:
    close = difflib.get_close_matches(word, sorted(choices), n=1)
    return f" (did you mean {close[0]}?)" if close else ""
