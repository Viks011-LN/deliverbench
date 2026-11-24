import io
import json

import pytest

from alertd import history
from alertd.cli import main
from alertd.errors import StateError
from alertd.model import Decision
from alertd.timeutil import parse_time

AT = "2026-11-03T10:00:00Z"


def record(at, key, sent, level, reasons):
    return {"at": at, "id": "x", "kind": key.split(":")[0], "key": key, "sent": sent, "level": level,
            "reasons": reasons, "message": None}


RECORDS = [
    record("2026-11-03T09:00:00Z", "price_move:ORVK", True, "warning", ["move"]),
    record("2026-11-03T09:30:00Z", "news:wire:KSVH", False, "warning", ["tag", "muted"]),
    record("2026-11-03T10:00:00Z", "news:dowline:ORVK", False, None, []),
]


def test_append_and_read(tmp_path):
    path = tmp_path / "history.jsonl"
    history.append(path, parse_time(AT), Decision("p1", "price_move", "price_move:ORVK", True, "warning", ["move"], "M"))
    assert history.read(path) == [{"at": AT, "id": "p1", "kind": "price_move", "key": "price_move:ORVK",
                                   "sent": True, "level": "warning", "reasons": ["move"], "message": "M"}]


def test_a_history_that_is_not_one(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text('{"id": "x"}\n', encoding="utf-8")
    with pytest.raises(StateError, match="not a history record"):
        history.read(path)


def test_select():
    assert len(history.select(RECORDS)) == 3
    assert [r["key"] for r in history.select(RECORDS, key="news:*")] == ["news:wire:KSVH", "news:dowline:ORVK"]
    assert len(history.select(RECORDS, since=parse_time("2026-11-03T09:30:00Z"))) == 2
    assert [r["key"] for r in history.select(RECORDS, sent_only=True)] == ["price_move:ORVK"]


def test_line():
    assert [history.line(r) for r in RECORDS] == [
        "2026-11-03T09:00:00Z  price_move:ORVK  sent warning",
        "2026-11-03T09:30:00Z  news:wire:KSVH  held warning (muted)",
        "2026-11-03T10:00:00Z  news:dowline:ORVK  no alert",
    ]


def test_run_writes_the_history(tmp_path, write_lines):
    feed = write_lines("feed.jsonl", [{"id": "s1", "kind": "stale_feed", "at": AT, "feed": "prices-eu",
                                        "last_update": "2026-11-03T09:30:00Z"}])
    state, config = tmp_path / "state.json", tmp_path / "alerts.toml"
    state.write_text("{}", encoding="utf-8")
    config.write_text("", encoding="utf-8")
    path = tmp_path / "history.jsonl"
    code = main(["run", "--feed", str(feed), "--state", str(state), "--outbox", str(tmp_path / "outbox.txt"),
                 "--history", str(path), "--config", str(config)], out=io.StringIO(), err=io.StringIO())
    assert code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["key"] == "stale_feed:prices-eu"
    out = io.StringIO()
    assert main(["history", "--history", str(path), "--sent"], out=out, err=io.StringIO()) == 0
    assert out.getvalue() == f"{AT}  stale_feed:prices-eu  sent warning\n"
    assert main(["history", "--history", str(path), "--since", "yesterday"], out=io.StringIO(),
                err=io.StringIO()) == 2
