"""Release alerts (docs/desk/release-alerts.md): the rule, its settings, and the shared suppressions on its alerts."""
import io
import json
from datetime import timedelta

import pytest

from alertd import registry
from alertd.cli import main
from alertd.engine import Engine
from alertd.errors import ConfigError, EventError
from alertd.feed import parse_line
from alertd.rules import release
from alertd.state import State

QUIET_OFF = '[alerts]\nquiet_start = "00:00"\nquiet_end = "00:00"\n'

# The six worked examples on the desk's page: each event's id and the line alertd prints for it.
WORKED_EXAMPLES = {
    "r01": '{"id": "r01", "kind": "release", "key": "release:VD:CPI", "sent": true, "level": "warning", "reasons": '
           '["surprise"], "message": "WARNING VD CPI: actual 0.46% vs consensus 0.22% (surprise +0.24%)"}',
    "r03": '{"id": "r03", "kind": "release", "key": "release:XR:TRADE_BALANCE", "sent": true, "level": "info", '
           '"reasons": ["revision"], "message": "INFO XR TRADE_BALANCE: actual -14.6bn, previous revised from -12.4bn '
           'to -15.8bn (revision -3.4bn)"}',
    "r04": '{"id": "r04", "kind": "release", "key": "release:VD:GDP", "sent": true, "level": "warning", "reasons": '
           '["surprise", "revision"], "message": "WARNING VD GDP: actual 0.31% vs consensus 0.45%, previous revised '
           'from 0.20% to 0.34% (surprise -0.14%, revision +0.14%)"}',
    "r06": '{"id": "r06", "kind": "release", "key": "release:QM:PAYROLLS", "sent": true, "level": "info", "reasons": '
           '["revision"], "message": "INFO QM PAYROLLS: actual 212k, previous revised from 175k to 198k (revision '
           '+23k)"}',
    "r08": '{"id": "r08", "kind": "release", "key": "release:QM:HOUSING_STARTS", "sent": true, "level": "critical", '
           '"reasons": ["surprise"], "message": "CRITICAL QM HOUSING_STARTS: actual 1,212k vs consensus 1,305k '
           '(surprise -93k)"}',
    "r10": '{"id": "r10", "kind": "release", "key": "release:XR:BUDGET_BALANCE", "sent": true, "level": "critical", '
           '"reasons": ["surprise", "revision"], "message": "CRITICAL XR BUDGET_BALANCE: actual 8.4bn vs consensus '
           '1.7bn, previous revised from 3.5bn to 1.2bn (surprise +6.7bn, revision -2.3bn)"}',
}


def event(make_event, at="2026-11-03T10:00:05Z", country="VD", code="CPI", importance="high", unit="pct",
          actual=0.46, consensus=0.22, previous=0.31, revised=None, released_at="2026-11-03T10:00:00Z", **extra):
    return make_event("release", at=at, country=country, release=code, released_at=released_at,
                      importance=importance, unit=unit, actual=actual, consensus=consensus, previous=previous,
                      revised=revised, **extra)


def evaluate(make_event, settings, **fields):
    return release.evaluate(event(make_event, **fields), settings.section("release"))


def replay(root, *extra):
    out, err = io.StringIO(), io.StringIO()
    code = main(["replay", "--feed", str(root / "examples" / "feed-release.jsonl"),
                 "--state", str(root / "examples" / "state.json"), *extra], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


# ----- the desk's page and the examples -------------------------------------------------------------------------

def test_the_kind_is_registered():
    assert registry.rule_for("release") is release
    assert "release" in registry.kinds()


def test_the_worked_examples(root, tmp_path):
    # The page's examples use the default thresholds.
    defaults_only = tmp_path / "empty.toml"
    defaults_only.write_text("", encoding="utf-8")
    code, out, err = replay(root, "--config", str(defaults_only))
    assert code == 0 and err == ""
    printed = {json.loads(line)["id"]: line for line in out.splitlines()}
    for event_id, line in WORKED_EXAMPLES.items():
        assert printed[event_id] == line, event_id


def test_every_example_release_gets_a_decision(root):
    code, out, err = replay(root, "--config", str(root / "config" / "alerts.toml"))
    assert code == 0 and err == ""
    feed = (root / "examples" / "feed-release.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in out.splitlines()] == [json.loads(line)["id"] for line in feed]


def test_the_example_decisions(root):
    code, out, _ = replay(root, "--config", str(root / "config" / "alerts.toml"))
    assert code == 0
    assert out == (root / "examples" / "decisions-release.jsonl").read_text(encoding="utf-8")


def test_the_example_feed_can_be_checked(root):
    out = io.StringIO()
    code = main(["check-feed", "--feed", str(root / "examples" / "feed-release.jsonl"),
                 "--config", str(root / "config" / "alerts.toml")], out=out, err=io.StringIO())
    assert code == 0, out.getvalue()
    assert out.getvalue().splitlines()[0] == "12 events: 12 can be decided, 0 cannot, 0 of kinds with no rule"


# ----- surprise --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("actual, level", [
    (0.31, None),         # +0.09, below the threshold of 0.10
    (0.32, "info"),       # +0.10, the threshold itself
    (0.41, "info"),       # +0.19
    (0.42, "warning"),    # +0.20, twice the threshold
    (0.51, "warning"),    # +0.29
    (0.52, "critical"),   # +0.30, three times the threshold
    (0.12, "info"),       # -0.10: the size of the surprise counts, not its sign
    (-0.08, "critical"),  # -0.30
])
def test_the_level_of_a_surprise(make_event, defaults, actual, level):
    found = evaluate(make_event, defaults, actual=actual, consensus=0.22)
    assert (found.level if found else None) == level
    if found:
        assert found.reasons == ["surprise"]


