from datetime import timedelta

import pytest

from alertd.errors import EventError
from alertd.rules import price_move


def event(make_event, measure="pct", last=41.27, reference=42.60, instrument="ORVK"):
    return make_event("price_move", instrument=instrument, quoted_at="2026-11-03T09:59:30Z", last=last,
                      reference=reference, measure=measure)


def settings(defaults):
    return defaults.section("price_move")


def test_a_small_move_is_not_worth_an_alert(make_event, defaults):
    assert price_move.evaluate(event(make_event, last=42.10), settings(defaults)) is None


def test_a_move_past_the_threshold_is_a_warning(make_event, defaults):
    found = price_move.evaluate(event(make_event), settings(defaults))
    assert (found.level, found.reasons) == ("warning", ["move"])


def test_a_move_past_the_critical_multiple(make_event, defaults):
    found = price_move.evaluate(event(make_event, last=40.0), settings(defaults))
    assert found.level == "critical"


def test_a_yield_moves_in_basis_points(make_event, defaults):
    found = price_move.evaluate(event(make_event, measure="bp", last=3.682, reference=3.472,
                                      instrument="QMB10"), settings(defaults))
    assert found.level == "critical"
    assert (found.what, found.detail) == ("yield up 21bp", "last 3.682, from 3.472")


def test_the_parts_of_the_message(make_event, defaults):
    found = price_move.evaluate(event(make_event), settings(defaults))
    assert found.subject == "ORVK"
    assert found.what == "price down 3.12%"
    assert found.detail == "last 41.27, from 42.60"


def test_the_key(make_event):
    assert price_move.key(event(make_event)) == "price_move:ORVK"


def test_staleness_comes_from_the_settings(make_event, make_settings):
    found = price_move.evaluate(event(make_event), make_settings("[price_move]\nstale_after_minutes = 3\n")
                                .section("price_move"))
    assert found.stale_after == timedelta(minutes=3)
    assert found.as_of.isoformat() == "2026-11-03T09:59:30+00:00"


def test_the_threshold_comes_from_the_settings(make_event, make_settings):
    strict = make_settings("[price_move]\nthreshold_pct = 4.0\n").section("price_move")
    assert price_move.evaluate(event(make_event), strict) is None


def test_a_zero_reference_cannot_be_read(make_event, defaults):
    with pytest.raises(EventError):
        price_move.evaluate(event(make_event, reference=0), settings(defaults))


def test_a_measure_alertd_does_not_know(make_event, defaults):
    with pytest.raises(EventError):
        price_move.evaluate(event(make_event, measure="ticks"), settings(defaults))
