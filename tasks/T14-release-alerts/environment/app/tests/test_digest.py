import io
import json

import pytest

from alertd.cli import main
from alertd.digest import held_back_by, read_decisions, render, summarise
from alertd.errors import FeedError


def decision(kind, sent, level, reasons, id="x"):
    return {"id": id, "kind": kind, "key": f"{kind}:x", "sent": sent, "level": level, "reasons": reasons,
            "message": "M" if sent else None}


DECISIONS = [
    decision("price_move", True, "warning", ["move"]),
    decision("price_move", False, "warning", ["move", "cooldown"]),
    decision("price_move", False, None, []),
    decision("news", True, "critical", ["tag", "watchlist"]),
    decision("news", False, "info", ["watchlist", "quiet_hours"]),
    decision("limit_usage", False, "warning", ["usage", "stale"]),
]


def test_held_back_by():
    assert held_back_by(DECISIONS[0]) is None
    assert held_back_by(DECISIONS[1]) == "cooldown"
    assert held_back_by(DECISIONS[2]) is None
    assert held_back_by(DECISIONS[5]) == "stale"


def test_summarise_and_render():
    lines = render(summarise(DECISIONS))
    assert lines == [
        "kind         events  alerts  sent",
        "limit_usage       1       1     0",
        "news              2       2     1",
        "price_move        3       2     1",
        "all               6       5     2",
        "sent by level: info 0, warning 1, critical 1",
        "held back: stale 1, muted 0, quiet_hours 1, cooldown 1, daily_cap 0",
    ]


def test_an_empty_digest():
    assert render(summarise([]))[:2] == ["kind  events  alerts  sent", "all        0       0     0"]


def test_read_decisions_refuses_what_is_not_a_decision(tmp_path):
    path = tmp_path / "decisions.jsonl"
    path.write_text(json.dumps({"id": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(FeedError, match="not a decision"):
        read_decisions(path)
    with pytest.raises(FeedError, match="cannot read"):
        read_decisions(tmp_path / "none.jsonl")


def test_the_command_reads_what_replay_printed(root, tmp_path):
    out = io.StringIO()
    main(["replay", "--feed", str(root / "examples" / "feed-price_move.jsonl"),
          "--state", str(root / "examples" / "state.json"), "--config", str(root / "config" / "alerts.toml")],
         out=out, err=io.StringIO())
    path = tmp_path / "decisions.jsonl"
    path.write_text(out.getvalue(), encoding="utf-8")
    printed = io.StringIO()
    assert main(["digest", str(path)], out=printed, err=io.StringIO()) == 0
    assert printed.getvalue().splitlines()[1].startswith("price_move")
