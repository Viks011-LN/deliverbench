import pytest

from alertd.rules import stale_feed


def event(make_event, last_update="2026-11-03T09:37:00Z", at="2026-11-03T10:00:00Z"):
    return make_event("stale_feed", at=at, feed="prices-eu", last_update=last_update)


@pytest.mark.parametrize("last_update, level", [("2026-11-03T09:50:00Z", None), ("2026-11-03T09:45:00Z", "warning"),
                                                ("2026-11-03T09:15:00Z", "critical")])
def test_levels_by_silence(make_event, defaults, last_update, level):
    found = stale_feed.evaluate(event(make_event, last_update), defaults.section("stale_feed"))
    assert (found.level if found else None) == level


def test_the_parts_of_the_message(make_event, defaults):
    found = stale_feed.evaluate(event(make_event), defaults.section("stale_feed"))
    assert (found.subject, found.what, found.detail) == ("prices-eu", "no update for 23 min", "last at 09:37 UTC")
    assert found.reasons == ["silent"]


def test_never_stale(make_event, defaults):
    found = stale_feed.evaluate(event(make_event), defaults.section("stale_feed"))
    assert found.stale_after is None
    assert found.as_of == event(make_event).at


def test_the_key(make_event):
    assert stale_feed.key(event(make_event)) == "stale_feed:prices-eu"
