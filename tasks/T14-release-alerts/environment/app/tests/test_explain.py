import io

import pytest

from alertd.cli import main
from alertd.engine import Engine
from alertd.errors import AlertdError
from alertd.explain import explain
from alertd.state import State

AT = "2026-11-03T10:00:00Z"


def price(make_event, id, at=AT, instrument="ORVK", last=41.27, reference=42.60, quoted_at=None):
    return make_event("price_move", id=id, at=at, instrument=instrument, quoted_at=quoted_at or at, last=last,
                      reference=reference, measure="pct")


def test_an_alert_that_goes_out(defaults, make_event):
    lines = explain([price(make_event, "a")], "a", Engine(defaults, State()))
    assert lines[0] == "event a (price_move), seen at 2026-11-03T10:00:00Z"
    assert lines[1] == "rule: warning, reasons move (key price_move:ORVK)"
    assert lines[2] == "  the message would be: WARNING ORVK: price down 3.12% (last 41.27, from 42.60)"
    assert [line.split(":")[0] for line in lines[3:8]] == ["stale", "muted", "quiet_hours", "cooldown", "daily_cap"]
    assert lines[-1] == "decision: sent"


def test_the_feed_before_the_event_counts(defaults, make_event):
    events = [price(make_event, "a"), price(make_event, "b", at="2026-11-03T10:05:00Z")]
    lines = explain(events, "b", Engine(defaults, State()))
    assert "cooldown: applies (last alert 5.0 min before, cooldown 30 min)" in lines
    assert "daily_cap: not looked at" in lines
    assert lines[-1] == "decision: not sent, cooldown"


def test_a_critical_alert_passes_a_mute(defaults, make_event):
    state = State()
    state.mute("price_move:*")
    lines = explain([price(make_event, "a", last=30.0)], "a", Engine(defaults, state))
    assert "muted: passed, the alert is critical (muted by price_move:*)" in lines
    assert lines[-1] == "decision: sent"


def test_stale_figures(defaults, make_event):
    lines = explain([price(make_event, "a", quoted_at="2026-11-03T09:45:00Z")], "a", Engine(defaults, State()))
    assert "stale: applies (figures 15.0 min old, 10 allowed)" in lines
    assert lines[-1] == "decision: not sent, stale"


def test_an_event_not_worth_an_alert_and_an_unknown_kind(defaults, make_event):
    engine = Engine(defaults, State())
    assert explain([price(make_event, "a", last=42.5)], "a", engine)[-1] == "decision: nothing to send"
    assert explain([make_event("fx_fixing", id="x")], "x", engine)[-1].startswith("rule: none for kind")


def test_an_id_not_in_the_feed(defaults, make_event):
    with pytest.raises(AlertdError, match="no event with id"):
        explain([price(make_event, "a")], "zz", Engine(defaults, State()))


def test_the_command(tmp_path, write_lines):
    feed = write_lines("feed.jsonl", [{"id": "a", "kind": "price_move", "at": AT, "instrument": "ORVK",
                                        "quoted_at": AT, "last": 41.27, "reference": 42.60, "measure": "pct"}])
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    config = tmp_path / "alerts.toml"
    config.write_text("", encoding="utf-8")
    out = io.StringIO()
    code = main(["explain", "--feed", str(feed), "--state", str(state), "--id", "a", "--config", str(config)],
                out=out, err=io.StringIO())
    assert code == 0 and out.getvalue().splitlines()[-1] == "decision: sent"
    assert state.read_text(encoding="utf-8") == "{}"
