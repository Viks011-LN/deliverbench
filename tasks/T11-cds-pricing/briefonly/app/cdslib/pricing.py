"""Prices of standard contracts: upfronts, quoted spreads and pricing off a name's curve (docs/desk-conventions.md,
"Prices and quotes")."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from scipy.optimize import brentq

from cdslib.curves import DAYS_PER_YEAR, CreditCurve, DiscountCurve
from cdslib.dates import trade_dates
from cdslib.legs import PREMIUM_DAYS_PER_YEAR, legs_per_unit

BP = 1e-4
# Root-finding tolerances on a hazard rate (per year): far inside a cent on any notional the desk trades.
_HAZARD_XTOL = 1e-15
_HAZARD_RTOL = 1e-14
# Hazard rates are searched up to this before giving up (a name defaulting within days, all but surely).
_MAX_HAZARD = 1e4


@dataclass(frozen=True)
class Upfront:
    """An upfront, from the protection buyer's side (positive when the buyer pays):
    points:  the clean upfront in percent of notional, as the market quotes it (2.5 means 2.5%);
    accrued: the accrued premium in dollars, which the seller pays back at cash settlement;
    cash:    the dollars the buyer pays at cash settlement, after the accrued premium."""
    points: float
    accrued: float
    cash: float


@dataclass(frozen=True)
class CurvePrice:
    """A contract priced off a name's credit curve: its par spread and its quoted spread in basis points, and its
    upfront."""
    par_spread: float
    quoted_spread: float
    upfront: Upfront


class _Contract:
    """A standard contract's dates and the pieces of its clean value that do not depend on the credit curve."""

    def __init__(self, trade_date: dt.date, maturity: dt.date, discount_curve: DiscountCurve):
        if maturity <= trade_date:
            raise ValueError(f"maturity {maturity} is not after the trade date {trade_date}")
        self.trade_date = trade_date
        self.maturity = maturity
        self.dates = trade_dates(trade_date)
        self.discount_curve = discount_curve
        # Carries a value at the trade date forward to the cash settlement date.
        self.df_cash_settle = (discount_curve.discount_factor(self.dates.cash_settle)
                               / discount_curve.discount_factor(trade_date))
        # Accrued premium per unit coupon rate: the days from the accrual start through the trade date, Act/360.
        self.accrued_per_coupon = (self.dates.step_in - self.dates.accrual_start).days / PREMIUM_DAYS_PER_YEAR

    def legs(self, credit_curve: CreditCurve) -> tuple[float, float]:
        """(protection per unit of loss, premium per unit coupon rate), at the trade date, per dollar."""
        return legs_per_unit(self.trade_date, self.maturity, self.discount_curve, credit_curve)

    def clean(self, legs: tuple[float, float], coupon: float, recovery: float) -> float:
        """The clean value to the buyer at the cash settlement date, per dollar, at `coupon` (a rate)."""
        protection, annuity = legs
        dirty = ((1.0 - recovery) * protection - coupon * annuity) / self.df_cash_settle
        return dirty + coupon * self.accrued_per_coupon

    def par_coupon(self, legs: tuple[float, float], recovery: float) -> float:
        """The coupon rate at which the clean value is nothing."""
        protection, annuity = legs
        return (1.0 - recovery) * protection / (annuity - self.accrued_per_coupon * self.df_cash_settle)

    def flat_curve(self, hazard: float) -> CreditCurve:
        return CreditCurve(self.trade_date, [self.maturity], [hazard])

    def upfront(self, legs: tuple[float, float], coupon_bp: float, recovery: float, notional: float) -> Upfront:
        coupon = coupon_bp * BP
        points = 100.0 * self.clean(legs, coupon, recovery)
        accrued = notional * coupon * self.accrued_per_coupon
        return Upfront(points=points, accrued=accrued, cash=notional * points / 100.0 - accrued)


def _solve_hazard(objective, lower: float = 0.0) -> float:
    """The hazard rate at which `objective` (increasing in the rate) is zero, searched from `lower` upwards."""
    f_lo = objective(lower)
    if f_lo == 0.0:
        return lower
    if f_lo > 0.0:
        raise ValueError("no hazard rate at or above the lower bound fits: the quote needs a lower hazard rate")
    upper = max(lower, 0.0) + 0.5
    while objective(upper) < 0.0:
        lower, upper = upper, upper * 4.0
        if upper > _MAX_HAZARD:
            raise ValueError("no finite hazard rate fits the quote")
    return brentq(objective, lower, upper, xtol=_HAZARD_XTOL, rtol=_HAZARD_RTOL, maxiter=500)