@pytest.mark.parametrize("actual, consensus, level", [
    (0.3, 0.2, "info"),       # 0.1 exactly, though 0.3 - 0.2 is 0.09999999999999998 in floats
    (0.6, 0.4, "warning"),    # 0.2, twice the threshold
    (0.7, 0.4, "critical"),   # 0.3, three times, though 0.7 - 0.4 is 0.29999999999999993 in floats
    (0.6, 0.3, "critical"),   # 0.3, though 0.1 * 3 is 0.30000000000000004 in floats
])
def test_a_surprise_equal_to_a_multiple_of_the_threshold_reaches_it(make_event, defaults, actual, consensus, level):
    assert evaluate(make_event, defaults, actual=actual, consensus=consensus).level == level


@pytest.mark.parametrize("importance, unit, small, enough", [
    ("high", "pct", 0.09, 0.10), ("high", "k", 14, 15), ("high", "bn", 0.9, 1.0),
    ("medium", "pct", 0.19, 0.20), ("medium", "k", 29, 30), ("medium", "bn", 1.9, 2.0),
    ("low", "pct", 0.29, 0.30), ("low", "k", 49, 50), ("low", "bn", 2.9, 3.0),
])
def test_the_default_threshold_for_each_importance_and_unit(make_event, defaults, importance, unit, small, enough):
    assert evaluate(make_event, defaults, importance=importance, unit=unit, actual=small, consensus=0) is None
    assert evaluate(make_event, defaults, importance=importance, unit=unit, actual=enough, consensus=0).level == "info"


# ----- revision --------------------------------------------------------------------------------------------------

def test_a_revision_alone_is_info(make_event, defaults):
    found = evaluate(make_event, defaults, actual=0.25, consensus=0.22, previous=0.31, revised=0.18)
    assert (found.level, found.reasons) == ("info", ["revision"])


def test_a_revision_raises_the_level_one_step(make_event, defaults):
    assert evaluate(make_event, defaults, actual=0.33, previous=0.31, revised=0.41).level == "warning"
    assert evaluate(make_event, defaults, actual=0.46, previous=0.31, revised=0.21).level == "critical"


def test_critical_stays_critical(make_event, defaults):
    found = evaluate(make_event, defaults, actual=0.60, previous=0.31, revised=0.41)
    assert (found.level, found.reasons) == ("critical", ["surprise", "revision"])


def test_a_smaller_revision_changes_nothing(make_event, defaults):
    found = evaluate(make_event, defaults, actual=0.46, previous=0.31, revised=0.39)
    assert (found.level, found.reasons) == ("warning", ["surprise"])
    assert found.what == "actual 0.46% vs consensus 0.22%"
    assert found.detail == "surprise +0.24%"


def test_a_previous_figure_revised_to_itself_is_no_revision(make_event, defaults):
    assert evaluate(make_event, defaults, actual=0.22, previous=0.25, revised=0.25) is None


# ----- no consensus, neither --------------------------------------------------------------------------------------

def test_no_consensus_no_surprise(make_event, defaults):
    assert evaluate(make_event, defaults, actual=9.0, consensus=None) is None
    found = evaluate(make_event, defaults, actual=9.0, consensus=None, previous=0.31, revised=0.45)
    assert (found.level, found.reasons) == ("info", ["revision"])
    assert found.what == "actual 9.00%, previous revised from 0.31% to 0.45%"


def test_an_absent_consensus_or_revision_is_none(defaults):
    data = {"id": "x", "kind": "release", "at": "2026-11-03T10:00:05Z", "country": "VD", "release": "CPI",
            "released_at": "2026-11-03T10:00:00Z", "importance": "high", "unit": "pct", "actual": 0.46,
            "previous": 0.31}
    assert release.evaluate(parse_line(json.dumps(data)), defaults.section("release")) is None


def test_neither_is_not_worth_an_alert(make_event, defaults):
    assert evaluate(make_event, defaults, actual=0.25, consensus=0.22, previous=0.31, revised=0.33) is None


# ----- the parts of the message, the key, staleness ---------------------------------------------------------------

def test_the_parts_of_the_message(make_event, defaults):
    found = evaluate(make_event, defaults, code="HOUSING_STARTS", country="QM", importance="medium", unit="k",
                     actual=1212, consensus=1305, previous=1288, revised=1250)
    assert found.subject == "QM HOUSING_STARTS"
    assert found.what == "actual 1,212k vs consensus 1,305k, previous revised from 1,288k to 1,250k"
    assert found.detail == "surprise -93k, revision -38k"


