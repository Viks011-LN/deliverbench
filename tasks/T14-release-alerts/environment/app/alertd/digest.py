"""A summary of decisions: `alertd digest FILE` reads what `replay` printed (one decision per line) and counts, for
each kind, the events decided, the ones worth an alert and the alerts sent; then the alerts sent by level, and the
ones held back by each suppression. The desk's morning note quotes it."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from alertd.errors import FeedError
from alertd.levels import LEVELS
from alertd.suppress import ORDER

FIELDS = ("id", "kind", "key", "sent", "level", "reasons", "message")


def read_decisions(path: str | Path) -> list[dict]:
    """The decisions in a file `replay` wrote; FeedError for a line that is not one."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise FeedError(f"cannot read the decisions {path}: {exc.strerror or exc}") from None
    decisions = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            raise FeedError(f"{path} line {number}: not JSON") from None
        if not isinstance(data, dict) or any(name not in data for name in FIELDS):
            raise FeedError(f"{path} line {number}: not a decision (it needs {', '.join(FIELDS)})")
        decisions.append(data)
    return decisions


def held_back_by(decision: dict) -> str | None:
    """The suppression that stopped an alert worth sending, or None."""
    if decision["sent"] or decision["level"] is None or not decision["reasons"]:
        return None
    tag = decision["reasons"][-1]
    return tag if tag in ORDER else None


def summarise(decisions: list[dict]) -> dict:
    kinds: dict[str, Counter] = {}
    levels, held = Counter(), Counter()
    for decision in decisions:
        counts = kinds.setdefault(decision["kind"], Counter())
        counts["events"] += 1
        if decision["level"] is not None:
            counts["alerts"] += 1
        if decision["sent"]:
            counts["sent"] += 1
            levels[decision["level"]] += 1
        tag = held_back_by(decision)
        if tag is not None:
            held[tag] += 1
    return {"kinds": kinds, "levels": levels, "held": held}


def render(summary: dict) -> list[str]:
    """The digest as lines of text: a table by kind, then two lines of totals."""
    rows = [(kind, c["events"], c["alerts"], c["sent"]) for kind, c in sorted(summary["kinds"].items())]
    total = ("all", sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows))
    width = max([len("kind")] + [len(r[0]) for r in rows])
    lines = [f"{'kind':<{width}}  events  alerts  sent"]
    for kind, events, alerts, sent in [*rows, total]:
        lines.append(f"{kind:<{width}}  {events:>6}  {alerts:>6}  {sent:>4}")
    lines.append("sent by level: " + ", ".join(f"{level} {summary['levels'][level]}" for level in LEVELS))
    lines.append("held back: " + ", ".join(f"{tag} {summary['held'][tag]}" for tag in ORDER))
    return lines
