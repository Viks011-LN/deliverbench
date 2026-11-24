"""The desk's discount curve and a name's credit curve (docs/desk-conventions.md, "Curves")."""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import math
from pathlib import Path
from typing import Sequence

# Time is counted in calendar days over 365 (Actual/365 Fixed), for discounting and for survival.
DAYS_PER_YEAR = 365.0


class DiscountCurve:
    """The curve service's discount curve: zero rates to pillar dates, from the curve date."""

    curve_date: dt.date

    def __init__(self, curve_date: dt.date, pillar_dates: Sequence[dt.date], zero_rates: Sequence[float]):
        """Continuously compounded Actual/365 Fixed zero rates from `curve_date` to each pillar date. The forward
        rate is flat between pillars and from the curve date to the first pillar; after the last pillar the last
        forward rate carries on."""
        if len(pillar_dates) != len(zero_rates) or not pillar_dates:
            raise ValueError("a discount curve needs one zero rate per pillar date, and at least one pillar")
        pillars = sorted(zip(pillar_dates, zero_rates))
        days = [(date - curve_date).days for date, _ in pillars]
        if days[0] <= 0 or any(b <= a for a, b in zip(days, days[1:])):
            raise ValueError("discount curve pillars must be distinct dates after the curve date")
        self.curve_date = curve_date
        self.pillar_dates = [date for date, _ in pillars]
        self.zero_rates = [float(rate) for _, rate in pillars]
        self._days = days
        # r * t at each pillar: minus the log of the discount factor.
        self._rt = [rate * day / DAYS_PER_YEAR for rate, day in zip(self.zero_rates, days)]

    def _neg_log_df(self, days: float) -> float:
        """Minus the log of the discount factor `days` calendar days after the curve date (flat forwards)."""
        knots, rt = self._days, self._rt
        if days <= knots[0]:
            return rt[0] * days / knots[0]
        i = bisect.bisect_left(knots, days)
        if i == len(knots):                       # after the last pillar: the last forward rate carries on
            if len(knots) == 1:
                return rt[0] * days / knots[0]
            fwd = (rt[-1] - rt[-2]) / (knots[-1] - knots[-2])
            return rt[-1] + fwd * (days - knots[-1])
        lo, hi = knots[i - 1], knots[i]
        return rt[i - 1] + (rt[i] - rt[i - 1]) * (days - lo) / (hi - lo)

    def discount_factor(self, date: dt.date) -> float:
        """The value at the curve date of one dollar paid on `date`."""
        return math.exp(-self._neg_log_df((date - self.curve_date).days))

    def __repr__(self) -> str:
        return f"DiscountCurve(curve_date={self.curve_date}, pillars={len(self.pillar_dates)})"


def load_discount_curve(path: str | Path) -> DiscountCurve:
    """The curve in a file in the curve service's format (data/discount-curve.csv: columns curve_date, tenor,
    maturity, zero_rate)."""
    with open(path, newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("maturity", "").strip()]
    if not rows:
        raise ValueError(f"no pillars in {path}")
    curve_dates = {row["curve_date"].strip() for row in rows}
    if len(curve_dates) != 1:
        raise ValueError(f"{path} holds more than one curve date: {sorted(curve_dates)}")
    curve_date = dt.date.fromisoformat(curve_dates.pop())
    return DiscountCurve(curve_date,
                         [dt.date.fromisoformat(row["maturity"].strip()) for row in rows],
                         [float(row["zero_rate"]) for row in rows])


class CreditCurve:
    """A name's credit curve: the probability that the name has not defaulted."""

    trade_date: dt.date

    def __init__(self, trade_date: dt.date, node_dates: Sequence[dt.date], hazard_rates: Sequence[float]):
        """A hazard rate flat from the end of `trade_date` to the end of the first node date, then from each node
        date to the next (`hazard_rates[i]` up to the end of `node_dates[i]`), and after the last node date at the
        last rate. Rates are continuously compounded, per year of 365 days."""
        if len(node_dates) != len(hazard_rates) or not node_dates:
            raise ValueError("a credit curve needs one hazard rate per node date, and at least one node")
        days = [(date - trade_date).days for date in node_dates]
        if days[0] <= 0 or any(b <= a for a, b in zip(days, days[1:])):
            raise ValueError("credit curve nodes must be increasing dates after the trade date")
        self.trade_date = trade_date
        self.node_dates = list(node_dates)
        self.hazard_rates = [float(rate) for rate in hazard_rates]
        self._days = days
        cumulative, previous, total = [], 0, 0.0
        for day, rate in zip(days, self.hazard_rates):
            total += rate * (day - previous) / DAYS_PER_YEAR
            cumulative.append(total)
            previous = day
        self._cumulative = cumulative           # integrated hazard to the end of each node date

    def _neg_log_survival(self, days: float) -> float:
        """The hazard integrated from the end of the trade date to `days` calendar days after it."""
        if days <= 0:
            return 0.0
        knots, cumulative, rates = self._days, self._cumulative, self.hazard_rates
        i = bisect.bisect_left(knots, days)
        if i == len(knots):
            return cumulative[-1] + rates[-1] * (days - knots[-1]) / DAYS_PER_YEAR
        previous_day = knots[i - 1] if i else 0
        previous_total = cumulative[i - 1] if i else 0.0
        return previous_total + rates[i] * (days - previous_day) / DAYS_PER_YEAR

    def survival(self, date: dt.date) -> float:
        """The probability that the name survives to the end of `date`, seen from the trade date."""
        return math.exp(-self._neg_log_survival((date - self.trade_date).days))

    def __repr__(self) -> str:
        nodes = ", ".join(f"{d}: {h:.6%}" for d, h in zip(self.node_dates, self.hazard_rates))
        return f"CreditCurve(trade_date={self.trade_date}, hazard to {{{nodes}}})"
