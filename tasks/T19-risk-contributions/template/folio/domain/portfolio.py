"""A portfolio: positions keyed by instrument id, plus cash by currency."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from folio.domain.instruments import Instrument, Universe
from folio.domain.money import Money, check_currency
from folio.domain.positions import Position


@dataclass(frozen=True)
class Holding:
    """What the portfolio holds of one instrument on one date."""

    instrument: Instrument
    quantity: Decimal
    average_price: Decimal | None


@dataclass
class Portfolio:
    """One portfolio: positions keyed by instrument id, cash keyed by currency."""

    code: str
    name: str
    positions: dict[str, Position] = field(default_factory=dict)
    # Cash is today's balance per currency. There is no cash ledger yet, so
    # valuing an earlier date uses the same balances.
    # TODO: book cash movements with the lots so that cash can be "as of" too.
    cash: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code or not self.code.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"invalid portfolio code {self.code!r}: use letters, digits, '-' and '_'")
        for currency in self.cash:
            check_currency(currency)
        for key, position in self.positions.items():
            if key != position.instrument_id:
                raise ValueError(f"position stored under {key!r} is for {position.instrument_id!r}")

    def add_position(self, position: Position) -> None:
        if position.instrument_id in self.positions:
            raise ValueError(f"portfolio {self.code}: more than one position in {position.instrument_id}")
        self.positions[position.instrument_id] = position

    def open_positions(self, as_of: date) -> list[Position]:
        """Positions with a non-zero quantity on ``as_of``, in instrument id order."""
        return [self.positions[key] for key in sorted(self.positions) if self.positions[key].is_open(as_of)]

    def cash_balances(self) -> list[Money]:
        """Non-zero cash balances, in currency order."""
        return [Money(self.cash[currency], currency) for currency in sorted(self.cash) if self.cash[currency] != 0]

    def unknown_instruments(self, universe: Universe) -> list[str]:
        return sorted(key for key in self.positions if key not in universe)

    def holdings(self, universe: Universe, as_of: date) -> list[Holding]:
        """Join open positions with their instruments."""
        unknown = self.unknown_instruments(universe)
        if unknown:
            raise ValueError(f"portfolio {self.code} holds instruments that are not in the instrument file: "
                             f"{', '.join(unknown)}")
        return [
            Holding(universe[position.instrument_id], position.quantity(as_of), position.average_price(as_of))
            for position in self.open_positions(as_of)
        ]
