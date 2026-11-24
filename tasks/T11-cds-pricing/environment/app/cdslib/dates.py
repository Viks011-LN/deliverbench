"""Dates of a standard contract: business days, a trade's dates and the coupon schedule.

The rules are the desk's: docs/desk-conventions.md, "Dates" and "The premium".
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

# The desk's holidays (columns date, name), read from data/ beside the package.
HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "holidays.csv"


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


def is_business_day(day: dt.date) -> bool:
    """Whether the desk does business on `day`."""
    raise NotImplementedError


def trade_dates(trade_date: dt.date) -> TradeDates:
    """The step-in, cash settlement and accrual start dates of a standard contract traded on `trade_date`."""
    raise NotImplementedError


def payment_schedule(trade_date: dt.date, maturity: dt.date, coupon_bp: float, notional: float) -> list[Period]:
    """Every coupon period of a standard contract traded on `trade_date` and maturing on `maturity`, from the period
    the trade accrues from to the last one, in order, each with the coupon it pays on `notional` dollars at
    `coupon_bp` basis points a year."""
    raise NotImplementedError
