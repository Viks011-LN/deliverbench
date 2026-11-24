import pytest

from alertd.errors import StateError
from alertd.outbox import Outbox, read_outbox
from alertd.timeutil import parse_time


def test_append_and_read(tmp_path):
    outbox = Outbox(tmp_path / "outbox.txt")
    outbox.append(parse_time("2026-11-03T10:00:00Z"), "WARNING ORVK: price down 3.12%")
    outbox.append(parse_time("2026-11-03T10:05:00Z"), "INFO prices-eu: back")
    assert outbox.written == 2
    assert read_outbox(tmp_path / "outbox.txt") == [("2026-11-03T10:00:00Z", "WARNING ORVK: price down 3.12%"),
                                                    ("2026-11-03T10:05:00Z", "INFO prices-eu: back")]


def test_an_outbox_that_cannot_be_written(tmp_path):
    with pytest.raises(StateError):
        Outbox(tmp_path / "missing" / "outbox.txt").append(parse_time("2026-11-03T10:00:00Z"), "x")
