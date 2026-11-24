"""From an amount of money to a quantity that can be dealt.

A proposal decides its trades as base-currency values; the dealer needs
quantities. A Quote holds what the conversion needs for one instrument on
the valuation date: the price as quoted and the rate to the base currency.
Held instruments reuse the valuation's own price and rate, so a trade and
the holding it changes are valued alike. An instrument the book does not
hold yet is priced from the price and FX files on the same date.

Quantities are whole multiples of the instrument's round lot (dealing.py).
quantity_for() rounds to the nearest lot when a trade is sized, and down,
towards zero, when a trade has to fit into a fixed amount of cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from folio.calc.valuation import Valuation
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory
from folio.domain.instruments import Instrument, Universe
from folio.domain.money import Money


@dataclass(frozen=True)
class Quote:
    """The price and FX rate a trade in one instrument is valued at."""

    instrument: Instrument
    price: Decimal    # as quoted: per unit, or per 100 nominal for bonds
    fx_rate: Decimal  # base currency per unit of the instrument's currency

    def local_value(self, quantity: Decimal) -> Money:
        return Money(self.instrument.market_value(quantity, self.price), self.instrument.currency)

    def base_value(self, quantity: Decimal) -> Decimal:
        return self.instrument.market_value(quantity, self.price) * self.fx_rate

    @property
    def unit_value(self) -> Decimal:
        """Base-currency value of one unit of quantity: one share, or one of nominal."""
        return self.base_value(Decimal(1))


class Quotes:
    """Quotes on the valuation date, for held instruments and for new ones."""

    def __init__(self, valuation: Valuation, universe: Universe, prices: PriceHistory, fx: FxRates):
        self._valuation = valuation
        self._universe = universe
        self._prices = prices
        self._fx = fx
        self._held = {line.instrument.id: line for line in valuation.positions}

    def quote(self, instrument_id: str) -> Quote:
        """Raises MissingPriceError when an instrument not held has no price or rate."""
        line = self._held.get(instrument_id)
        if line is not None:
            return Quote(line.instrument, line.price, line.fx_rate)
        instrument = self._universe[instrument_id]
        as_of = self._valuation.as_of
        point = self._prices.latest(instrument_id, as_of)
        rate = self._fx.rate(instrument.currency, self._valuation.base_currency, as_of)
        return Quote(instrument, point.price, rate)


def to_lots(quantity: Decimal, lot: Decimal, rounding: str = ROUND_HALF_EVEN) -> Decimal:
    """``quantity`` as a whole number of ``lot``s, keeping its sign; zero is plain 0."""
    lots = (quantity / lot).quantize(Decimal(1), rounding=rounding)
    return lots * lot if lots else Decimal(0)


def quantity_for(value: Decimal, quote: Quote, lot: Decimal, rounding: str = ROUND_HALF_EVEN) -> Decimal:
    """The quantity worth ``value`` in the base currency (signed), in whole lots."""
    return to_lots(value / quote.unit_value, lot, rounding)
