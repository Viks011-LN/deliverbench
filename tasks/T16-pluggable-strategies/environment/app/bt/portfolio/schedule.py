"""The rebalancing schedule.

The book is rebalanced on the first day after the warm-up, then on the configured schedule: every day, on the
first trading day of a new week, or on the first trading day of a new month.
"""
from bt.data.calendar import new_month, new_week, parse_day


def is_rebalance_day(dates, t, frequency):
    """Daily: every day. Weekly: the first trading day of a new week. Monthly: the first trading day of a new
    month. (t >= 1: the engine only asks after its warm-up.)"""
    if frequency == "daily":
        return True
    today = parse_day(dates[t])
    before = parse_day(dates[t - 1])
    if frequency == "weekly":
        return new_week(today, before)
    return new_month(today, before)


def trades_today(dates, t, first_day, frequency):
    """True if the engine rebalances on day t: on first_day (the end of the warm-up), then on the schedule."""
    return t >= first_day and (t == first_day or is_rebalance_day(dates, t, frequency))