def _flat_hazard_for_spread(contract: _Contract, spread: float, recovery: float) -> float:
    """The flat hazard rate at which the contract, at a coupon of `spread` (a rate), is worth nothing clean."""
    return _solve_hazard(lambda h: contract.clean(contract.legs(contract.flat_curve(h)), spread, recovery))


def _quoted_spread(contract: _Contract, coupon: float, points: float, recovery: float) -> float:
    """The quoted spread (a rate) of the contract at `coupon` whose clean upfront is `points`."""
    target = points / 100.0

    def objective(hazard: float) -> float:
        return contract.clean(contract.legs(contract.flat_curve(hazard)), coupon, recovery) - target

    try:
        hazard = _solve_hazard(objective)
    except ValueError as exc:
        raise ValueError(f"no non-negative flat hazard rate gives an upfront of {points} points") from exc
    return contract.par_coupon(contract.legs(contract.flat_curve(hazard)), recovery)


def upfront_from_quoted_spread(trade_date: dt.date, maturity: dt.date, coupon_bp: float, quoted_spread_bp: float,
                               recovery: float, notional: float, discount_curve: DiscountCurve) -> Upfront:
    """The upfront of a standard contract quoted at `quoted_spread_bp`, on `notional` dollars."""
    contract = _Contract(trade_date, maturity, discount_curve)
    hazard = _flat_hazard_for_spread(contract, quoted_spread_bp * BP, recovery)
    return contract.upfront(contract.legs(contract.flat_curve(hazard)), coupon_bp, recovery, notional)


def quoted_spread_from_upfront(trade_date: dt.date, maturity: dt.date, coupon_bp: float, points: float,
                               recovery: float, discount_curve: DiscountCurve) -> float:
    """The quoted spread, in basis points, of a standard contract whose upfront is `points` (percent of notional,
    clean)."""
    contract = _Contract(trade_date, maturity, discount_curve)
    return _quoted_spread(contract, coupon_bp * BP, points, recovery) / BP


def credit_curve(trade_date: dt.date, quotes: list[tuple[dt.date, float]], recovery: float,
                 discount_curve: DiscountCurve) -> CreditCurve:
    """A name's credit curve from its quotes: (maturity date, par spread in basis points) pairs, as of the trade
    date."""
    if not quotes:
        raise ValueError("a credit curve needs at least one quote")
    quotes = sorted((maturity, float(spread)) for maturity, spread in quotes)
    if any(a[0] == b[0] for a, b in zip(quotes, quotes[1:])):
        raise ValueError("two quotes share a maturity")
    dates: list[dt.date] = []
    rates: list[float] = []
    integrated = 0.0                       # hazard integrated to the end of the previous quote's maturity
    previous_day = 0
    for maturity, spread_bp in quotes:
        contract = _Contract(trade_date, maturity, discount_curve)
        spread = spread_bp * BP
        dates.append(maturity)
        rates.append(0.0)

        def objective(hazard: float) -> float:
            rates[-1] = hazard
            curve = CreditCurve(trade_date, dates, rates)
            return contract.clean(contract.legs(curve), spread, recovery)

        day = (maturity - trade_date).days
        try:
            hazard = _solve_hazard(objective)
        except ValueError:
            # The desk's quotes never need a negative hazard rate; should one, allow it down to the rate at which
            # survival to this maturity would reach one, and no further.
            hazard = _solve_hazard(objective, lower=-integrated * DAYS_PER_YEAR / (day - previous_day))
        rates[-1] = hazard
        integrated += hazard * (day - previous_day) / DAYS_PER_YEAR
        previous_day = day
    return CreditCurve(trade_date, dates, rates)


def price_off_curve(trade_date: dt.date, maturity: dt.date, coupon_bp: float, notional: float,
                    quotes: list[tuple[dt.date, float]], recovery: float,
                    discount_curve: DiscountCurve) -> CurvePrice:
    """A standard contract on `notional` dollars priced off the name's credit curve, built from all its quotes
    ((maturity date, par spread in basis points) pairs)."""
    curve = credit_curve(trade_date, quotes, recovery, discount_curve)
    contract = _Contract(trade_date, maturity, discount_curve)
    legs = contract.legs(curve)
    upfront = contract.upfront(legs, coupon_bp, recovery, notional)
    par_spread = contract.par_coupon(legs, recovery) / BP
    quoted_spread = _quoted_spread(contract, coupon_bp * BP, upfront.points, recovery) / BP
    return CurvePrice(par_spread=par_spread, quoted_spread=quoted_spread, upfront=upfront)
