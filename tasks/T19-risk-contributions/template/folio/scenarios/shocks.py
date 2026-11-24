"""Shock types: what a stress scenario does to prices, currencies and yields.

A scenario is a named set of shocks, read from scenarios.toml by
scenario_file.py. There are three kinds of shock and a scenario may mix them:

* PriceShock moves the price of every instrument of one kind, of one sector,
  or of one instrument id, by a fraction (-0.2 is a 20% fall).
* FxShock moves the value of one currency in the base currency. It moves
  every position in that currency and the cash held in it.
* YieldShift moves bond yields in parallel by a number of basis points, for
  every bond or only for the bonds of one currency. The engine turns it into
  a price change through each bond's modified duration.

Shocks that hit the same holding compound rather than add: an equity in a
shocked sector moves by (1 + kind change) x (1 + sector change) - 1. Adding
them would let two -60% shocks push a price below zero.

A historical scenario (HistoricalSpec) has no shocks of its own; history.py
finds its moves in the price file when the scenario is run.

Whatever its type, a scenario applied to a book comes down to Moves: one
price change per held instrument and one change per currency. revalue() is
the one formula that turns those into a stressed value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from folio.domain.instruments import KINDS, Bond, Instrument
from folio.domain.money import check_currency

PRICE_TARGETS = ("kind", "sector", "instrument")
HISTORICAL_SCOPES = ("book", "instrument")
MAX_SHIFT_BP = Decimal(1000)
BASIS_POINT = Decimal("0.0001")

# The instrument attribute that each price target is matched against.
_TARGET_ATTRIBUTES = {"kind": "kind", "sector": "sector", "instrument": "id"}


def signed_percent(change: Decimal) -> str:
    """``Decimal('-0.125')`` -> ``'-12.5%'``, ``Decimal('0.05')`` -> ``'+5%'``: as written in the file."""
    return f"{(change * 100).normalize():+f}%"


def revalue(amount: Decimal, price_change: Decimal, fx_change: Decimal) -> Decimal:
    """A base-currency ``amount`` after its price and its currency have moved by these fractions."""
    return amount * (1 + price_change) * (1 + fx_change)


def _check_change(change: Decimal, what: str) -> None:
    if change < -1:
        raise ValueError(f"{what}: nothing can lose more than 100% of its value")


@dataclass(frozen=True)
class PriceShock:
    """Move the price of every instrument whose kind, sector or id is ``key``."""

    target: str      # one of PRICE_TARGETS
    key: str
    change: Decimal  # fraction: -0.2 is a 20% fall

    def __post_init__(self) -> None:
        if self.target not in PRICE_TARGETS:
            raise ValueError(f"unknown price shock target {self.target!r}; "
                             f"expected one of: {', '.join(PRICE_TARGETS)}")
        if self.target == "kind" and self.key not in KINDS:
            raise ValueError(f"unknown kind {self.key!r}; expected one of: {', '.join(KINDS)}")
        _check_change(self.change, self.describe())

    def applies_to(self, instrument: Instrument) -> bool:
        return getattr(instrument, _TARGET_ATTRIBUTES[self.target]) == self.key

    def describe(self) -> str:
        return f"{self.target} {self.key} {signed_percent(self.change)}"


@dataclass(frozen=True)
class FxShock:
    """Move the value of one unit of ``currency`` in the base currency (+0.1: it buys 10% more)."""

    currency: str
    change: Decimal

    def __post_init__(self) -> None:
        check_currency(self.currency)
        _check_change(self.change, self.describe())

    def describe(self) -> str:
        return f"{self.currency} {signed_percent(self.change)}"


@dataclass(frozen=True)
class YieldShift:
    """A parallel move in bond yields: every bond, or only the bonds in ``currency``."""

    bp: Decimal                  # basis points; +100 is one percentage point higher
    currency: str | None = None

    def __post_init__(self) -> None:
        if self.currency is not None:
            check_currency(self.currency)
        if abs(self.bp) > MAX_SHIFT_BP:
            raise ValueError(f"{self.describe()}: shifts are limited to {MAX_SHIFT_BP} bp either way; "
                             f"beyond that a duration estimate means little")

    def applies_to(self, instrument: Instrument) -> bool:
        return isinstance(instrument, Bond) and self.currency in (None, instrument.currency)

    def price_change(self, modified_duration: Decimal) -> Decimal:
        """First-order price change of a bond with this duration, never below -100%."""
        return max(-modified_duration * self.bp * BASIS_POINT, Decimal(-1))

    def describe(self) -> str:
        where = f"{self.currency} yields" if self.currency else "yields"
        return f"{where} {self.bp.normalize():+f}bp"


@dataclass(frozen=True)
class HistoricalSpec:
    """Replay the worst ``days``-business-day move found in the price history.

    ``scope`` "book" replays the one window in which today's book would have
    lost most; "instrument" gives every holding its own worst move at once.
    """

    days: int
    scope: str = "book"

    def __post_init__(self) -> None:
        if isinstance(self.days, bool) or not isinstance(self.days, int) or self.days < 1:
            raise ValueError(f"historical days must be a whole number of business days, 1 or more, "
                             f"got {self.days!r}")
        if self.scope not in HISTORICAL_SCOPES:
            raise ValueError(f"historical scope must be one of: {', '.join(HISTORICAL_SCOPES)}; "
                             f"got {self.scope!r}")

    def describe(self) -> str:
        of = "the book" if self.scope == "book" else "each instrument"
        return f"worst {self.days}-day move of {of}"


@dataclass(frozen=True)
class Scenario:
    """One named what-if: shocks from the file, or a historical replay."""

    name: str
    description: str = ""
    prices: tuple[PriceShock, ...] = ()
    fx: tuple[FxShock, ...] = ()
    yields: tuple[YieldShift, ...] = ()
    historical: HistoricalSpec | None = None

    def __post_init__(self) -> None:
        bare = self.name.replace("-", "").replace("_", "")
        if not bare.isascii() or not bare.isalnum():
            raise ValueError(f"invalid scenario name {self.name!r}: it is typed on the command line, "
                             f"so use only letters, digits, '-' and '_'")
        shocked = bool(self.prices or self.fx or self.yields)
        if self.historical is not None and shocked:
            raise ValueError("a historical scenario takes its moves from the price history and cannot "
                             "have shocks of its own; put them in a scenario of their own")
        if self.historical is None and not shocked:
            raise ValueError("no shocks; give at least one of kind, sector, instrument, fx, yield_bp "
                             "or historical")

    def shock_summary(self) -> list[str]:
        """One phrase per shock: price shocks, then currencies, then yields."""
        if self.historical is not None:
            return [self.historical.describe()]
        return [shock.describe() for shock in (*self.prices, *self.fx, *self.yields)]


@dataclass(frozen=True)
class Window:
    """The two price dates a historical move was measured between."""

    start: date
    end: date

    def __str__(self) -> str:
        return f"{self.start} to {self.end}"


@dataclass(frozen=True)
class Moves:
    """A scenario applied to one book.

    ``prices`` maps instrument ids to price changes and ``fx`` maps currencies
    to changes in their base-currency value; whatever is not listed does not
    move. For a historical scenario ``windows`` says where each instrument's
    move was measured, and ``window`` is the one window of a whole-book replay.
    """

    prices: dict[str, Decimal]
    fx: dict[str, Decimal]
    windows: dict[str, Window] = field(default_factory=dict)
    window: Window | None = None

    def price_change(self, instrument_id: str) -> Decimal:
        return self.prices.get(instrument_id, Decimal(0))

    def fx_change(self, currency: str) -> Decimal:
        return self.fx.get(currency, Decimal(0))
