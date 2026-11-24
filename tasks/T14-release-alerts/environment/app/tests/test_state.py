import json

import pytest

from alertd.errors import StateError
from alertd.state import State
from alertd.timeutil import parse_time as t


def test_an_empty_object_is_an_empty_state():
    state = State.from_dict({})
    assert state.muted == {} and state.last_alert == {} and state.count == 0


def test_save_and_load_round_trip(tmp_path):
    state = State()
    state.mute("news:wire:*")
    state.mute("price_move:ORVK", t("2026-11-04T00:00:00Z"))
    state.record_sent("limit_usage:rates:VAR", t("2026-11-03T09:12:00Z"))
    path = tmp_path / "state.json"
    state.save(path)
    again = State.load(path)
    assert again.to_dict() == state.to_dict()
    assert json.loads(path.read_text())["sent_today"] == {"day": "2026-11-03", "count": 1}


def test_a_mute_by_its_key(empty_state):
    empty_state.mute("price_move:ORVK")
    assert empty_state.is_muted("price_move:ORVK", t("2026-11-03T10:00:00Z"))
    assert not empty_state.is_muted("price_move:ORVKX", t("2026-11-03T10:00:00Z"))
    assert not empty_state.is_muted("price_move:BRHW", t("2026-11-03T10:00:00Z"))


def test_a_mute_by_a_prefix(empty_state):
    empty_state.mute("news:wire:*")
    assert empty_state.mute_for("news:wire:KSVH", t("2026-11-03T10:00:00Z")) == "news:wire:*"
    assert empty_state.is_muted("news:wire:-", t("2026-11-03T10:00:00Z"))
    assert not empty_state.is_muted("news:dowline:KSVH", t("2026-11-03T10:00:00Z"))


def test_a_mute_runs_out(empty_state):
    empty_state.mute("price_move:ORVK", t("2026-11-03T12:00:00Z"))
    assert empty_state.is_muted("price_move:ORVK", t("2026-11-03T11:59:59Z"))
    assert not empty_state.is_muted("price_move:ORVK", t("2026-11-03T12:00:00Z"))


def test_unmute(empty_state):
    empty_state.mute("price_move:ORVK")
    assert empty_state.unmute("price_move:ORVK")
    assert not empty_state.unmute("price_move:ORVK")
    assert not empty_state.is_muted("price_move:ORVK", t("2026-11-03T10:00:00Z"))


def test_record_sent_counts_and_starts_the_cooldown(empty_state):
    empty_state.record_sent("a:1", t("2026-11-03T10:00:00Z"))
    empty_state.record_sent("b:2", t("2026-11-03T10:05:00Z"))
    assert empty_state.sent_on("2026-11-03") == 2
    assert empty_state.last_alert_for("b:2") == t("2026-11-03T10:05:00Z")
    assert empty_state.last_alert_for("c:3") is None


def test_the_count_starts_again_on_a_new_day():
    state = State.from_dict({"sent_today": {"day": "2026-11-03", "count": 20}})
    assert state.sent_on("2026-11-03") == 20
    assert state.sent_on("2026-11-04") == 0
    state.record_sent("a:1", t("2026-11-04T00:10:00Z"))
    assert (state.day, state.count) == ("2026-11-04", 1)


@pytest.mark.parametrize("data", [
    [],
    {"muted": {"a": "tomorrow"}},
    {"last_alert": {"a": None}},
    {"sent_today": {"day": "2026-11-03", "count": -1}},
    {"sent_today": {"day": "03/11/2026", "count": 1}},
    {"mutes": {}},
])
def test_a_bad_state_is_refused(data):
    with pytest.raises(StateError):
        State.from_dict(data)


def test_a_state_file_that_is_not_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError, match="not JSON"):
        State.load(path)


def test_an_empty_state_file_is_an_empty_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("", encoding="utf-8")
    assert State.load(path).to_dict() == State().to_dict()
