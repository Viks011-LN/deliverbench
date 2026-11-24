"""Times in alertd.

Every time alertd reads or writes is UTC, written as 2026-11-02T10:00:00Z. Seconds may be left out, and +00:00 is
accepted in place of Z; any other offset is refused, so that no two parts of the desk disagree about what a time
means. Times of day in the settings are written HH:MM, also in UTC."""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone

_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_EXAMPLE = "2026-11-02T10:00:00Z"


def parse_time(text: object, what: str = "time") -> datetime:
    """The UTC time ``text`` stands for; ValueError, naming ``what``, if it is not one."""
    if not isinstance(text, str):
        raise ValueError(f"{what} must be a time written as {_EXAMPLE}, got {text!r}")
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{what} must be a time written as {_EXAMPLE}, got {text!r}") from None
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{what} must be in UTC (written with a final Z), got {text!r}")
    return value.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    """A time as alertd writes it: 2026-11-02T10:00:00Z."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes_between(earlier: datetime, later: datetime) -> float:
    """Minutes from ``earlier`` to ``later``; negative when ``later`` comes first."""
    return (later - earlier).total_seconds() / 60


def day_of(value: datetime) -> str:
    """The UTC day of a time, as 2026-11-02: the day the daily cap counts in."""
    return value.astimezone(timezone.utc).date().isoformat()


def parse_clock(text: object, what: str = "time of day") -> time:
    """A time of day written HH:MM (00:00 to 23:59)."""
    if not isinstance(text, str) or not _CLOCK.match(text):
        raise ValueError(f"{what} must be written HH:MM (00:00 to 23:59), got {text!r}")
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def clock_of(value: datetime) -> time:
    """The UTC time of day of a time, seconds included."""
    return value.astimezone(timezone.utc).time().replace(tzinfo=None)


def in_window(value: datetime, start: time, end: time) -> bool:
    """Whether the time of day of ``value`` falls from ``start`` up to, not including, ``end``.

    A window whose start is later than its end runs over midnight (22:00 to 07:00 covers 23:30 and 06:59:59).
    A window whose start equals its end is empty."""
    now = clock_of(value)
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end
