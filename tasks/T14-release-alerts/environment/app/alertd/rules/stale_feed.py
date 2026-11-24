"""Stale feeds: a data feed the desk relies on has gone quiet (docs/desk/stale-feeds.md).

Not to be confused with the stale suppression (alertd/suppress.py): a silent feed is worth knowing about however
late alertd hears of it, so these alerts are never stale themselves."""
from __future__ import annotations

from alertd import format as fmt
from alertd.model import Finding
from alertd.timeutil import minutes_between

KIND = "stale_feed"


def key(event) -> str:
    return f"{KIND}:{event.text('feed')}"


def evaluate(event, settings: dict) -> Finding | None:
    last_update = event.time("last_update")
    silent = minutes_between(last_update, event.at)
    if silent >= settings["critical_after_minutes"]:
        level = "critical"
    elif silent >= settings["warn_after_minutes"]:
        level = "warning"
    else:
        return None
    return Finding(
        key=key(event),
        level=level,
        reasons=["silent"],
        subject=event.text("feed"),
        what=f"no update for {fmt.amount(silent, 'min')}",
        detail=f"last at {fmt.clock(last_update)}",
        as_of=event.at,
        stale_after=None,
    )
