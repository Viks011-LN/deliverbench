"""Instrument reference data.

An instrument is anything the portfolio can hold. Its kind decides how a
quantity and a price become a market value:

* Equity and Fund: quantity x price.
* Bond: nominal x clean price / 100, because bond prices are quoted per 100
  of nominal. Accrued interest is not included (see the TODO in
  calc/valuation.py).

Instruments are immutable. A Universe holds the instruments loaded from
instruments.csv, keyed by id, and always iterates in id order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import ClassVar, Iterable, Iterator

from folio.domain.money import check_currency

KINDS = ("equity", "bond", "fund")


@dataclass(frozen=True)
class Instrument:
    """Fields shared by every kind. Build one of the subclasses, not this."""

    id: str
    name: str
    sector: str
    currency: str
    country: str = ""
    issuer: str = ""

    kind: ClassVar[str] = "instrument"

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip() or " " in self.id:
            raise ValueError(f"invalid instrument id {self.id!r}: it must be non-empty and contain no spaces")
        if not self.name.strip():
            raise ValueError(f"instrument {self.id}: name is empty")
        if not self.sector.strip():
            raise ValueError(f"instrument {self.id}: sector is empty")
        try:
            check_currency(self.currency)
        except ValueError as exc:
            raise ValueError(f"instrument {self.id}: {exc}") from None

    @property
    def issuer_key(self) -> str:
        """Who we are exposed to if this goes wrong; the instrument itself unless an issuer is set."""
        return self.issuer or self.id

    def market_value(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Value of ``quantity`` at ``price``, in the instrument's currency."""
        return quantity * price


@dataclass(frozen=True)
class Equity(Instrument):
    kind: ClassVar[str] = "equity"


@dataclass(frozen=True)
class Bond(Instrument):
    coupon_rate: Decimal = Decimal(0)  # annual, as a fraction: 0.0425 is 4.25%
    maturity: date | None = None

    kind: ClassVar[str] = "bond"
    PRICE_BASIS: ClassVar[Decimal] = Decimal(100)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not Decimal(0) <= self.coupon_rate < Decimal(1):
            raise ValueError(f"bond {self.id}: coupon_rate {self.coupon_rate} must be a fraction such as 0.0425")
        if self.maturity is None:
            raise ValueError(f"bond {self.id}: maturity is required")

    def market_value(self, quantity: Decimal, price: Decimal) -> Decimal:
        return quantity * price / self.PRICE_BASIS

    def is_matured(self, as_of: date) -> bool:
        return self.maturity <= as_of


@dataclass(frozen=True)
class Fund(Instrument):
    expense_ratio: Decimal = Decimal(0)  # annual, as a fraction: 0.0020 is 20 bp

    kind: ClassVar[str] = "fund"

    def __post_init__(self) -> None:
        super().__post_init__()
        if not Decimal(0) <= self.expense_ratio < Decimal("0.1"):
            raise ValueError(f"fund {self.id}: expense_ratio {self.expense_ratio} looks wrong; "
                             f"expected a fraction such as 0.0035")


_CLASSES: dict[str, type[Instrument]] = {"equity": Equity, "bond": Bond, "fund": Fund}


def make_instrument(kind: str, **fields) -> Instrument:
    """Build an instrument of ``kind`` from keyword fields."""
    try:
        cls = _CLASSES[kind]
    except KeyError:
        raise ValueError(f"unknown instrument kind {kind!r}; expected one of: {', '.join(KINDS)}") from None
    return cls(**fields)


class Universe:
    """All known instruments, keyed by id. Iteration is in id order."""

    def __init__(self, instruments: Iterable[Instrument] = ()):
        self._by_id: dict[str, Instrument] = {}
        for instrument in instruments:
            self.add(instrument)

    def add(self, instrument: Instrument) -> None:
        if instrument.id in self._by_id:
            raise ValueError(f"duplicate instrument id {instrument.id}")
        self._by_id[instrument.id] = instrument

    def __getitem__(self, instrument_id: str) -> Instrument:
        try:
            return self._by_id[instrument_id]
        except KeyError:
            raise KeyError(f"unknown instrument {instrument_id!r}") from None

    def __contains__(self, instrument_id: object) -> bool:
        return instrument_id in self._by_id

    def __iter__(self) -> Iterator[Instrument]:
        for instrument_id in sorted(self._by_id):
            yield self._by_id[instrument_id]

    def __len__(self) -> int:
        return len(self._by_id)

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def sectors(self) -> list[str]:
        return sorted({instrument.sector for instrument in self._by_id.values()})
