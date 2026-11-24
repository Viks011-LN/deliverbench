from datetime import datetime, time, timezone

import pytest

from alertd.timeutil import (clock_of, day_of, format_time, in_window, minutes_between, parse_clock,
                             parse_time)


def test_a_time_with_z_is_utc():
    assert parse_time("2026-11-03T10:15:30Z") == datetime(2026, 11, 3, 10, 15, 30, tzinfo=timezone.utc)


def test_plus_zero_offset_and_missing_seconds_are_accepted():
    assert parse_time("2026-11-03T10:15+00:00") == datetime(2026, 11, 3, 10, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("text", ["2026-11-03T10:15:00", "2026-11-03T10:15:00+01:00", "yesterday", "", None, 5])
def test_anything_but_a_utc_time_is_refused(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_format_time_writes_what_parse_time_reads():
    text = "2026-11-03T07:00:05Z"
    assert format_time(parse_time(text)) == text


def test_minutes_between_is_signed():
    a, b = parse_time("2026-11-03T10:00:00Z"), parse_time("2026-11-03T11:30:30Z")
    assert minutes_between(a, b) == 90.5
    assert minutes_between(b, a) == -90.5


def test_day_of_is_the_utc_day():
    assert day_of(parse_time("2026-11-03T23:59:59Z")) == "2026-11-03"
    assert day_of(parse_time("2026-11-04T00:00:00Z")) == "2026-11-04"


def test_parse_clock():
    assert parse_clock("06:30") == time(6, 30)
    for bad in ("6:30", "24:00", "07:60", "0730", 730):
        with pytest.raises(ValueError):
            parse_clock(bad)


def test_clock_of_keeps_seconds():
    assert clock_of(parse_time("2026-11-03T06:59:30Z")) == time(6, 59, 30)


def test_a_window_within_the_day():
    start, end = time(12, 0), time(13, 0)
    assert in_window(parse_time("2026-11-03T12:00:00Z"), start, end)
    assert in_window(parse_time("2026-11-03T12:59:59Z"), start, end)
    assert not in_window(parse_time("2026-11-03T13:00:00Z"), start, end)


def test_a_window_over_midnight():
    start, end = time(22, 0), time(7, 0)
    assert in_window(parse_time("2026-11-03T23:30:00Z"), start, end)
    assert in_window(parse_time("2026-11-04T06:59:59Z"), start, end)
    assert not in_window(parse_time("2026-11-04T07:00:00Z"), start, end)
    assert not in_window(parse_time("2026-11-03T21:59:59Z"), start, end)


def test_a_window_whose_start_is_its_end_is_empty():
    assert not in_window(parse_time("2026-11-03T05:00:00Z"), time(5, 0), time(5, 0))
