import io

from alertd.cli import main
from alertd.feedcheck import check_feed, render

AT = "2026-11-03T10:00:00Z"


def test_a_feed_that_can_be_decided(defaults, make_event):
    events = [make_event("stale_feed", feed="prices-eu", last_update=AT),
              make_event("news", source="wire", headline="h", published_at=AT, tickers=[], tags=[])]
    result = check_feed(events, defaults)
    assert not result["problems"] and not result["notes"]
    assert render(result)[0] == "2 events: 2 can be decided, 0 cannot, 0 of kinds with no rule"


def test_problems_and_notes(defaults, make_event):
    events = [make_event("stale_feed", id="s1", feed="prices-eu", last_update="10:00"),
              make_event("fx_fixing", id="f1"),
              make_event("limit_usage", id="l1", desk="rates", limit="VAR", used=1.0, limit_amount=0,
                         measured_at=AT)]
    result = check_feed(events, defaults)
    assert len(result["problems"]) == 2 and result["problems"][0].startswith("line 1 (id s1): last_update")
    assert result["notes"] == ["line 2 (id f1): no rule for kind 'fx_fixing'"]
    lines = render(result)
    assert lines[0] == "3 events: 0 can be decided, 2 cannot, 1 of kinds with no rule"
    assert lines[-1] == "note: line 2 (id f1): no rule for kind 'fx_fixing'"


def test_the_examples_can_be_decided(root):
    for kind in ("price_move", "limit_usage", "stale_feed", "news"):
        out = io.StringIO()
        code = main(["check-feed", "--feed", str(root / "examples" / f"feed-{kind}.jsonl"),
                     "--config", str(root / "config" / "alerts.toml")], out=out, err=io.StringIO())
        assert code == 0, out.getvalue()


def test_the_command_fails_on_a_problem(write_lines, tmp_path):
    feed = write_lines("feed.jsonl", [{"id": "s1", "kind": "stale_feed", "at": AT, "feed": "prices-eu"}])
    config = tmp_path / "alerts.toml"
    config.write_text("", encoding="utf-8")
    out = io.StringIO()
    assert main(["check-feed", "--feed", str(feed), "--config", str(config)], out=out, err=io.StringIO()) == 1
    assert "problem: line 1 (id s1)" in out.getvalue()