def test_the_key(make_event):
    assert release.key(event(make_event, country="XR", code="TRADE_BALANCE")) == "release:XR:TRADE_BALANCE"


def test_staleness_is_measured_from_the_release(make_event, make_settings):
    found = evaluate(make_event, make_settings("[release]\nstale_after_minutes = 5\n"))
    assert found.stale_after == timedelta(minutes=5)
    assert found.as_of.isoformat() == "2026-11-03T10:00:00+00:00"


def test_a_release_seen_late_is_stale(make_event, defaults):
    engine = Engine(defaults, State())
    on_time = engine.decide(event(make_event, at="2026-11-03T12:00:00Z", released_at="2026-11-03T10:00:00Z"))
    late = engine.decide(event(make_event, at="2026-11-03T12:00:01Z", released_at="2026-11-03T10:00:00Z",
                               code="GDP"))
    assert on_time.sent
    assert late.reasons == ["surprise", "stale"] and not late.sent


@pytest.mark.parametrize("fields", [
    {"country": "US"},
    {"importance": "top"},
    {"unit": "m"},
    {"actual": "0.46"},
    {"actual": None},
    {"consensus": "n/a"},
    {"previous": None},
    {"revised": True},
    {"released_at": "10:00"},
    {"code": ""},
])
def test_a_release_its_rule_cannot_read(make_event, defaults, fields):
    # The engine asks for the key, then the finding; either may find the field it cannot read.
    unreadable = event(make_event, **fields)
    with pytest.raises(EventError):
        release.key(unreadable)
        release.evaluate(unreadable, defaults.section("release"))


def test_a_release_its_rule_cannot_read_is_skipped_with_a_note(make_event, defaults):
    notes = []
    engine = Engine(defaults, State(), note=notes.append)
    assert engine.decide(event(make_event, id="r9", importance="urgent")) is None
    assert notes and notes[0].startswith("line 1 (id r9): skipped: importance must be one of high, medium, low")


# ----- settings ---------------------------------------------------------------------------------------------------

def test_the_default_settings(defaults):
    assert defaults.section("release") == {
        "stale_after_minutes": 120,
        "thresholds": {
            "high": {"pct": 0.10, "k": 15, "bn": 1.0},
            "medium": {"pct": 0.20, "k": 30, "bn": 2.0},
            "low": {"pct": 0.30, "k": 50, "bn": 3.0},
        },
    }


def test_the_thresholds_come_from_the_config(make_event, make_settings):
    strict = make_settings("[release.thresholds.high]\npct = 0.25\n")
    assert strict.get("release.thresholds.high.k") == 15
    assert evaluate(make_event, strict, actual=0.46, consensus=0.22) is None
    assert evaluate(make_event, strict, actual=0.47, consensus=0.22).level == "info"


def test_an_unknown_threshold_is_an_error(make_settings):
    with pytest.raises(ConfigError, match="unknown key release.thresholds.urgent.pct"):
        make_settings("[release.thresholds.urgent]\npct = 0.05\n")
    with pytest.raises(ConfigError, match="unknown key release.thresholds.high.m"):
        make_settings("[release.thresholds.high]\nm = 1.0\n")


# ----- the shared suppressions ------------------------------------------------------------------------------------

def test_a_release_alert_can_be_muted_by_key_or_prefix(make_event, defaults):
    for mute in ("release:VD:CPI", "release:VD:*", "release:*"):
        state = State()
        state.mute(mute)
        decision = Engine(defaults, state).decide(event(make_event))
        assert decision.reasons == ["surprise", "muted"] and not decision.sent, mute


def test_a_critical_release_passes_a_mute(make_event, defaults):
    state = State()
    state.mute("release:*")
    assert Engine(defaults, state).decide(event(make_event, actual=0.60)).sent


def test_quiet_hours(make_event, defaults):
    decision = Engine(defaults, State()).decide(event(make_event, at="2026-11-03T22:30:05Z",
                                                      released_at="2026-11-03T22:30:00Z"))
    assert decision.reasons == ["surprise", "quiet_hours"] and decision.message is None


def test_the_cooldown_goes_by_the_release_key(make_event, defaults):
    engine = Engine(defaults, State())
    first = engine.decide(event(make_event, at="2026-11-03T10:00:05Z"))
    again = engine.decide(event(make_event, at="2026-11-03T10:10:05Z", released_at="2026-11-03T10:10:00Z"))
    other = engine.decide(event(make_event, at="2026-11-03T10:10:05Z", released_at="2026-11-03T10:10:00Z",
                                country="QM"))
    assert first.sent and other.sent
    assert again.reasons == ["surprise", "cooldown"]


def test_release_alerts_count_towards_the_daily_cap(make_event, make_settings):
    settings = make_settings(QUIET_OFF + "daily_cap = 1\n")
    state = State()
    engine = Engine(settings, state)
    first = engine.decide(event(make_event, code="CPI"))
    second = engine.decide(event(make_event, code="GDP"))
    assert first.sent and second.reasons == ["surprise", "daily_cap"]
    assert state.count == 1
