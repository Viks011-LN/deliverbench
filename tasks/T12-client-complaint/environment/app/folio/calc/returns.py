"""NAV history and returns.

Risk figures use the *current* holdings revalued at historical prices and FX
("what would today's portfolio have done?"), not the NAV the portfolio
actually had. That is what the VaR limit is meant to measure, and it means a
trade never shows up as a jump in the series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from folio.calc.valuation import Valuation
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory

Series = list[tuple[date, Decimal]]


def history_dates(valuation: Valuation, prices: PriceHistory) -> list[date]:
    """Price dates up to the valuation date, from the first one on which every held instrument has a price.

    Earlier dates would value only part of the portfolio.
    """
    start = max((prices.first_price_date(line.instrument.id) for line in valuation.positions), default=None)
    return [day for day in prices.dates() if day <= valuation.as_of and (start is None or day >= start)]


def line_values(valuation: Valuation, prices: PriceHistory, fx: FxRates, day: date) -> list[Decimal]:
    """Base-currency value on ``day`` of each position, then each cash balance, in valuation order.

    A gap in an instrument's prices (a holiday) is filled with its previous price.
    """
    base = valuation.base_currency
    values = []
    for line in valuation.positions:
        point = prices.latest(line.instrument.id, day)
        local = line.instrument.market_value(line.quantity, point.price)
        values.append(local * fx.rate(line.instrument.currency, base, day))
    values.extend(fx.convert(cash.local_value, base, day).amount for cash in valuation.cash)
    return values


def nav_series(valuation: Valuation, prices: PriceHistory, fx: FxRates) -> Series:
    """NAV of the valuation's holdings and cash on every date of history_dates()."""
    return [
        (day, sum(line_values(valuation, prices, fx, day), Decimal(0)))
        for day in history_dates(valuation, prices)
    ]


def simple_returns(series: Series) -> list[tuple[date, float]]:
    """Day-on-day returns, dated by the later day."""
    returns = []
    for (_, before), (day, after) in zip(series, series[1:]):
        if before <= 0:
            raise ValueError(f"NAV is not positive before {day}; returns are undefined")
        returns.append((day, float(after / before - 1)))
    return returns


def log_returns(series: Series) -> list[tuple[date, float]]:
    return [(day, math.log1p(value)) for day, value in simple_returns(series)]


def cumulative_return(returns: list[float]) -> float:
    growth = 1.0
    for value in returns:
        growth *= 1.0 + value
    return growth - 1.0


def annualise(total_return: float, periods: int, periods_per_year: int) -> float:
    """Compound ``total_return`` earned over ``periods`` up to a year.

    Shown next to the period return only; over a few weeks it exaggerates
    wildly, which is why it is never used in a limit.
    """
    if periods <= 0:
        raise ValueError("cannot annualise a return over no periods")
    if total_return <= -1.0:
        return -1.0
    return (1.0 + total_return) ** (periods_per_year / periods) - 1.0


@dataclass(frozen=True)
class Drawdown:
    depth: float          # negative, e.g. -0.034 for a 3.4% fall
    peak: date
    trough: date
    recovered: date | None  # first day back at the peak level, None if not yet


def max_drawdown(series: Series) -> Drawdown | None:
    """Largest peak-to-trough fall in the series, or None if it never falls."""
    if not series:
        return None
    peak_day, peak_value = series[0]
    worst: tuple[float, date, date, Decimal] | None = None
    for day, value in series:
        if value > peak_value:
            peak_day, peak_value = day, value
            continue
        depth = float(value / peak_value - 1)
        if depth < 0 and (worst is None or depth < worst[0]):
            worst = (depth, peak_day, day, peak_value)
    if worst is None:
        return None
    depth, peak, trough, level = worst
    recovered = next((day for day, value in series if day > trough and value >= level), None)
    return Drawdown(depth, peak, trough, recovered)
