import json

import pytest

from alertd.errors import EventError, FeedError
from alertd.feed import parse_line, parse_lines, read_feed


def line(**fields):
    return json.dumps({"id": "e1", "kind": "news", "at": "2026-11-03T10:00:00Z", **fields})


def test_an_event_keeps_its_fields():
    event = parse_line(line(headline="hello", tickers=["ORVK"]), 3)
    assert (event.id, event.kind, event.line) == ("e1", "news", 3)
    assert event.fields["headline"] == "hello"
    assert event.where() == "line 3 (id e1)"


@pytest.mark.parametrize("text", ["not json", "[1, 2]", '"text"'])
def test_a_line_that_is_not_an_object_stops_the_feed(text):
    with pytest.raises(FeedError):
        parse_line(text, 1)


@pytest.mark.parametrize("missing", ["id", "kind", "at"])
def test_id_kind_and_at_are_required(missing):
    data = {"id": "e1", "kind": "news", "at": "2026-11-03T10:00:00Z"}
    del data[missing]
    with pytest.raises(FeedError, match=missing):
        parse_line(json.dumps(data), 1)


def test_at_must_be_a_utc_time():
    with pytest.raises(FeedError, match="UTC"):
        parse_line(line(at="2026-11-03T10:00:00+02:00"), 1)


def test_blank_lines_are_skipped_and_ids_are_unique():
    events = list(parse_lines([line(id="a"), "", "   ", line(id="b")]))
    assert [e.id for e in events] == ["a", "b"]
    assert [e.line for e in events] == [1, 4]
    with pytest.raises(FeedError, match="twice"):
        list(parse_lines([line(id="a"), line(id="a")]))


def test_read_feed_reports_a_missing_file(tmp_path):
    with pytest.raises(FeedError, match="cannot read"):
        read_feed(tmp_path / "nothing.jsonl")


def test_text_and_number_helpers(make_event):
    event = make_event(kind="price_move", instrument="ORVK", last=41.27, reference=42, flag=True)
    assert event.text("instrument") == "ORVK"
    assert event.number("last") == 41.27
    assert event.number("reference") == 42.0
    for name in ("flag", "instrument", "absent"):
        with pytest.raises(EventError, match=name):
            event.number(name)
    with pytest.raises(EventError):
        event.text("last")


def test_optional_number_is_none_when_absent_or_null(make_event):
    event = make_event(kind="x", given=1.5, nothing=None)
    assert event.optional_number("given") == 1.5
    assert event.optional_number("nothing") is None
    assert event.optional_number("absent") is None
    assert not event.has("nothing") and event.has("given")


def test_time_choice_and_strings(make_event):
    event = make_event(kind="x", when="2026-11-03T09:00:00Z", measure="bp", tags=["a", "b"], bad=["a", 1])
    assert event.time("when").hour == 9
    assert event.choice("measure", ("pct", "bp")) == "bp"
    assert event.strings("tags") == ["a", "b"]
    assert event.strings("absent") == []
    with pytest.raises(EventError):
        event.choice("measure", ("pct",))
    with pytest.raises(EventError):
        event.strings("bad")
    with pytest.raises(EventError):
        event.time("measure")
