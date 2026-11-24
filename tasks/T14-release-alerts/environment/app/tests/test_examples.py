"""The decisions in examples/ are what alertd prints for the example feeds (README.md, "Events")."""
import io
import json

import pytest

from alertd.cli import main

KINDS = ("price_move", "limit_usage", "stale_feed", "news")


def replay(root, kind):
    out, err = io.StringIO(), io.StringIO()
    code = main(["replay", "--feed", str(root / "examples" / f"feed-{kind}.jsonl"),
                 "--state", str(root / "examples" / "state.json"),
                 "--config", str(root / "config" / "alerts.toml")], out=out, err=err)
    return code, out.getvalue()


@pytest.mark.parametrize("kind", KINDS)
def test_the_example_decisions(root, kind):
    code, out = replay(root, kind)
    assert code == 0
    assert out == (root / "examples" / f"decisions-{kind}.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", KINDS)
def test_each_example_feed_holds_one_kind(root, kind):
    lines = (root / "examples" / f"feed-{kind}.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines and {json.loads(line)["kind"] for line in lines} == {kind}
