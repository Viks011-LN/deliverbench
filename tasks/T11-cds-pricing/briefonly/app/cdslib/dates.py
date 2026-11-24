"""Dates of a standard contract: business days, a trade's dates and the coupon schedule.

The rules are the desk's: docs/desk-conventions.md, "Dates" and "The premium".
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

# The desk's holidays (columns date, name), read from data/ beside the package.
HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "holidays.csv"

# Coupon dates fall on the 20th of these months (docs/desk-conventions.md, "Dates").
COUPON_MONTHS = (3, 6, 9, 12)
COUPON_DAY = 20
# The cash settlement date is this many business days after the trade date.
CASH_SETTLE_LAG = 3

_ONE_DAY = dt.timedelta(days=1)
_holiday_cache: dict[Path, frozenset[dt.date]] = {}


@dataclass(frozen=True)
class TradeDates:
    """The dates a standard contract traded on `trade_date` runs from."""
    trade_date: dt.date
    step_in: dt.date
    cash_settle: dt.date
    accrual_start: dt.date


@dataclass(frozen=True)
class Period:
    """One coupon period: it accrues from accrual_start (included) to accrual_end (excluded) and is paid on
    pay_date; amount is the coupon it pays, in dollars."""
    accrual_start: dt.date
    accrual_end: dt.date
    pay_date: dt.date
    amount: float


def _holidays() -> frozenset[dt.date]:
    """The desk's holidays, read once per file from HOLIDAYS_FILE (looked up at call time)."""
    path = Path(HOLIDAYS_FILE)
    cached = _holiday_cache.get(path)
    if cached is None:
        with open(path, newline="", encoding="utf-8") as handle:
            cached = frozenset(dt.date.fromisoformat(row["date"].strip()) for row in csv.DictReader(handle)
                               if row.get("date", "").strip())
        _holiday_cache[path] = cached
    return cached


def is_business_day(day: dt.date) -> bool:
    """Whether the desk does business on `day`."""
    return day.weekday() < 5 and day not in _holidays()


def next_business_day(day: dt.date) -> dt.date:
    """`day` itself if it is a business day, otherwise the first business day after it (always forward)."""
    while not is_business_day(day):
        day += _ONE_DAY
    return day


def add_business_days(day: dt.date, count: int) -> dt.date:
    """The `count`-th business day after `day`."""
    for _ in range(count):
        day += _ONE_DAY
        while not is_business_day(day):
            day += _ONE_DAY
    return day


def _coupon_date_on_or_before(day: dt.date) -> dt.date:
    """The latest unadjusted coupon date (a 20 Mar/Jun/Sep/Dec) on or before `day`."""
    year, month = day.year, day.month
    while True:
        if month in COUPON_MONTHS:
            candidate = dt.date(year, month, COUPON_DAY)
            if candidate <= day:
                return candidate
        month -= 1
        if month == 0:
            year, month = year - 1, 12


def _next_coupon_date(day: dt.date) -> dt.date:
    """The unadjusted coupon date after the unadjusted coupon date `day` (the 20th of the next coupon month)."""
    year, month = day.year, day.month
    while True:
        month += 1
        if month == 13:
            year, month = year + 1, 1
        if month in COUPON_MONTHS:
            return dt.date(year, month, COUPON_DAY)


def _accrual_start(trade_date: dt.date) -> tuple[dt.date, dt.date]:
    """The latest coupon date on or before `trade_date`, as moved to a business day: (unadjusted, moved)."""
    unadjusted = _coupon_date_on_or_before(trade_date)
    adjusted = next_business_day(unadjusted)
    # Only matters if the trade date is not a business day: the moved date must still not be after it.
    while adjusted > trade_date:
        unadjusted = _coupon_date_on_or_before(unadjusted - _ONE_DAY)
        adjusted = next_business_day(unadjusted)
    return unadjusted, adjusted


def trade_dates(trade_date: dt.date) -> TradeDates:
    """The step-in, cash settlement and accrual start dates of a standard contract traded on `trade_date`."""
    return TradeDates(trade_date=trade_date,
                      step_in=trade_date + _ONE_DAY,
                      cash_settle=add_business_days(trade_date, CASH_SETTLE_LAG),
                      accrual_start=_accrual_start(trade_date)[1])


def accrual_periods(trade_date: dt.date, maturity: dt.date) -> list[tuple[dt.date, dt.date, dt.date]]:
    """(accrual start, accrual end (excluded), pay date) of every coupon period of a standard contract, in order.

    Periods run between coupon dates as moved to business days; the last one runs through the maturity date
    itself (its accrual end is the day after the maturity) and is paid on the maturity date, moved forward to a
    business day if it is not one. The maturity itself is never moved."""
    if maturity <= trade_date:
        raise ValueError(f"maturity {maturity} is not after the trade date {trade_date}")
    unadjusted, start = _accrual_start(trade_date)
    boundaries = [start]
    while True:
        unadjusted = _next_coupon_date(unadjusted)
        if unadjusted >= maturity:
            break
        adjusted = next_business_day(unadjusted)
        if adjusted > boundaries[-1]:
            boundaries.append(adjusted)
    periods = [(boundaries[i], boundaries[i + 1], boundaries[i + 1]) for i in range(len(boundaries) - 1)]
    periods.append((boundaries[-1], maturity + _ONE_DAY, next_business_day(maturity)))
    return periods


def payment_schedule(trade_date: dt.date, maturity: dt.date, coupon_bp: float, notional: float) -> list[Period]:
    """Every coupon period of a standard contract traded on `trade_date` and maturing on `maturity`, from the period
    the trade accrues from to the last one, in order, each with the coupon it pays on `notional` dollars at
    `coupon_bp` basis points a year."""
    rate = coupon_bp / 10_000.0
    return [Period(accrual_start=start, accrual_end=end, pay_date=pay,
                   amount=notional * rate * (end - start).days / 360.0)
            for start, end, pay in accrual_periods(trade_date, maturity)]
