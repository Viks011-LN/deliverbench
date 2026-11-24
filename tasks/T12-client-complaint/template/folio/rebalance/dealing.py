"""Read trading.toml: the dealing rules a rebalancing proposal has to respect.

    min_ticket = 25000            # smallest trade worth sending, base currency
    cash_buffer = 0.01            # share of NAV that stays in cash after the trades
    bonds_in_nominal_multiples = true

    [lots]                        # round lot per instrument kind
    equity = 1
    bond = 1000

    [instrument_lots]             # instruments that deal in other lots
    KIWQ = 100

Every key is optional; an absent one means no minimum ticket, no buffer,
bonds in nominal multiples and a lot of 1. Trade quantities are whole
multiples of the instrument's round lot: its own if [instrument_lots] lists
it, else its kind's. Bond quantities are nominal, so a bond lot of 1000 is
1,000 of nominal. With bonds_in_nominal_multiples = false bonds deal in any
whole amount of nominal and bond lots are not used; a bond in
[instrument_lots] is then an error, since the line would do nothing.

The rules are not folio settings: they describe how this book is dealt, so
they sit in the data folder next to the targets. As with the settings, an
unknown key is an error, with a suggestion when one is close.
"""

from __future__ import annotations

import dataclasses
import difflib
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from folio.domain.instruments import KINDS, Instrument, Universe
from folio.domain.money import Money, to_decimal
from folio.errors import DataError

KEYS = ("min_ticket", "cash_buffer", "bonds_in_nominal_multiples", "lots", "instrument_lots")
DEFAULT_LOT = Decimal(1)


def check_cash_buffer(value: Decimal, name: str = "cash_buffer") -> Decimal:
    """``value`` if it is a usable cash buffer (a share of NAV, 0 up to but not 1)."""
    if not Decimal(0) <= value < Decimal(1):
        raise ValueError(f"{name} must be a share of NAV from 0 up to 1, such as 0.01, got {value}")
    return value


@dataclass(frozen=True)
class DealingRules:
    """Round lots, minimum ticket and cash buffer for one book."""

    min_ticket: Money                 # in the base currency
    cash_buffer: Decimal              # share of NAV
    bonds_in_nominal_multiples: bool = True
    kind_lots: dict[str, Decimal] = field(default_factory=dict)
    instrument_lots: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.min_ticket.amount < 0:
            raise ValueError(f"min_ticket must be 0 or more, got {self.min_ticket.amount}")
        check_cash_buffer(self.cash_buffer)
        for name, lots in (("lots", self.kind_lots), ("instrument_lots", self.instrument_lots)):
            for key, lot in sorted(lots.items()):
                if lot <= 0:
                    raise ValueError(f"{name}.{key} must be above 0, got {lot}")

    def lot_for(self, instrument: Instrument) -> Decimal:
        """The round lot ``instrument`` deals in, in units (nominal for bonds)."""
        if instrument.kind == "bond" and not self.bonds_in_nominal_multiples:
            return DEFAULT_LOT
        if instrument.id in self.instrument_lots:
            return self.instrument_lots[instrument.id]
        return self.kind_lots.get(instrument.kind, DEFAULT_LOT)

    def with_overrides(self, cash_buffer: Decimal | None = None, min_ticket: Decimal | None = None) -> DealingRules:
        """A copy with the command-line --cash-buffer and --min-ticket applied (None keeps the file's)."""
        changes: dict[str, Any] = {}
        if cash_buffer is not None:
            changes["cash_buffer"] = cash_buffer
        if min_ticket is not None:
            changes["min_ticket"] = Money(min_ticket, self.min_ticket.currency)
        return dataclasses.replace(self, **changes)


def load_rules(path, universe: Universe, base_currency: str) -> DealingRules:
    """Read trading.toml at ``path``; amounts in it are in ``base_currency``."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError:
        raise DataError(f"dealing rules file not found: {path} (use --rules)") from None
    except tomllib.TOMLDecodeError as exc:
        raise DataError(f"not valid TOML: {exc}", source=path.name) from None
    return parse_rules(document, universe, base_currency, source=path.name)


def parse_rules(document: dict[str, Any], universe: Universe, base_currency: str,
                source: str = "<rules>") -> DealingRules:
    """Build DealingRules from an already parsed TOML ``document``."""
    try:
        _refuse_unknown(document, KEYS, "")
        nominal = document.get("bonds_in_nominal_multiples", True)
        if not isinstance(nominal, bool):
            raise ValueError(f"bonds_in_nominal_multiples must be true or false, got {nominal!r}")
        kind_lots = _lots(document, "lots")
        _refuse_unknown(kind_lots, KINDS, "lots.")
        instrument_lots = _lots(document, "instrument_lots")
        for instrument_id in sorted(instrument_lots):
            if instrument_id not in universe:
                raise ValueError(f"instrument_lots lists {instrument_id}, which is not in instruments.csv")
            if universe[instrument_id].kind == "bond" and not nominal:
                raise ValueError(f"instrument_lots.{instrument_id} has no effect: bond lots are not used while "
                                 f"bonds_in_nominal_multiples is false")
        return DealingRules(
            min_ticket=Money(_number(document.get("min_ticket", 0), "min_ticket"), base_currency),
            cash_buffer=_number(document.get("cash_buffer", 0), "cash_buffer"),
            bonds_in_nominal_multiples=nominal,
            kind_lots=kind_lots,
            instrument_lots=instrument_lots,
        )
    except ValueError as exc:
        raise DataError(str(exc), source=source) from None


def _lots(document: dict[str, Any], name: str) -> dict[str, Decimal]:
    table = document.get(name, {})
    if not isinstance(table, dict):
        raise ValueError(f"{name} must be a table such as [{name}]")
    return {key: _number(value, f"{name}.{key}") for key, value in sorted(table.items())}


def _number(value: Any, name: str) -> Decimal:
    try:
        return to_decimal(value, what=name)
    except TypeError:
        raise ValueError(f"{name} must be a number, got {value!r}") from None


def _refuse_unknown(table: dict[str, Any], known: tuple[str, ...], prefix: str) -> None:
    for key in sorted(table):
        if key not in known:
            close = difflib.get_close_matches(key, sorted(known), n=1)
            hint = f" (did you mean {prefix}{close[0]}?)" if close else f"; expected one of: {', '.join(known)}"
            raise ValueError(f"unknown key {prefix}{key}{hint}")
