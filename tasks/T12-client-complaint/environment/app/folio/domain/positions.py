"""Positions and the lots they are built from.

A position is the list of trades (lots) in one instrument. Buys have a
positive quantity and sells a negative one. Quantity and cost are always
worked out "as of" a date, so the same file can answer "what did we hold on
31 August?".

Cost uses the average-cost method: a sell takes cost out at the average cost
of what is held, so the average cost of the remainder does not change.
Short positions are not supported and are rejected when the position is built.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Lot:
    """One trade. A negative quantity is a sale."""

    trade_date: date
    quantity: Decimal
    price: Decimal  # trade price, quoted like the instrument (per 100 for bonds)

    def __post_init__(self) -> None:
        if self.quantity == 0:
            raise ValueError(f"lot on {self.trade_date}: quantity is zero")
        if self.price < 0:
            raise ValueError(f"lot on {self.trade_date}: price {self.price} is negative")

    @property
    def is_buy(self) -> bool:
        return self.quantity > 0


@dataclass(frozen=True)
class Position:
    """All lots in one instrument, kept in trade-date order."""

    instrument_id: str
    lots: tuple[Lot, ...]

    def __post_init__(self) -> None:
        if not self.lots:
            raise ValueError(f"position {self.instrument_id}: no lots")
        # Trade order; sorted() is stable, so same-day lots keep file order.
        object.__setattr__(self, "lots", tuple(sorted(self.lots, key=lambda lot: lot.trade_date)))
        self._held_and_cost(None)  # raises if the lots ever go short

    def lots_as_of(self, as_of: date | None = None) -> tuple[Lot, ...]:
        """The lots traded on or before ``as_of``, or every lot when it is None."""
        if as_of is None:
            return self.lots
        return tuple(lot for lot in self.lots if lot.trade_date < as_of)

    def quantity(self, as_of: date | None = None) -> Decimal:
        return sum((lot.quantity for lot in self.lots_as_of(as_of)), Decimal(0))

    def is_open(self, as_of: date | None = None) -> bool:
        return self.quantity(as_of) != 0

    def average_price(self, as_of: date | None = None) -> Decimal | None:
        """Average cost per unit of what is held, or None if nothing is."""
        held, cost = self._held_and_cost(as_of)
        return cost / held if held else None

    def _held_and_cost(self, as_of: date | None) -> tuple[Decimal, Decimal]:
        held = Decimal(0)
        cost = Decimal(0)
        for lot in self.lots_as_of(as_of):
            if lot.is_buy:
                held += lot.quantity
                cost += lot.quantity * lot.price
                continue
            sold = -lot.quantity
            if sold > held:
                raise ValueError(
                    f"position {self.instrument_id}: the sale of {sold} on {lot.trade_date} is more than "
                    f"the {held} held; short positions are not supported"
                )
            cost -= sold * (cost / held)
            held -= sold
            if held == 0:
                cost = Decimal(0)  # drop rounding dust once the position is closed
        return held, cost

    @property
    def first_trade_date(self) -> date:
        return self.lots[0].trade_date
