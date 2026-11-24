"""Prices of standard contracts: the quoting convention (one flat hazard rate), a name's term structure, and the
conversions between upfront and quoted spread (docs/desk-conventions.md, "Prices and quotes")."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from cdslib.curves import CreditCurve, DiscountCurve
from cdslib.dates import TradeDates, payment_schedule, trade_dates
from cdslib.legs import accrued_premium, premium_leg, protection_leg

BP = 1e-4


@dataclass(frozen=True)
class Upfront:
    """An upfront from the protection buyer's side: positive when the buyer pays.
    points: the clean upfront, in percent of notional (what the market quotes);
    accrued: the premium accrued before the step-in date, which the seller pays back at settlement;
    cash: what the buyer pays at cash settlement, notional x points / 100 - accrued."""
    points: float
    accrued: float
    cash: float


@dataclass(frozen=True)
class CurvePrice:
    """A contract priced off a name's term structure: its par spread and quoted spread (bp) and its upfront."""
    par_spread: float
    quoted_spread: float
    upfront: Upfront


@dataclass(frozen=True)
class Contract:
    dates: TradeDates
    maturity: dt.date
    periods: list

    @staticmethod
    def make(trade_date: dt.date, maturity: dt.date) -> "Contract":
        return Contract(trade_dates(trade_date), maturity, payment_schedule(trade_date, maturity, 1.0, 1.0))

    def legs(self, coupon: float, recovery: float, discount: DiscountCurve, credit: CreditCurve) -> tuple:
        """(protection, premium, accrued) per unit notional at a coupon (decimal): the two legs valued at the
        cash settlement date, and the accrued premium paid there."""
        trade = self.dates.trade_date
        grow = 1.0 / discount.discount_factor(self.dates.cash_settle)
        protection = protection_leg(self.dates, (self.maturity - trade).days, recovery, discount, credit) * grow
        premium = premium_leg(self.dates, self.periods, coupon, discount, credit) * grow
        return protection, premium, accrued_premium(self.periods, self.dates.step_in, coupon)

    def clean_value(self, coupon: float, recovery: float, discount: DiscountCurve, credit: CreditCurve) -> float:
        protection, premium, accrued = self.legs(coupon, recovery, discount, credit)
        return protection - premium + accrued

    def upfront(self, coupon: float, recovery: float, notional: float, discount: DiscountCurve,
                credit: CreditCurve) -> Upfront:
        protection, premium, accrued = self.legs(coupon, recovery, discount, credit)
        clean = protection - premium + accrued
        return Upfront(points=100.0 * clean, accrued=notional * accrued, cash=notional * (clean - accrued))

    def par_spread(self, recovery: float, discount: DiscountCurve, credit: CreditCurve) -> float:
        """The coupon (decimal) at which the contract has no clean upfront."""
        protection, premium, accrued = self.legs(1.0, recovery, discount, credit)
        return protection / (premium - accrued)


def check_discount_curve(trade_date: dt.date, discount: DiscountCurve) -> None:
    if discount.curve_date != trade_date:
        raise ValueError(f"the discount curve is for {discount.curve_date}, the trade date is {trade_date}")


def solve(f, lo: float, hi: float, tol: float = 1e-15, iterations: int = 200) -> float:
    """A root of f in [lo, hi] (f(lo) and f(hi) of opposite signs), by Brent's method."""
    a, b, fa, fb = lo, hi, f(lo), f(hi)
    if fa * fb > 0:
        raise ValueError("the root is not bracketed")
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc, d, bisected = a, fa, b - a, True
    for _ in range(iterations):
        if fb == 0 or abs(b - a) <= tol * max(1.0, abs(b)):
            return b
        if fa != fc and fb != fc:
            s = (a * fb * fc / ((fa - fb) * (fa - fc)) + b * fa * fc / ((fb - fa) * (fb - fc))
                 + c * fa * fb / ((fc - fa) * (fc - fb)))
        else:
            s = b - fb * (b - a) / (fb - fa)
        lower, upper = sorted(((3 * a + b) / 4, b))
        if (not lower < s < upper or (bisected and abs(s - b) >= abs(b - c) / 2)
                or (not bisected and abs(s - b) >= abs(c - d) / 2)):
            s, bisected = (a + b) / 2, True
        else:
            bisected = False
        fs = f(s)
        d, c, fc = c, b, fb
        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
    return b


