"""The two legs of a contract (docs/desk-conventions.md, "The premium" and "Valuation"), per dollar of notional."""
from __future__ import annotations

import bisect
import datetime as dt
import math

from cdslib.curves import DAYS_PER_YEAR, CreditCurve, DiscountCurve
from cdslib.dates import accrual_periods

# Over a piece where the hazard and the forward rate, each taken as its total over the piece, add up to less than
# this in absolute value, the standard uses the numerical fix note's series instead of the exact formula.
SERIES_THRESHOLD = 1e-4
# The standard's half-day adjustment to the time accrued at a default, in days.
HALF_DAY = 0.5
# Premium accrues Actual/360.
PREMIUM_DAYS_PER_YEAR = 360.0


class _Curves:
    """The discount and credit curves seen from the end of a trade date, on whole calendar days after it.

    Day d stands for the end of the d-th calendar day after the trade date (day 0 is the end of the trade date,
    the moment protection starts); its time is d / 365."""

    def __init__(self, trade_date: dt.date, discount_curve: DiscountCurve, credit_curve: CreditCurve):
        self._disc = discount_curve
        self._credit = credit_curve
        self._disc_offset = (trade_date - discount_curve.curve_date).days
        self._credit_offset = (trade_date - credit_curve.trade_date).days
        self._disc_base = discount_curve._neg_log_df(self._disc_offset)
        self._credit_base = credit_curve._neg_log_survival(self._credit_offset)
        nodes = {(date - trade_date).days for date in discount_curve.pillar_dates}
        nodes |= {(date - trade_date).days for date in credit_curve.node_dates}
        # Days where the forward rate or the hazard rate may change: both are flat in between.
        self.nodes = sorted(day for day in nodes if day > 0)
        self._cache: dict[int, tuple[float, float]] = {}

    def logs(self, day: int) -> tuple[float, float]:
        """(integrated hazard, minus log discount factor) from day 0 to `day`."""
        cached = self._cache.get(day)
        if cached is None:
            hazard = self._credit._neg_log_survival(day + self._credit_offset) - self._credit_base
            rate = self._disc._neg_log_df(day + self._disc_offset) - self._disc_base
            cached = self._cache[day] = (hazard, rate)
        return cached

    def survival(self, day: int) -> float:
        return math.exp(-self.logs(day)[0])

    def discount(self, day: int) -> float:
        return math.exp(-self.logs(day)[1])

    def pieces(self, start: int, end: int):
        """The pieces of [start, end] (days) over which both rates are flat."""
        lo = bisect.bisect_right(self.nodes, start)
        hi = bisect.bisect_left(self.nodes, end)
        points = [start, *self.nodes[lo:hi], end]
        return zip(points[:-1], points[1:])


def _protection_piece(lam: float, x: float) -> float:
    """Integral over one flat piece of hazard times survival times discount, divided by S0 * D0, where `lam` is the
    piece's total hazard and `x` its total hazard plus total forward rate (numerical fix note, page 3)."""
    if abs(x) < SERIES_THRESHOLD:
        return lam * (1.0 - x / 2.0 + x * x / 6.0 - x ** 3 / 24.0 + x ** 4 / 120.0)
    return lam / x * (-math.expm1(-x))


def _accrual_piece(lam: float, x: float, t0: float, t1: float) -> float:
    """Integral over one flat piece of (time accrued) times hazard times survival times discount, divided by
    S0 * D0, where the time accrued runs linearly from `t0` to `t1` (years) over the piece (numerical fix note,
    pages 2-3: A / (S0 * D0))."""
    if abs(x) < SERIES_THRESHOLD:
        return lam * ((t0 + t1) / 2.0 - (t0 + 2.0 * t1) / 6.0 * x + (t0 + 3.0 * t1) / 24.0 * x ** 2
                      - (t0 + 4.0 * t1) / 120.0 * x ** 3 + (t0 + 5.0 * t1) / 720.0 * x ** 4)
    dt_ = t1 - t0
    return lam * ((t0 + dt_ / x) / x - (t1 + dt_ / x) / x * math.exp(-x))


