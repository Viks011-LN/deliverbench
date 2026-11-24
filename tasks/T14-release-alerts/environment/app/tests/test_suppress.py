from datetime import timedelta

import pytest

from alertd.model import Finding
from alertd.state import State
from alertd.suppress import CRITICAL_PASSES, ORDER, applies, first_suppression
from alertd.timeutil import parse_time as t

ALERTS = {"cooldown_minutes": 30, "daily_cap": 3, "quiet_start": "22:00", "quiet_end": "06:30"}
NOON = t("2026-11-03T12:00:00Z")


def finding(level="warning", key="price_move:ORVK", as_of=NOON, stale_after=timedelta(minutes=10)):
    return Finding(key=key, level=level, reasons=["move"], subject="ORVK", what="price up 3.00%", detail=None,
                   as_of=as_of, stale_after=stale_after)


def old(level="warning"):
    return finding(level, as_of=NOON - timedelta(minutes=11))


def muted_state(key="price_move:ORVK"):
    state = State()
    state.mute(key)
    return state


def capped_state(count=3):
    return State.from_dict({"sent_today": {"day": "2026-11-03", "count": count}})


def cooling_state(minutes_ago=10, key="price_move:ORVK"):
    state = State()
    state.last_alert[key] = NOON - timedelta(minutes=minutes_ago)
    return state


def test_the_order():
    assert ORDER == ("stale", "muted", "quiet_hours", "cooldown", "daily_cap")
    assert CRITICAL_PASSES == {"muted", "quiet_hours", "daily_cap"}


def test_nothing_applies():
    assert first_suppression(finding(), NOON, State(), ALERTS) is None


def test_stale():
    assert first_suppression(old(), NOON, State(), ALERTS) == "stale"
    assert first_suppression(finding(as_of=NOON - timedelta(minutes=10)), NOON, State(), ALERTS) is None


def test_a_kind_that_is_never_stale():
    assert first_suppression(finding(as_of=NOON - timedelta(days=3), stale_after=None), NOON, State(), ALERTS) is None


def test_muted():
    assert first_suppression(finding(), NOON, muted_state(), ALERTS) == "muted"
    assert first_suppression(finding(), NOON, muted_state("price_move:*"), ALERTS) == "muted"
    assert first_suppression(finding(), NOON, muted_state("news:*"), ALERTS) is None


@pytest.mark.parametrize("time, quiet", [("2026-11-03T22:00:00Z", True), ("2026-11-04T06:29:59Z", True),
                                         ("2026-11-04T06:30:00Z", False), ("2026-11-03T21:59:00Z", False)])
def test_quiet_hours(time, quiet):
    at = t(time)
    tag = first_suppression(finding(as_of=at), at, State(), ALERTS)
    assert tag == ("quiet_hours" if quiet else None)


def test_cooldown():
    assert first_suppression(finding(), NOON, cooling_state(10), ALERTS) == "cooldown"
    assert first_suppression(finding(), NOON, cooling_state(30), ALERTS) is None
    assert first_suppression(finding(key="price_move:BRHW"), NOON, cooling_state(10), ALERTS) is None


def test_daily_cap():
    assert first_suppression(finding(), NOON, capped_state(3), ALERTS) == "daily_cap"
    assert first_suppression(finding(), NOON, capped_state(2), ALERTS) is None


def test_the_cap_of_another_day_does_not_count():
    state = State.from_dict({"sent_today": {"day": "2026-11-02", "count": 99}})
    assert first_suppression(finding(), NOON, state, ALERTS) is None


def test_critical_passes_mutes_quiet_hours_and_the_cap():
    late = t("2026-11-03T23:00:00Z")
    assert first_suppression(finding("critical"), NOON, muted_state(), ALERTS) is None
    assert first_suppression(finding("critical", as_of=late), late, State(), ALERTS) is None
    assert first_suppression(finding("critical"), NOON, capped_state(), ALERTS) is None


def test_nothing_passes_stale_or_the_cooldown():
    assert first_suppression(old("critical"), NOON, State(), ALERTS) == "stale"
    assert first_suppression(finding("critical"), NOON, cooling_state(), ALERTS) == "cooldown"


def test_stale_comes_first():
    state = muted_state()
    state.last_alert["price_move:ORVK"] = NOON - timedelta(minutes=5)
    assert first_suppression(old(), NOON, state, ALERTS) == "stale"


def test_muted_comes_before_quiet_hours():
    late = t("2026-11-03T23:00:00Z")
    assert first_suppression(finding(as_of=late), late, muted_state(), ALERTS) == "muted"


def test_quiet_hours_come_before_the_cooldown():
    late = t("2026-11-03T23:00:00Z")
    state = State()
    state.last_alert["price_move:ORVK"] = late - timedelta(minutes=5)
    assert first_suppression(finding(as_of=late), late, state, ALERTS) == "quiet_hours"


def test_the_cooldown_comes_before_the_cap():
    state = capped_state()
    state.last_alert["price_move:ORVK"] = NOON - timedelta(minutes=5)
    assert first_suppression(finding(), NOON, state, ALERTS) == "cooldown"


def test_applies_one_at_a_time():
    assert applies("muted", finding(), NOON, muted_state(), ALERTS)
    assert not applies("muted", finding("critical"), NOON, muted_state(), ALERTS)
    assert applies("cooldown", finding("critical"), NOON, cooling_state(), ALERTS)
