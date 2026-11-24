"""Business-day helpers.

Weekends are never business days. Holidays are optional and passed in by the
caller; folio ships no holiday calendars because the price files already
skip the days a market was shut, and staleness only needs to be roughly right.
"""

from datetime import date, timedelta
from typing import AbstractSet

NO_HOLIDAYS: AbstractSet[date] = frozenset()


def parse_date(text: str, what: str = "date") -> date:
    """Parse an ISO date (YYYY-MM-DD) with an error message naming ``what``."""
    try:
        return date.fromisoformat(text.strip())
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{what} {text!r} is not a date in YYYY-MM-DD form") from None


def is_business_day(day: date, holidays: AbstractSet[date] = NO_HOLIDAYS) -> bool:
    return day.weekday() < 5 and day not in holidays


def previous_business_day(day: date, holidays: AbstractSet[date] = NO_HOLIDAYS) -> date:
    """The last business day strictly before ``day``."""
    candidate = day - timedelta(days=1)
    while not is_business_day(candidate, holidays):
        candidate -= timedelta(days=1)
    return candidate


def roll_back(day: date, holidays: AbstractSet[date] = NO_HOLIDAYS) -> date:
    """``day`` itself if it is a business day, otherwise the one before it."""
    if is_business_day(day, holidays):
        return day
    return previous_business_day(day, holidays)


def business_days_between(start: date, end: date, holidays: AbstractSet[date] = NO_HOLIDAYS) -> int:
    """Count business days d with start < d <= end (negative if end < start).

    So a Friday price used on the following Monday is 1 business day old.
    """
    if end < start:
        return -business_days_between(end, start, holidays)
    weeks, rest = divmod((end - start).days, 7)
    count = weeks * 5  # every run of seven days holds five weekdays
    # The leftover days have the same weekdays as the first `rest` days after
    # start, because whole weeks do not shift the weekday.
    for offset in range(1, rest + 1):
        if (start + timedelta(days=offset)).weekday() < 5:
            count += 1
    count -= sum(1 for holiday in holidays if start < holiday <= end and holiday.weekday() < 5)
    return count
