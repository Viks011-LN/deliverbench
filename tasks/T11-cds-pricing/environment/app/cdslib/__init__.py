"""cdslib: the desk's pricer for standard single-name CDS, to the market's standard model.

The entry points the desk's tools call (dates are datetime.date; coupons and spreads in basis points; recovery a
fraction such as 0.4; notionals and money in dollars):

    load_discount_curve(path)                                               -> DiscountCurve
    payment_schedule(trade_date, maturity, coupon_bp, notional)             -> list[Period]
    upfront_from_quoted_spread(trade_date, maturity, coupon_bp, quoted_spread_bp, recovery, notional,
                               discount_curve)                              -> Upfront
    quoted_spread_from_upfront(trade_date, maturity, coupon_bp, points, recovery, discount_curve)   -> float (bp)
    price_off_curve(trade_date, maturity, coupon_bp, notional, quotes, recovery, discount_curve)    -> CurvePrice

How the modules behind them are organised is up to whoever writes them; these names, their arguments and their
results are what the desk relies on. The conventions are in docs/desk-conventions.md.
"""
from cdslib.curves import CreditCurve, DiscountCurve, load_discount_curve
from cdslib.dates import Period, TradeDates, payment_schedule, trade_dates
from cdslib.pricing import (CurvePrice, Upfront, credit_curve, price_off_curve, quoted_spread_from_upfront,
                            upfront_from_quoted_spread)

__all__ = ["CreditCurve", "CurvePrice", "DiscountCurve", "Period", "TradeDates", "Upfront", "credit_curve",
           "load_discount_curve", "payment_schedule", "price_off_curve", "quoted_spread_from_upfront",
           "trade_dates", "upfront_from_quoted_spread"]
