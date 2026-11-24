"""Yield to maturity and duration of the bonds we hold.

Good enough for a risk summary, not for trading:

* clean prices only (see the accrued-interest TODO in valuation.py);
* coupons on a regular schedule rolled back from maturity, twice a year for
  GBP, USD and JPY bonds and once a year for EUR bonds, which are the market
  conventions of everything in the book;
* time measured ACT/365 from the valuation date.

Yields are found by bisection, which is slow but cannot fail to converge.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from folio.calc.valuation import PositionValue, Valuation
from folio.domain.instruments import Bond

COUPONS_PER_YEAR = {"EUR": 1}
DEFAULT_COUPONS_PER_YEAR = 2
YIELD_BRACKET = (-0.05, 1.0)
TOLERANCE = 1e-10

Flows = list[tuple[float, float]]  # (years from now, amount per 100 nominal)


@dataclass(frozen=True)
class BondRisk:
    line: PositionValue
    yield_to_maturity: float
    modified_duration: float


def add_months(day: date, months: int) -> date:
    """``day`` moved by ``months``, clamped to the end of a shorter month."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last_day))


def coupon_frequency(bond: Bond) -> int:
    return COUPONS_PER_YEAR.get(bond.currency, DEFAULT_COUPONS_PER_YEAR)


def coupon_dates(maturity: date, after: date, frequency: int) -> list[date]:
    """Coupon dates strictly after ``after``, up to and including maturity, oldest first."""
    step = 12 // frequency
    dates = []
    count = 0
    while (day := add_months(maturity, -step * count)) > after:
        dates.append(day)
        count += 1
    return dates[::-1]


def cash_flows(bond: Bond, as_of: date) -> Flows:
    frequency = coupon_frequency(bond)
    coupon = float(bond.coupon_rate) * 100 / frequency
    flows = [((day - as_of).days / 365, coupon) for day in coupon_dates(bond.maturity, as_of, frequency)]
    if not flows:
        raise ValueError(f"{bond.id} has no cash flows left after {as_of}")
    years, last = flows[-1]
    flows[-1] = (years, last + 100.0)
    return flows


def price_at_yield(flows: Flows, annual_yield: float, frequency: int) -> float:
    per_period = 1.0 + annual_yield / frequency
    return sum(amount / per_period ** (years * frequency) for years, amount in flows)


def yield_to_maturity(flows: Flows, price: float, frequency: int) -> float:
    """The yield at which the flows are worth ``price``."""
    low, high = YIELD_BRACKET
    if not price_at_yield(flows, high, frequency) <= price <= price_at_yield(flows, low, frequency):
        raise ValueError(f"price {price} implies a yield outside {low:.0%} to {high:.0%}")
    while high - low > TOLERANCE:
        middle = (low + high) / 2
        if price_at_yield(flows, middle, frequency) > price:
            low = middle   # price falls as yield rises
        else:
            high = middle
    return (low + high) / 2


def modified_duration(flows: Flows, annual_yield: float, frequency: int) -> float:
    per_period = 1.0 + annual_yield / frequency
    weighted = sum(years * amount / per_period ** (years * frequency) for years, amount in flows)
    macaulay = weighted / price_at_yield(flows, annual_yield, frequency)
    return macaulay / per_period


def bond_risks(valuation: Valuation) -> list[BondRisk]:
    """Yield and modified duration of each bond held, in instrument id order."""
    risks = []
    for line in valuation.positions:
        if not isinstance(line.instrument, Bond):
            continue
        frequency = coupon_frequency(line.instrument)
        flows = cash_flows(line.instrument, valuation.as_of)
        ytm = yield_to_maturity(flows, float(line.price), frequency)
        risks.append(BondRisk(line, ytm, modified_duration(flows, ytm, frequency)))
    return risks


def duration_summary(valuation: Valuation) -> tuple[float, float, float] | None:
    """(bond duration, NAV duration, bond share of NAV), or None if no bonds are held.

    Bond duration is weighted over the bonds only; NAV duration counts every
    other holding as zero, so it is what a 1% parallel move does to NAV.
    """
    risks = bond_risks(valuation)
    if not risks:
        return None
    bond_share = float(sum(risk.line.weight for risk in risks))
    nav_duration = sum(float(risk.line.weight) * risk.modified_duration for risk in risks)
    return nav_duration / bond_share, nav_duration, bond_share
