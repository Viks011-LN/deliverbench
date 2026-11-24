"""The rebalancing schedule and the calendar it rests on (bt/portfolio/schedule.py, bt/data/calendar.py)."""
from datetime import date, timedelta

import pytest

from bt.data.calendar import month_key, new_month, new_week, parse_day, year_key
from bt.portfolio.schedule import is_rebalance_day, trades_today


def weekdays_between(first, last):
    days = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return days


MAY = weekdays_between(date(2025, 5, 1), date(2025, 6, 30))


def rebalance_days(dates, frequency):
    return [dates[t] for t in range(1, len(dates)) if is_rebalance_day(dates, t, frequency)]


def test_parse_day_rejects_a_bad_date():
    with pytest.raises(ValueError):
        parse_day("2025-02-30")


def test_keys():
    assert month_key("2025-05-07") == "2025-05"
    assert year_key("2025-05-07") == "2025"


def test_daily_rebalancing_is_every_day():
    assert rebalance_days(MAY, "daily") == MAY[1:]


def test_monthly_rebalancing_is_the_first_trading_day_of_a_month():
    assert rebalance_days(MAY, "monthly") == ["2025-06-02"]


def test_weekly_rebalancing_is_each_monday_in_an_ordinary_spring():
    days = rebalance_days(MAY, "weekly")
    assert all(date.fromisoformat(day).weekday() == 0 for day in days)
    assert days[0] == "2025-05-05" and days[-1] == "2025-06-30"
    assert len(days) == 9


def test_a_holiday_monday_moves_the_weekly_rebalancing_to_tuesday():
    dates = [day for day in MAY if day != "2025-05-26"]
    assert "2025-05-27" in rebalance_days(dates, "weekly")


def test_a_gap_of_more_than_a_week_is_a_new_week():
    assert new_week(date(2025, 5, 23), date(2025, 5, 13))


def test_same_week_is_not_a_new_week():
    assert not new_week(date(2025, 5, 16), date(2025, 5, 12))


def test_a_new_month_after_a_long_gap():
    assert new_month(date(2025, 8, 1), date(2025, 6, 30))
    assert not new_month(date(2025, 6, 30), date(2025, 6, 2))


def test_the_first_day_is_never_a_rebalancing_without_a_warm_up_end():
    assert not trades_today(MAY, 0, 5, "daily")
    assert not trades_today(MAY, 4, 5, "daily")
    assert trades_today(MAY, 5, 5, "monthly")


def test_after_the_warm_up_the_schedule_rules():
    start = 3
    monthly = [MAY[t] for t in range(len(MAY)) if trades_today(MAY, t, start, "monthly")]
    assert monthly == [MAY[3], "2025-06-02"]
    weekly = [MAY[t] for t in range(len(MAY)) if trades_today(MAY, t, start, "weekly")]
    assert weekly[0] == MAY[3] and weekly[1] == "2025-05-12"


@pytest.mark.parametrize("frequency", ["daily", "weekly", "monthly"])
def test_the_schedule_only_looks_at_the_day_and_the_day_before(frequency):
    for t in range(1, len(MAY)):
        assert is_rebalance_day(MAY, t, frequency) == is_rebalance_day(MAY[t - 1:t + 1], 1, frequency)
