"""Value a portfolio on a date, in the base currency.

value_portfolio() joins the open positions with their instruments, takes the
latest price on or before the valuation date, converts each line to the base
currency at that date's FX rate and works out its weight in NAV. NAV is the
sum of the positions plus cash.

Prices older than ``stale_after_days`` business days are still used but the
line is flagged as stale: a fund that prices monthly would otherwise stop the
whole run for most of the month.

TODO: bonds are valued clean. Add accrued interest once instruments.csv has
coupon dates; until then bond weights are understated by the accrued coupon.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from folio.data.business_days import business_days_between, roll_back
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory
from folio.domain.instruments import Bond, Instrument, Universe
from folio.domain.money import Money, sum_money
from folio.domain.portfolio import Portfolio
from folio.errors import ValuationError


@dataclass(frozen=True)
class PositionValue:
    """One open position valued on the valuation date."""

    instrument: Instrument
    quantity: Decimal
    price: Decimal
    price_date: date
    fx_rate: Decimal          # value of one unit of the instrument's currency in base currency
    local_value: Money
    base_value: Money
    cost_value: Money | None  # what the held quantity cost, in local currency
    weight: Decimal           # base_value / NAV
    stale: bool = False

    @property
    def unrealised(self) -> Money | None:
        if self.cost_value is None:
            return None
        return self.local_value - self.cost_value

    @property
    def unrealised_pct(self) -> Decimal | None:
        """Price return on cost in local currency, e.g. Decimal('0.042') for +4.2%."""
        if self.cost_value is None or self.cost_value.is_zero():
            return None
        return self.local_value.amount / self.cost_value.amount - 1


@dataclass(frozen=True)
class CashValue:
    """One cash balance converted to the base currency."""

    local_value: Money
    fx_rate: Decimal
    base_value: Money
    weight: Decimal


@dataclass(frozen=True)
class Valuation:
    """A portfolio valued on one date: every line in base currency, and NAV.

    This is what every report, export and limit works from. Nothing in it is
    rounded; formatting is left to report/.
    """

    portfolio_code: str
    portfolio_name: str
    as_of: date
    base_currency: str
    positions: tuple[PositionValue, ...]  # in instrument id order
    cash: tuple[CashValue, ...]           # in currency order
    nav: Money

    @property
    def invested(self) -> Money:
        return sum_money((line.base_value for line in self.positions), self.base_currency)

    @property
    def cash_total(self) -> Money:
        return sum_money((line.base_value for line in self.cash), self.base_currency)

    def position(self, instrument_id: str) -> PositionValue:
        for line in self.positions:
            if line.instrument.id == instrument_id:
                return line
        raise KeyError(f"{self.portfolio_code} holds no {instrument_id} on {self.as_of}")

    def stale_positions(self) -> list[PositionValue]:
        return [line for line in self.positions if line.stale]


def resolve_as_of(requested: date, prices: PriceHistory) -> tuple[date, str | None]:
    """Turn a requested valuation date into the one we can actually use.

    A weekend rolls back to the Friday before, and a date after the last price
    in the file becomes that last price date, so ``folio value`` with no
    --as-of still works on a data folder that was refreshed a while ago.
    Returns the date and a note for the user, or None if nothing changed.
    """
    first, last = prices.first_date(), prices.last_date()
    if first is None or last is None:
        raise ValuationError("the price file has no prices")
    if requested < first:
        raise ValuationError(f"cannot value on {requested}: the first prices are for {first}")
    if requested > last:
        return last, f"valuing as of {last}, the last date in the price file (asked for {requested})"
    effective = roll_back(requested)
    if effective != requested:
        return effective, f"valuing as of {effective}: {requested} is not a business day"
    return requested, None


def value_portfolio(
    portfolio: Portfolio,
    universe: Universe,
    prices: PriceHistory,
    fx: FxRates,
    as_of: date,
    *,
    base_currency: str,
    stale_after_days: int,
) -> Valuation:
    """Value ``portfolio`` on ``as_of`` in ``base_currency``.

    Raises ValuationError when nothing is held, a held bond has matured or NAV is
    not positive, and MissingPriceError when a price or FX rate is missing.
    """
    try:
        holdings = portfolio.holdings(universe, as_of)
    except ValueError as exc:
        raise ValuationError(str(exc)) from None
    balances = portfolio.cash_balances()
    if not holdings and not balances:
        raise ValuationError(f"portfolio {portfolio.code} holds nothing on {as_of}")

    lines = []
    for holding in holdings:
        instrument = holding.instrument
        if isinstance(instrument, Bond) and instrument.is_matured(as_of):
            raise ValuationError(f"{instrument.id} matured on {instrument.maturity} but is still held on "
                                 f"{as_of}; book the redemption in positions.json")
        point = prices.latest(instrument.id, as_of)
        rate = fx.rate(instrument.currency, base_currency, as_of)
        local = Money(instrument.market_value(holding.quantity, point.price), instrument.currency)
        cost = None
        if holding.average_price is not None:
            cost = Money(instrument.market_value(holding.quantity, holding.average_price), instrument.currency)
        stale = business_days_between(point.day, as_of) > stale_after_days
        lines.append((holding, point, rate, local, cost, stale))

    cash_lines = [(balance, fx.rate(balance.currency, base_currency, as_of)) for balance in balances]

    nav_amount = sum((local.amount * rate for _, _, rate, local, _, _ in lines), Decimal(0))
    nav_amount += sum((balance.amount * rate for balance, rate in cash_lines), Decimal(0))
    nav = Money(nav_amount, base_currency)
    if nav_amount <= 0:
        raise ValuationError(f"NAV of {portfolio.code} on {as_of} is {nav.rounded()}; weights would be meaningless")

    positions = tuple(
        PositionValue(
            instrument=holding.instrument,
            quantity=holding.quantity,
            price=point.price,
            price_date=point.day,
            fx_rate=rate,
            local_value=local,
            base_value=Money(local.amount * rate, base_currency),
            cost_value=cost,
            weight=local.amount * rate / nav_amount,
            stale=stale,
        )
        for holding, point, rate, local, cost, stale in lines
    )
    cash = tuple(
        CashValue(balance, rate, Money(balance.amount * rate, base_currency), balance.amount * rate / nav_amount)
        for balance, rate in cash_lines
    )
    return Valuation(portfolio.code, portfolio.name, as_of, base_currency, positions, cash, nav)