def fit_credit_curve(trade_date: dt.date, quotes: list[tuple[dt.date, float]], recovery: float,
                     discount: DiscountCurve) -> CreditCurve:
    """The name's hazard rates, one maturity at a time: each quote (maturity, par spread as a decimal) is a contract
    traded today whose clean value at that coupon is zero."""
    quotes = sorted(quotes)
    knots, hazards = [], []
    for maturity, spread in quotes:
        contract = Contract.make(trade_date, maturity)

        def value(h: float) -> float:
            return contract.clean_value(spread, recovery, discount,
                                        CreditCurve(trade_date, knots + [maturity], hazards + [h]))

        hi = max(spread / (1 - recovery), 1e-4)
        while value(hi) < 0:
            hi *= 2
            if hi > 1e3:
                raise ValueError(f"no hazard rate fits the quote at {maturity}")
        if value(0.0) > 0:
            raise ValueError(f"the quote at {maturity} needs a negative hazard rate")
        hazard = solve(value, 0.0, hi)
        knots.append(maturity)
        hazards.append(hazard)
    return CreditCurve(trade_date, knots, hazards)


def flat_curve(trade_date: dt.date, maturity: dt.date, quoted_spread: float, recovery: float,
               discount: DiscountCurve) -> CreditCurve:
    """The quoting convention: one flat hazard rate, fitted to the contract itself at the quoted spread."""
    return fit_credit_curve(trade_date, [(maturity, quoted_spread)], recovery, discount)


def upfront_from_quoted_spread(trade_date: dt.date, maturity: dt.date, coupon_bp: float, quoted_spread_bp: float,
                               recovery: float, notional: float, discount_curve: DiscountCurve) -> Upfront:
    check_discount_curve(trade_date, discount_curve)
    credit = flat_curve(trade_date, maturity, quoted_spread_bp * BP, recovery, discount_curve)
    return Contract.make(trade_date, maturity).upfront(coupon_bp * BP, recovery, notional, discount_curve, credit)


def quoted_spread_from_upfront(trade_date: dt.date, maturity: dt.date, coupon_bp: float, points: float,
                               recovery: float, discount_curve: DiscountCurve) -> float:
    check_discount_curve(trade_date, discount_curve)
    contract = Contract.make(trade_date, maturity)

    def gap(spread: float) -> float:
        credit = flat_curve(trade_date, maturity, spread, recovery, discount_curve)
        return contract.clean_value(coupon_bp * BP, recovery, discount_curve, credit) - points / 100.0

    hi = 0.01
    while gap(hi) < 0:
        hi *= 2
        if hi > 100:
            raise ValueError(f"no quoted spread gives {points} points")
    lo = 1e-9
    if gap(lo) > 0:
        raise ValueError(f"no positive quoted spread gives {points} points")
    return solve(gap, lo, hi, tol=1e-13) / BP


def credit_curve(trade_date: dt.date, quotes: list[tuple[dt.date, float]], recovery: float,
                 discount_curve: DiscountCurve) -> CreditCurve:
    check_discount_curve(trade_date, discount_curve)
    return fit_credit_curve(trade_date, [(m, s * BP) for m, s in quotes], recovery, discount_curve)


def price_off_curve(trade_date: dt.date, maturity: dt.date, coupon_bp: float, notional: float,
                    quotes: list[tuple[dt.date, float]], recovery: float, discount_curve: DiscountCurve) -> CurvePrice:
    credit = credit_curve(trade_date, quotes, recovery, discount_curve)
    contract = Contract.make(trade_date, maturity)
    upfront = contract.upfront(coupon_bp * BP, recovery, notional, discount_curve, credit)
    par = contract.par_spread(recovery, discount_curve, credit) / BP
    quoted = quoted_spread_from_upfront(trade_date, maturity, coupon_bp, upfront.points, recovery, discount_curve)
    return CurvePrice(par_spread=par, quoted_spread=quoted, upfront=upfront)
