"""Estimated running costs of the funds we hold.

A fund takes its expense ratio out of its own price, so the cost never shows
up as a cash flow in the portfolio. We estimate it from today's value: a year
of fees is the base value times the expense ratio. Over a period, use
accrue() with the day count of the period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from folio.calc.valuation import PositionValue, Valuation
from folio.domain.instruments import Fund
from folio.domain.money import Money, sum_money

DAY_COUNTS = {"ACT/365": Decimal(365), "ACT/360": Decimal(360)}


@dataclass(frozen=True)
class FundCost:
    line: PositionValue
    annual: Money  # in base currency


def accrue(annual_rate: Decimal, amount: Decimal, start: date, end: date, basis: str = "ACT/365") -> Decimal:
    """Fee on ``amount`` at ``annual_rate`` from ``start`` to ``end``."""
    try:
        year = DAY_COUNTS[basis]
    except KeyError:
        raise ValueError(f"unknown day count {basis!r}; expected one of {', '.join(sorted(DAY_COUNTS))}") from None
    if end < start:
        raise ValueError(f"fee period ends ({end}) before it starts ({start})")
    return amount * annual_rate * Decimal((end - start).days) / year


def fund_costs(valuation: Valuation) -> list[FundCost]:
    """Annual cost of each fund held, largest first (ties by instrument id)."""
    costs = [
        FundCost(line, line.base_value * line.instrument.expense_ratio)
        for line in valuation.positions
        if isinstance(line.instrument, Fund) and line.instrument.expense_ratio > 0
    ]
    return sorted(costs, key=lambda cost: (-cost.annual.amount, cost.line.instrument.id))


def total_fund_cost(valuation: Valuation) -> Money:
    return sum_money((cost.annual for cost in fund_costs(valuation)), valuation.base_currency)


def cost_ratio(valuation: Valuation) -> Decimal:
    """Fund costs as a fraction of the whole NAV (a look-through ongoing charge)."""
    return total_fund_cost(valuation).amount / valuation.nav.amount


def year_to_date(valuation: Valuation) -> Money:
    """Fund costs from 1 January to the valuation date, at today's values.

    An estimate: it assumes we held today's funds at today's values all year.
    """
    start = date(valuation.as_of.year, 1, 1)
    total = sum(
        (accrue(cost.line.instrument.expense_ratio, cost.line.base_value.amount, start, valuation.as_of)
         for cost in fund_costs(valuation)),
        Decimal(0),
    )
    return Money(total, valuation.base_currency)
