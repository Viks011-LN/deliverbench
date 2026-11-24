"""The two legs of a contract, valued exactly in continuous time.

Between the dates where either curve has a knot, the hazard rate and the forward interest rate are both flat, so
each piece of the protection leg and of the premium accrued on default has a closed form (the integrals in the
methodology paper, evaluated exactly rather than with its monthly points or half-coupon shortcut). Where the hazard
and the forward rate over a piece add up to almost nothing, the closed form divides by almost nothing; there the
standard uses a series expansion instead (ISDA's 2012 note on a numerical fix), from the same threshold.

Days are counted from the trade date. A survival observed "at day d" is survival to the end of day d. Protection
starts at the end of the trade date (the start of the step-in date) and ends at the end of the maturity date; a
coupon is paid if the name survives to the end of its period's last accrual day (docs/desk-conventions.md).
"""
from __future__ import annotations

import math

from cdslib.curves import CreditCurve, DiscountCurve
from cdslib.dates import DAY_COUNT_BASIS, Period, TradeDates

YEAR_DAYS = 365.0
SERIES_THRESHOLD = 1e-4     # ISDA's 2012 note: below this, the series replaces the closed form
TINY = 1e-50                # keeps a piece with no hazard and no rate from dividing by zero
HALF_DAY = 0.5              # the standard's half-day adjustment to the time accrued at default


def knots_between(start: int, end: int, *curves) -> list[int]:
    """start, end and every curve knot strictly between them, in order (days)."""
    inside = {d for curve in curves for d in curve.knot_days if start < d < end}
    return [start, *sorted(inside), end]


def protection_leg(dates: TradeDates, maturity_day: int, recovery: float, discount: DiscountCurve,
                   credit: CreditCurve) -> float:
    """(1 - recovery) paid at default, from the end of the trade date to the end of the maturity date; per unit of
    notional, valued at the trade date."""
    loss = 1.0 - recovery
    total = 0.0
    points = knots_between(0, maturity_day, discount, credit)
    s0, d0 = credit.log_survival(points[0]), discount.log_discount(points[0])
    for day in points[1:]:
        s1, d1 = credit.log_survival(day), discount.log_discount(day)
        hazard, rate = s0 - s1, d0 - d1
        both = hazard + rate + TINY
        start = math.exp(s0 + d0)
        if abs(both) > SERIES_THRESHOLD:
            piece = loss * hazard / both * (1.0 - math.exp(-both)) * start
        else:
            piece = loss * hazard * start * (1.0 - both / 2 + both ** 2 / 6 - both ** 3 / 24 + both ** 4 / 120)
        total += piece
        s0, d0 = s1, d1
    return total


def accrued_on_default(period: Period, coupon: float, step_in_day: int, discount: DiscountCurve,
                       credit: CreditCurve, trade: object) -> float:
    """The premium accrued since the period's start and paid at a default inside the period (from the step-in date
    on), per unit of notional, valued at the trade date. The time accrued at a default is measured from the start
    of the period's first day, plus half a day."""
    first = (period.accrual_start - trade).days - 1     # the end of the day before the period starts
    last = (period.accrual_end - trade).days - 1        # the end of the period's last accrual day
    amount = coupon * (period.accrual_end - period.accrual_start).days / DAY_COUNT_BASIS
    rate_per_year = amount / ((last - first) / YEAR_DAYS)
    begin = max(step_in_day - 1, first)
    if last <= begin:
        return 0.0
    total = 0.0
    points = knots_between(begin, last, discount, credit)
    s0, d0 = credit.log_survival(begin), discount.log_discount(max(begin, 0))
    for before, day in zip(points, points[1:]):
        s1, d1 = credit.log_survival(day), discount.log_discount(day)
        t0 = (before + HALF_DAY - first) / YEAR_DAYS
        t1 = (day + HALF_DAY - first) / YEAR_DAYS
        t = t1 - t0
        hazard, rate = s0 - s1, d0 - d1
        both = hazard + rate + TINY
        start = math.exp(s0 + d0)
        if abs(both) > SERIES_THRESHOLD:
            piece = hazard * rate_per_year * start * (
                (t0 + t / both) / both - (t1 + t / both) / both * math.exp(-both))
        else:
            piece = hazard * rate_per_year * start * (
                (t0 + t1) / 2 - (t0 + 2 * t1) / 6 * both + (t0 + 3 * t1) / 24 * both ** 2
                - (t0 + 4 * t1) / 120 * both ** 3 + (t0 + 5 * t1) / 720 * both ** 4)
        total += piece
        s0, d0 = s1, d1
    return total


def premium_leg(dates: TradeDates, periods: list[Period], coupon: float, discount: DiscountCurve,
                credit: CreditCurve) -> float:
    """Every coupon still to come (paid if the name survives its period) plus the premium accrued on default; per
    unit of notional at the given coupon (a decimal), valued at the trade date. Includes the whole first coupon."""
    trade = dates.trade_date
    step_in_day = (dates.step_in - trade).days
    total = 0.0
    for period in periods:
        if period.accrual_end <= dates.step_in:
            continue
        amount = coupon * (period.accrual_end - period.accrual_start).days / DAY_COUNT_BASIS
        survive = math.exp(credit.log_survival((period.accrual_end - trade).days - 1))
        total += amount * survive * discount.discount_factor(period.pay_date)
        total += accrued_on_default(period, coupon, step_in_day, discount, credit, trade)
    return total


def accrued_premium(periods: list[Period], step_in, coupon: float) -> float:
    """The premium accrued in the current period up to the step-in date (excluded), per unit of notional: what the
    seller pays back at settlement, since the buyer pays the whole first coupon."""
    for period in periods:
        if period.accrual_start < step_in < period.accrual_end:
            return coupon * (step_in - period.accrual_start).days / DAY_COUNT_BASIS
    return 0.0
