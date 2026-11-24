"""cdslib: the desk's pricer for standard single-name CDS."""
from cdslib.curves import CreditCurve, DiscountCurve, load_discount_curve
from cdslib.dates import Period, TradeDates, payment_schedule, trade_dates
from cdslib.pricing import (CurvePrice, Upfront, credit_curve, price_off_curve, quoted_spread_from_upfront,
                            upfront_from_quoted_spread)

__all__ = ["CreditCurve", "CurvePrice", "DiscountCurve", "Period", "TradeDates", "Upfront", "credit_curve",
           "load_discount_curve", "payment_schedule", "price_off_curve", "quoted_spread_from_upfront",
           "trade_dates", "upfront_from_quoted_spread"]
