"""`alertd check-feed --feed F [--config C]`: whether every event in a feed can be decided.

The feed team runs it on a sample before a new source goes live. Every event goes to its kind's rule, with the
settings in force, exactly as the engine would send it (but with no state, so nothing is suppressed or recorded).
An event whose rule cannot read it is a problem; an event of a kind alertd has no rule for is only noted, since a
feed may carry kinds that alertd does not decide."""
from __future__ import annotations

from collections import Counter

from alertd import registry
from alertd.config import Settings
from alertd.errors import EventError
from alertd.feed import Event


def check_feed(events: list[Event], settings: Settings, rules: dict | None = None) -> dict:
    """{"problems": [...], "notes": [...], "decided": Counter by kind, "skipped": Counter by kind}."""
    rules = registry.RULES if rules is None else rules
    result = {"problems": [], "notes": [], "decided": Counter(), "skipped": Counter()}
    for event in events:
        rule = rules.get(event.kind)
        if rule is None:
            result["skipped"][event.kind] += 1
            result["notes"].append(f"{event.where()}: no rule for kind {event.kind!r}")
            continue
        try:
            rule.key(event)
            rule.evaluate(event, settings.section(event.kind))
        except EventError as exc:
            result["problems"].append(f"{event.where()}: {exc}")
            continue
        result["decided"][event.kind] += 1
    return result


def render(result: dict) -> list[str]:
    decided, skipped = result["decided"], result["skipped"]
    total = sum(decided.values()) + sum(skipped.values()) + len(result["problems"])
    lines = [f"{total} events: {sum(decided.values())} can be decided, {len(result['problems'])} cannot, "
             f"{sum(skipped.values())} of kinds with no rule"]
    lines += [f"  {kind}: {count}" for kind, count in sorted(decided.items())]
    lines += [f"problem: {text}" for text in result["problems"]]
    lines += [f"note: {text}" for text in result["notes"]]
    return lines
