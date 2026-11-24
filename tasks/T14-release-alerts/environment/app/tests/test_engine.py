from alertd.engine import Engine
from alertd.state import State

QUIET_OFF = '[alerts]\nquiet_start = "00:00"\nquiet_end = "00:00"\n'


def price(make_event, at="2026-11-03T10:00:00Z", instrument="ORVK", last=103.0, reference=100.0, **extra):
    return make_event("price_move", at=at, instrument=instrument, quoted_at=at, last=last, reference=reference,
                      measure="pct", **extra)


def news(make_event, at="2026-11-03T10:00:00Z", tags=("guidance",), tickers=("KSVH",), **extra):
    return make_event("news", at=at, source="wire", headline="Kesvora cuts guidance", published_at=at,
                      tickers=list(tickers), tags=list(tags), **extra)


def test_a_kind_without_a_rule_is_skipped_with_a_note(defaults, make_event):
    notes = []
    engine = Engine(defaults, State(), note=notes.append)
    assert engine.decide(make_event("fx_fixing", id="f1")) is None
    assert notes == ["line 1 (id f1): no rule for kind 'fx_fixing'; skipped"]


def test_an_alert_that_goes_out_is_recorded(defaults, make_event):
    state = State()
    decision = Engine(defaults, state).decide(price(make_event))
    assert decision.sent and decision.level == "warning" and decision.reasons == ["move"]
    assert decision.message == "WARNING ORVK: price up 3.00% (last 103.00, from 100.00)"
    assert state.count == 1 and "price_move:ORVK" in state.last_alert


def test_a_suppressed_alert_has_its_tag_and_no_message(defaults, make_event):
    state = State()
    state.mute("price_move:ORVK")
    decision = Engine(defaults, state).decide(price(make_event))
    assert decision.as_dict() == {"id": decision.id, "kind": "price_move", "key": "price_move:ORVK", "sent": False,
                                  "level": "warning", "reasons": ["move", "muted"], "message": None}
    assert state.count == 0 and state.last_alert == {}


def test_an_event_not_worth_an_alert(defaults, make_event):
    decision = Engine(defaults, State()).decide(price(make_event, last=100.5))
    assert decision.as_dict()["level"] is None
    assert (decision.sent, decision.reasons, decision.message, decision.key) == (False, [], None, "price_move:ORVK")


def test_an_event_its_rule_cannot_read_is_skipped(defaults, make_event):
    notes = []
    engine = Engine(defaults, State(), note=notes.append)
    assert engine.decide(make_event("price_move", id="p9", instrument="ORVK", last="high")) is None
    assert notes and notes[0].startswith("line 1 (id p9): skipped:")


def test_every_kind_counts_towards_one_cap(make_settings, make_event):
    settings = make_settings(QUIET_OFF + "daily_cap = 2\n")
    engine = Engine(settings, State())
    first = engine.decide(price(make_event, at="2026-11-03T10:00:00Z"))
    second = engine.decide(news(make_event, at="2026-11-03T10:01:00Z"))
    third = engine.decide(price(make_event, at="2026-11-03T10:02:00Z", instrument="BRHW"))
    assert first.sent and second.sent
    assert third.reasons == ["move", "daily_cap"] and not third.sent


def test_a_critical_alert_past_the_cap_still_counts(make_settings, make_event):
    settings = make_settings(QUIET_OFF + "daily_cap = 1\n")
    state = State()
    engine = Engine(settings, state)
    engine.decide(price(make_event, instrument="A1"))
    decision = engine.decide(price(make_event, instrument="A2", last=110.0))
    assert decision.sent and decision.level == "critical"
    assert state.count == 2


def test_the_cooldown_goes_by_key(defaults, make_event):
    engine = Engine(defaults, State())
    engine.decide(price(make_event, at="2026-11-03T10:00:00Z"))
    again = engine.decide(price(make_event, at="2026-11-03T10:10:00Z"))
    other = engine.decide(price(make_event, at="2026-11-03T10:10:00Z", instrument="BRHW"))
    assert again.reasons == ["move", "cooldown"]
    assert other.sent


def test_replay_keeps_the_feed_order_and_leaves_out_skipped_events(defaults, make_event):
    events = [price(make_event, id="a"), make_event("fx_fixing", id="b"), news(make_event, id="c")]
    assert [d.id for d in Engine(defaults, State()).replay(events)] == ["a", "c"]


def test_the_engine_reads_each_kind_its_own_settings(make_settings, make_event):
    settings = make_settings("[price_move]\nthreshold_pct = 5.0\n")
    decision = Engine(settings, State()).decide(price(make_event))
    assert decision.level is None
