from datetime import timedelta

import pytest

from alertd.errors import EventError
from alertd.rules import limit_usage


def event(make_event, used=10.6, limit_amount=12.0):
    return make_event("limit_usage", desk="rates", limit="VAR", used=used, limit_amount=limit_amount,
                      measured_at="2026-11-03T09:45:00Z")


@pytest.mark.parametrize("used, level", [(8.3, None), (8.5, "info"), (10.5, "warning"), (12.0, "critical")])
def test_levels_by_usage(make_event, defaults, used, level):
    found = limit_usage.evaluate(event(make_event, used=used), defaults.section("limit_usage"))
    assert (found.level if found else None) == level


def test_usage_above_the_limit_is_a_breach(make_event, defaults):
    at_limit = limit_usage.evaluate(event(make_event, used=12.0), defaults.section("limit_usage"))
    above = limit_usage.evaluate(event(make_event, used=12.5), defaults.section("limit_usage"))
    assert at_limit.reasons == ["usage"]
    assert above.reasons == ["usage", "breach"]


def test_the_parts_of_the_message(make_event, defaults):
    found = limit_usage.evaluate(event(make_event, used=12.25, limit_amount=11.75), defaults.section("limit_usage"))
    assert found.subject == "rates VAR"
    assert found.what == "104.3% of limit used"
    assert found.detail == "12.3m of 11.8m"


def test_the_key_and_staleness(make_event, defaults):
    found = limit_usage.evaluate(event(make_event), defaults.section("limit_usage"))
    assert found.key == limit_usage.key(event(make_event)) == "limit_usage:rates:VAR"
    assert found.stale_after == timedelta(minutes=60)


def test_a_limit_of_zero_cannot_be_read(make_event, defaults):
    with pytest.raises(EventError):
        limit_usage.evaluate(event(make_event, limit_amount=0), defaults.section("limit_usage"))
