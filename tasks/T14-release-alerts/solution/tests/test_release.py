"""Release alerts: the worked examples of docs/desk/release-alerts.md, and the rules around them."""
import io
import json
import re

import pytest

from alertd.cli import main
from alertd.rules import release


def example_pairs(root):
    """(event, decision) for each worked example: the two JSON lines under each example heading."""
    text = (root / "docs" / "desk" / "release-alerts.md").read_text(encoding="utf-8")
    lines = [json.loads(line.strip()) for line in text.splitlines() if re.match(r"^    \{", line)]
    return list(zip(lines[0::2], lines[1::2]))


def test_the_worked_examples(root):
    out = io.StringIO()
    code = main(["replay", "--feed", str(root / "examples" / "feed-release.jsonl"),
                 "--state", str(root / "examples" / "state.json"),
                 "--config", str(root / "config" / "alerts.toml")], out=out, err=io.StringIO())
    assert code == 0
    printed = {d["id"]: d for d in map(json.loads, out.getvalue().splitlines())}
    pairs = example_pairs(root)
    assert len(pairs) == 6
    for event, decision in pairs:
        assert printed[event["id"]] == decision


def finding(make_event, defaults_with_release, **fields):
    data = {"country": "VD", "release": "CPI", "released_at": "2026-11-03T10:00:00Z", "importance": "high",
            "unit": "pct", "actual": 0.30, "consensus": 0.30, "previous": 0.20, "revised": None, **fields}
    return release.evaluate(make_event("release", **data), defaults_with_release)


@pytest.fixture
def defaults_with_release(root):
    from alertd.config import load_settings
    return load_settings(root / "config" / "alerts.toml").section("release")


def test_a_revision_below_the_threshold_is_no_reason(make_event, defaults_with_release):
    assert finding(make_event, defaults_with_release, revised=0.25) is None


def test_no_consensus_and_no_revision_is_no_alert(make_event, defaults_with_release):
    assert finding(make_event, defaults_with_release, consensus=None) is None


def test_a_revision_alone_is_info_whatever_its_size(make_event, defaults_with_release):
    found = finding(make_event, defaults_with_release, consensus=None, revised=0.75)
    assert (found.level, found.reasons) == ("info", ["revision"])


def test_critical_stays_critical(make_event, defaults_with_release):
    found = finding(make_event, defaults_with_release, actual=0.75, revised=0.45)
    assert (found.level, found.reasons) == ("critical", ["surprise", "revision"])


def test_the_key(make_event):
    assert release.key(make_event("release", country="QM", release="PAYROLLS")) == "release:QM:PAYROLLS"
