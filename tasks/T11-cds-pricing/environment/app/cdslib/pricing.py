"""Prices of standard contracts: upfronts, quoted spreads and pricing off a name's curve (docs/desk-conventions.md,
"Prices and quotes")."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from cdslib.curves import CreditCurve, DiscountCurve


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


def upfront_from_quoted_spread(trade_date: dt.date, maturity: dt.date, coupon_bp: float, quoted_spread_bp: float,
                               recovery: float, notional: float, discount_curve: DiscountCurve) -> Upfront:
    """The upfront of a standard contract quoted at `quoted_spread_bp`, on `notional` dollars."""
    raise NotImplementedError


def quoted_spread_from_upfront(trade_date: dt.date, maturity: dt.date, coupon_bp: float, points: float,
                               recovery: float, discount_curve: DiscountCurve) -> float:
    """The quoted spread, in basis points, of a standard contract whose upfront is `points` (percent of notional,
    clean)."""
    raise NotImplementedError


def credit_curve(trade_date: dt.date, quotes: list[tuple[dt.date, float]], recovery: float,
                 discount_curve: DiscountCurve) -> CreditCurve:
    """A name's credit curve from its quotes: (maturity date, par spread in basis points) pairs, as of the trade
    date."""
    raise NotImplementedError


def price_off_curve(trade_date: dt.date, maturity: dt.date, coupon_bp: float, notional: float,
                    quotes: list[tuple[dt.date, float]], recovery: float,
                    discount_curve: DiscountCurve) -> CurvePrice:
    """A standard contract on `notional` dollars priced off the name's credit curve, built from all its quotes
    ((maturity date, par spread in basis points) pairs)."""
    raise NotImplementedError
