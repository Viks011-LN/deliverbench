"""Dates of a standard contract: business days, coupon dates, a trade's dates and the coupon schedule.

Every rule here is the desk's (docs/desk-conventions.md, "Dates" and "The premium").
"""
from __future__ import annotations

import csv
import datetime as dt
import functools
from dataclasses import dataclass
from pathlib import Path

HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "holidays.csv"
COUPON_MONTHS = (3, 6, 9, 12)
COUPON_DAY = 20
CASH_SETTLE_BUSINESS_DAYS = 3
DAY_COUNT_BASIS = 360          # the premium accrues Actual/360
ONE_DAY = dt.timedelta(days=1)


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
    pay_date; amount is the coupon it pays, in the notional's currency."""
    accrual_start: dt.date
    accrual_end: dt.date
    pay_date: dt.date
    amount: float


@functools.cache
def holidays() -> frozenset[dt.date]:
    with open(HOLIDAYS_FILE, newline="", encoding="utf-8") as fh:
        return frozenset(dt.date.fromisoformat(row["date"]) for row in csv.DictReader(fh))


def is_business_day(day: dt.date) -> bool:
    return day.weekday() < 5 and day not in holidays()


def following_business_day(day: dt.date) -> dt.date:
    while not is_business_day(day):
        day += ONE_DAY
    return day


def add_business_days(day: dt.date, count: int) -> dt.date:
    while count > 0:
        day += ONE_DAY
        if is_business_day(day):
            count -= 1
    return day


def latest_coupon_date(day: dt.date) -> dt.date:
    """The latest 20 March, June, September or December on or before `day` (as a calendar date)."""
    year, month = day.year, day.month
    while not (month in COUPON_MONTHS and dt.date(year, month, COUPON_DAY) <= day):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return dt.date(year, month, COUPON_DAY)


def trade_dates(trade_date: dt.date) -> TradeDates:
    return TradeDates(trade_date=trade_date, step_in=trade_date + ONE_DAY,
                      cash_settle=add_business_days(trade_date, CASH_SETTLE_BUSINESS_DAYS),
                      accrual_start=following_business_day(latest_coupon_date(trade_date)))


def months_before(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 - months
    return dt.date(index // 12, index % 12 + 1, day.day)


def coupon_dates(accrual_start: dt.date, maturity: dt.date) -> list[dt.date]:
    """The calendar coupon dates after accrual_start, every three months back from the maturity, maturity last."""
    dates = [maturity]
    step = 1
    while True:
        day = months_before(maturity, 3 * step)
        if day <= accrual_start:
            break
        dates.append(day)
        step += 1
    return sorted(dates)


def payment_schedule(trade_date: dt.date, maturity: dt.date, coupon_bp: float, notional: float) -> list[Period]:
    dates = trade_dates(trade_date)
    if maturity <= dates.accrual_start:
        raise ValueError(f"maturity {maturity} is not after the accrual start {dates.accrual_start}")
    calendar = coupon_dates(dates.accrual_start, maturity)
    periods = []
    start = dates.accrual_start
    for i, day in enumerate(calendar):
        last = i == len(calendar) - 1
        pay = following_business_day(day)
        end = day + ONE_DAY if last else pay     # the last period runs through the maturity date itself
        amount = notional * coupon_bp / 10_000 * (end - start).days / DAY_COUNT_BASIS
        periods.append(Period(start, end, pay, amount))
        start = end
    return periods
