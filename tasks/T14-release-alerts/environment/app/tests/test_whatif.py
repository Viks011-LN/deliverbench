import io

from alertd.cli import main
from alertd.state import State
from alertd.whatif import compare, render

AT = "2026-11-03T10:00:00Z"


def prices(make_event):
    return [make_event("price_move", id="a", at=AT, instrument="ORVK", quoted_at=AT, last=41.90, reference=42.60,
                       measure="pct"),
            make_event("price_move", id="b", at="2026-11-03T10:01:00Z", instrument="BRHW", quoted_at=AT,
                       last=19.35, reference=19.10, measure="pct"),
            make_event("fx_fixing", id="c")]


def test_the_same_settings_change_nothing(make_settings, make_event):
    settings = make_settings("")
    assert compare(prices(make_event), State(), settings, settings) == []


def test_a_lower_threshold(make_settings, make_event):
    before, after = make_settings(""), make_settings("[price_move]\nthreshold_pct = 1.25\n")
    differences = compare(prices(make_event), State(), before, after)
    assert [d.id for d in differences] == ["b"]
    assert differences[0].fields() == ["sent", "level", "reasons", "message"]
    lines = render(differences, 3)
    assert lines[:2] == ["1 of 3 events decided differently", "b (price_move): no alert -> sent warning [move]"]


def test_a_lower_cap(make_settings, make_event):
    before = make_settings("")
    after = make_settings("[alerts]\ndaily_cap = 1\n")
    differences = compare(prices(make_event), State(), before, make_settings("[alerts]\ndaily_cap = 0\n"))
    assert [d.id for d in differences] == ["a"]
    assert render(differences, 3)[1] == "a (price_move): sent warning [move] -> held warning [move, daily_cap]"
    assert compare(prices(make_event), State(), before, after) == []


def test_the_state_is_left_alone(make_settings, make_event):
    state = State()
    compare(prices(make_event), state, make_settings(""), make_settings("[alerts]\ndaily_cap = 0\n"))
    assert state.count == 0 and state.last_alert == {}


def test_the_command(root, tmp_path):
    other = tmp_path / "other.toml"
    other.write_text((root / "config" / "alerts.toml").read_text(encoding="utf-8")
                     .replace("daily_cap = 20", "daily_cap = 3"), encoding="utf-8")
    out = io.StringIO()
    code = main(["what-if", "--feed", str(root / "examples" / "feed-limit_usage.jsonl"),
                 "--state", str(root / "examples" / "state.json"), "--config", str(root / "config" / "alerts.toml"),
                 "--with", str(other)], out=out, err=io.StringIO())
    assert code == 0
    assert out.getvalue().splitlines()[0].endswith("events decided differently")
    assert "daily_cap" in out.getvalue()
