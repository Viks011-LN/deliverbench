"""The two legs of a contract (docs/desk-conventions.md, "The premium" and "Valuation"), per dollar of notional."""
from __future__ import annotations

import datetime as dt

from cdslib.curves import CreditCurve, DiscountCurve


def protection_leg(trade_date: dt.date, maturity: dt.date, recovery: float, discount_curve: DiscountCurve,
                   credit_curve: CreditCurve) -> float:
    """The value at the trade date of the protection, per dollar of notional."""
    raise NotImplementedError


def premium_leg(trade_date: dt.date, maturity: dt.date, coupon_bp: float, discount_curve: DiscountCurve,
                credit_curve: CreditCurve) -> float:
    """The value at the trade date of the premium the buyer pays (the coupons to come, the first one whole, and the
    premium accrued at a default), per dollar of notional."""
    raise NotImplementedError
