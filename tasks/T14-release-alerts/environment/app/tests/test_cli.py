import io
import json
from datetime import datetime, timezone

import pytest

from alertd.cli import main

AT = "2026-11-03T10:00:00Z"


def run(*argv, now=None):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err, now=now)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def files(tmp_path, write_lines):
    config = tmp_path / "alerts.toml"
    config.write_text("[alerts]\ndaily_cap = 10\n", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"muted": {"price_move:BRHW": None}}), encoding="utf-8")
    feed = write_lines("feed.jsonl", [
        {"id": "p1", "kind": "price_move", "at": AT, "instrument": "ORVK", "quoted_at": AT, "last": 41.27,
         "reference": 42.60, "measure": "pct"},
        {"id": "x1", "kind": "fx_fixing", "at": AT, "pair": "VDQ"},
        {"id": "p2", "kind": "price_move", "at": AT, "instrument": "BRHW", "quoted_at": AT, "last": 19.5,
         "reference": 19.0, "measure": "pct"},
    ])
    return {"config": str(config), "state": str(state), "feed": str(feed), "dir": tmp_path}


def replay(files):
    return run("replay", "--feed", files["feed"], "--state", files["state"], "--config", files["config"])


def test_replay_prints_one_json_line_per_decision(files):
    code, out, err = replay(files)
    assert code == 0
    lines = [json.loads(line) for line in out.splitlines()]
    assert [line["id"] for line in lines] == ["p1", "p2"]
    assert list(lines[0]) == ["id", "kind", "key", "sent", "level", "reasons", "message"]
    assert lines[0]["message"] == "WARNING ORVK: price down 3.12% (last 41.27, from 42.60)"
    assert lines[1]["reasons"] == ["move", "muted"] and lines[1]["message"] is None


def test_replay_notes_a_kind_it_has_no_rule_for(files):
    _, _, err = replay(files)
    assert "alertd: note: line 2 (id x1): no rule for kind 'fx_fixing'; skipped" in err


def test_replay_never_writes_the_state(files):
    before = open(files["state"], encoding="utf-8").read()
    replay(files)
    replay(files)
    assert open(files["state"], encoding="utf-8").read() == before


def test_run_sends_to_the_outbox_and_saves_the_state(files):
    outbox = files["dir"] / "outbox.txt"
    code, out, err = run("run", "--feed", files["feed"], "--state", files["state"], "--outbox", str(outbox),
                         "--config", files["config"])
    assert code == 0
    assert outbox.read_text(encoding="utf-8") == f"{AT}\tWARNING ORVK: price down 3.12% (last 41.27, from 42.60)\n"
    saved = json.loads(open(files["state"], encoding="utf-8").read())
    assert saved["sent_today"] == {"day": "2026-11-03", "count": 1}
    assert saved["last_alert"] == {"price_move:ORVK": AT}
    assert "1 alert(s) sent" in err


def test_a_bad_config_stops_with_status_2(files):
    with open(files["config"], "w", encoding="utf-8") as fh:
        fh.write("[alerts]\ndaily_limit = 3\n")
    code, out, err = replay(files)
    assert code == 2 and out == ""
    assert err.startswith("alertd: error:") and "daily_limit" in err


def test_a_missing_feed_stops_with_status_2(files):
    code, _, err = run("replay", "--feed", "nowhere.jsonl", "--state", files["state"], "--config", files["config"])
    assert code == 2 and "cannot read the feed" in err


def test_check_config(files, root):
    code, out, _ = run("check-config", "--config", str(root / "config" / "alerts.toml"))
    assert code == 0 and ": ok (" in out


def test_settings_says_where_each_value_comes_from(files):
    code, out, _ = run("settings", "--config", files["config"])
    assert code == 0
    assert f"alerts.daily_cap = 10  # {files['config']}" in out.splitlines()
    assert "alerts.cooldown_minutes = 30  # default" in out.splitlines()


def test_mute_for_a_while_and_unmute(files):
    now = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    code, out, _ = run("mute", "news:wire:*", "--for", "90", "--state", files["state"], now=now)
    assert code == 0 and out.strip() == "muted news:wire:* until 2026-11-03T11:30:00Z"
    assert json.loads(open(files["state"], encoding="utf-8").read())["muted"]["news:wire:*"] == "2026-11-03T11:30:00Z"
    code, out, _ = run("unmute", "news:wire:*", "--state", files["state"])
    assert out.strip() == "unmuted news:wire:*"
    code, out, _ = run("unmute", "news:wire:*", "--state", files["state"])
    assert out.strip() == "news:wire:* was not muted"


def test_show_state(files):
    code, out, _ = run("show-state", "--state", files["state"])
    assert code == 0
    assert out.splitlines() == ["muted: 1", "  price_move:BRHW until unmuted", "last alerts: 0", "sent on -: 0"]
