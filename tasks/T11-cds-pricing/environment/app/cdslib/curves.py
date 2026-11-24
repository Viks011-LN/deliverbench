"""The desk's discount curve and a name's credit curve (docs/desk-conventions.md, "Curves")."""
from __future__ import annotations

import datetime as dt
from pathlib import Path


class DiscountCurve:
    """The curve service's discount curve: zero rates to pillar dates, from the curve date."""

    curve_date: dt.date

    def discount_factor(self, date: dt.date) -> float:
        """The value at the curve date of one dollar paid on `date`."""
        raise NotImplementedError


def load_discount_curve(path: str | Path) -> DiscountCurve:
    """The curve in a file in the curve service's format (data/discount-curve.csv: columns curve_date, tenor,
    maturity, zero_rate)."""
    raise NotImplementedError


class CreditCurve:
    """A name's credit curve: the probability that the name has not defaulted."""

    trade_date: dt.date

    def survival(self, date: dt.date) -> float:
        """The probability that the name survives to the end of `date`, seen from the trade date."""
        raise NotImplementedError
