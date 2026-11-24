"""Calendar tests used by the rebalancing schedule (bt/portfolio/schedule.py).

Dates travel through the program as "YYYY-MM-DD" strings; these helpers parse them only where a calendar
question is asked.
"""
import datetime


def parse_day(text):
    """A "YYYY-MM-DD" string as a date."""
    return datetime.date.fromisoformat(text)


def new_month(today, before):
    """True if `today` is in another month than `before` (the trading day before it)."""
    return today.month != before.month


def new_week(today, before):
    """True if `today` starts a new week: its ISO week number differs from the day before's, or the calendar
    year does (in case of a long gap between the two days)."""
    return today.isocalendar()[1] != before.isocalendar()[1] or today.year != before.year


def month_key(day):
    """"YYYY-MM" of a "YYYY-MM-DD" string."""
    return day[:7]


def year_key(day):
    """"YYYY" of a "YYYY-MM-DD" string."""
    return day[:4]
