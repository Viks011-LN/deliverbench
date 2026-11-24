"""The desk's discount curve and a name's credit curve.

Both are piecewise flat in their forward rate: the discount curve's forward interest rate is flat between its
pillars, and the credit curve's hazard rate is flat between the maturities of the name's quotes (the methodology
paper's "piecewise flat" hazard rate structure; docs/desk-conventions.md, "Curves"). Time is counted in days
from the trade date over 365.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import math
from pathlib import Path

YEAR_DAYS = 365.0


class PiecewiseFlat:
    """A curve given by its integral at knots (days from the curve date): linear between knots, through zero at
    the curve date, and continued along its last piece after the last knot."""

    def __init__(self, days: list[int], integrals: list[float]):
        if not days or any(b <= a for a, b in zip(days, days[1:])) or days[0] <= 0:
            raise ValueError("knots must be strictly increasing and after the curve date")
        self.days = list(days)
        self.integrals = list(integrals)

    def integral(self, day: float) -> float:
        days, values = self.days, self.integrals
        if day <= days[0]:
            return values[0] * day / days[0]
        if len(days) == 1:
            return values[0] * day / days[0]
        i = bisect.bisect_left(days, day)
        if i < len(days) and days[i] == day:
            return values[i]
        i = min(i, len(days) - 1)
        d0, d1, v0, v1 = days[i - 1], days[i], values[i - 1], values[i]
        return v0 + (v1 - v0) * (day - d0) / (d1 - d0)


class DiscountCurve:
    """The desk's discount curve: continuously compounded zero rates, Actual/365 Fixed, from the curve date."""

    def __init__(self, curve_date: dt.date, pillars: list[tuple[dt.date, float]]):
        self.curve_date = curve_date
        self.pillars = sorted(pillars)
        days = [(d - curve_date).days for d, _ in self.pillars]
        self._curve = PiecewiseFlat(days, [r * n / YEAR_DAYS for (_, r), n in zip(self.pillars, days)])

    @property
    def knot_days(self) -> list[int]:
        return self._curve.days

    def log_discount(self, day: float) -> float:
        """The natural log of the discount factor `day` days after the curve date."""
        return -self._curve.integral(day)

    def discount_factor(self, date: dt.date) -> float:
        return math.exp(self.log_discount((date - self.curve_date).days))


def load_discount_curve(path: str | Path) -> DiscountCurve:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path}: no pillars")
    curve_dates = {row["curve_date"] for row in rows}
    if len(curve_dates) != 1:
        raise ValueError(f"{path}: one curve date expected, found {sorted(curve_dates)}")
    return DiscountCurve(dt.date.fromisoformat(curve_dates.pop()),
                         [(dt.date.fromisoformat(row["maturity"]), float(row["zero_rate"])) for row in rows])


class CreditCurve:
    """A name's survival curve: the hazard rate is flat between knots (the quotes' maturity dates), from the trade
    date to the first knot, and after the last knot at the last piece's rate."""

    def __init__(self, trade_date: dt.date, knots: list[dt.date], hazards: list[float]):
        self.trade_date = trade_date
        self.knots = list(knots)
        self.hazards = list(hazards)
        days = [(k - trade_date).days for k in knots]
        total, integrals, previous = 0.0, [], 0
        for d, h in zip(days, hazards):
            total += h * (d - previous) / YEAR_DAYS
            integrals.append(total)
            previous = d
        self._curve = PiecewiseFlat(days, integrals)

    @property
    def knot_days(self) -> list[int]:
        return self._curve.days

    def log_survival(self, day: float) -> float:
        """The natural log of the probability of surviving to the end of the day `day` days after the trade date."""
        return -self._curve.integral(day)

    def survival(self, date: dt.date) -> float:
        return math.exp(self.log_survival((date - self.trade_date).days))
