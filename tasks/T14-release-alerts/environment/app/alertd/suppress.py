"""The shared suppressions.

Every alert of every kind passes through them once its rule has found it worth an alert (engine.py). They are
checked in this order, and the first that applies stops the alert: its tag is added after the alert's reasons, the
alert is not sent, and no later suppression is looked at.

    stale        the figures are older than the kind allows: more than Finding.stale_after (the kind's
                 stale_after_minutes setting) from Finding.as_of to the time alertd sees the event
    muted        the alert's key is muted in the state, by its own key or by a prefix ending in *, and the mute has
                 not run out (state.py)
    quiet_hours  the event comes in from alerts.quiet_start up to, not including, alerts.quiet_end (UTC)
    cooldown     an alert with the same key was sent less than alerts.cooldown_minutes before
    daily_cap    alerts.daily_cap alerts have already been sent on the event's day (UTC)

A critical alert passes mutes, quiet hours and the daily cap; nothing passes stale or the cooldown. Every alert sent
counts towards the daily cap, whatever its kind and level, and starts its key's cooldown (State.record_sent)."""
from __future__ import annotations

from datetime import datetime

from alertd.levels import is_critical
from alertd.model import Finding
from alertd.state import State
from alertd.timeutil import day_of, in_window, minutes_between, parse_clock

ORDER = ("stale", "muted", "quiet_hours", "cooldown", "daily_cap")
CRITICAL_PASSES = frozenset({"muted", "quiet_hours", "daily_cap"})


def stale(finding: Finding, at: datetime, state: State, alerts: dict) -> bool:
    if finding.stale_after is None:
        return False
    return at - finding.as_of > finding.stale_after


def muted(finding: Finding, at: datetime, state: State, alerts: dict) -> bool:
    return state.is_muted(finding.key, at)


def quiet_hours(finding: Finding, at: datetime, state: State, alerts: dict) -> bool:
    return in_window(at, parse_clock(alerts["quiet_start"]), parse_clock(alerts["quiet_end"]))


def cooldown(finding: Finding, at: datetime, state: State, alerts: dict) -> bool:
    last = state.last_alert_for(finding.key)
    return last is not None and minutes_between(last, at) < alerts["cooldown_minutes"]


def daily_cap(finding: Finding, at: datetime, state: State, alerts: dict) -> bool:
    return state.sent_on(day_of(at)) >= alerts["daily_cap"]


CHECKS = {"stale": stale, "muted": muted, "quiet_hours": quiet_hours, "cooldown": cooldown, "daily_cap": daily_cap}


def applies(tag: str, finding: Finding, at: datetime, state: State, alerts: dict) -> bool:
    """Whether one suppression stops this alert (critical's exceptions included)."""
    if tag in CRITICAL_PASSES and is_critical(finding.level):
        return False
    return CHECKS[tag](finding, at, state, alerts)


def first_suppression(finding: Finding, at: datetime, state: State, alerts: dict) -> str | None:
    """The tag of the first suppression, in ORDER, that stops the alert; None if it goes out."""
    for tag in ORDER:
        if applies(tag, finding, at, state, alerts):
            return tag
    return None