def _protection_value(curves: _Curves, maturity_day: int) -> float:
    """The value at the trade date of one dollar paid at a default from the end of the trade date (day 0) to the
    end of the maturity date."""
    total = 0.0
    for a, b in curves.pieces(0, maturity_day):
        h0, g0 = curves.logs(a)
        h1, g1 = curves.logs(b)
        lam = h1 - h0
        total += math.exp(-h0 - g0) * _protection_piece(lam, lam + (g1 - g0))
    return total


def _accrued_at_default(curves: _Curves, first_day: int, end_day: int) -> float:
    """The value at the trade date of the premium accrued at a default, per unit of coupon rate, in a period that
    accrues from day `first_day` (its first day of accrual, relative to the trade date) up to day `end_day`
    (excluded). Defaults count from the start of the step-in date (day 0) on; the time accrued runs from the start
    of the period's first day, plus half a day."""
    origin = first_day - 1                     # the start of the first day of accrual is the end of the day before
    start, end = max(origin, 0), end_day - 1   # the last day of accrual ends at end_day - 1
    if end <= start:
        return 0.0
    total = 0.0
    for a, b in curves.pieces(start, end):
        h0, g0 = curves.logs(a)
        h1, g1 = curves.logs(b)
        lam = h1 - h0
        t0 = (a - origin + HALF_DAY) / DAYS_PER_YEAR
        t1 = (b - origin + HALF_DAY) / DAYS_PER_YEAR
        total += math.exp(-h0 - g0) * _accrual_piece(lam, lam + (g1 - g0), t0, t1)
    # A year of 365 days of accrual earns 365/360 of the coupon rate on an Actual/360 basis.
    return total * DAYS_PER_YEAR / PREMIUM_DAYS_PER_YEAR


def _annuity(curves: _Curves, trade_date: dt.date, maturity: dt.date) -> float:
    """The value at the trade date of the premium leg per unit of coupon rate: every coupon, the first one whole,
    plus the premium accrued at a default."""
    total = 0.0
    for start, end, pay in accrual_periods(trade_date, maturity):
        first_day, end_day, pay_day = ((d - trade_date).days for d in (start, end, pay))
        accrual = (end_day - first_day) / PREMIUM_DAYS_PER_YEAR
        # Paid if the name survives to the end of the period's last day of accrual.
        total += accrual * curves.survival(end_day - 1) * curves.discount(pay_day)
        total += _accrued_at_default(curves, first_day, end_day)
    return total


def protection_leg(trade_date: dt.date, maturity: dt.date, recovery: float, discount_curve: DiscountCurve,
                   credit_curve: CreditCurve) -> float:
    """The value at the trade date of the protection, per dollar of notional."""
    curves = _Curves(trade_date, discount_curve, credit_curve)
    return (1.0 - recovery) * _protection_value(curves, (maturity - trade_date).days)


def premium_leg(trade_date: dt.date, maturity: dt.date, coupon_bp: float, discount_curve: DiscountCurve,
                credit_curve: CreditCurve) -> float:
    """The value at the trade date of the premium the buyer pays (the coupons to come, the first one whole, and the
    premium accrued at a default), per dollar of notional."""
    curves = _Curves(trade_date, discount_curve, credit_curve)
    return coupon_bp / 10_000.0 * _annuity(curves, trade_date, maturity)


def legs_per_unit(trade_date: dt.date, maturity: dt.date, discount_curve: DiscountCurve,
                  credit_curve: CreditCurve) -> tuple[float, float]:
    """(protection per unit of loss, premium leg per unit of coupon rate), both at the trade date, per dollar of
    notional: the building blocks of every price, computed once for a curve."""
    if maturity <= trade_date:
        raise ValueError(f"maturity {maturity} is not after the trade date {trade_date}")
    curves = _Curves(trade_date, discount_curve, credit_curve)
    return _protection_value(curves, (maturity - trade_date).days), _annuity(curves, trade_date, maturity)
