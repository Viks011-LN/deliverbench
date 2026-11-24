"""Economic releases: a figure far from the consensus, or a revision of the previous figure
(docs/desk/release-alerts.md).

Both are judged against the threshold for the release's importance and unit (release.thresholds.<importance>.<unit>).
Staleness, mutes, quiet hours, the cooldown and the daily cap are the shared suppressions, as for every kind."""
from __future__ import annotations

from datetime import timedelta

from alertd import format as fmt
from alertd.levels import raise_level
from alertd.model import Finding

KIND = "release"
IMPORTANCES = ("high", "medium", "low")
UNITS = ("pct", "k", "bn")


def key(event) -> str:
    return f"{KIND}:{event.text('country')}:{event.text('release')}"


def surprise_level(size: float, threshold: float) -> str:
    """The level of a surprise of at least the threshold: critical from three times it, warning from twice."""
    if size >= 3 * threshold:
        return "critical"
    if size >= 2 * threshold:
        return "warning"
    return "info"


def evaluate(event, settings: dict) -> Finding | None:
    importance = event.choice("importance", IMPORTANCES)
    unit = event.choice("unit", UNITS)
    actual = event.number("actual")
    consensus = event.optional_number("consensus")
    previous = event.number("previous")
    revised = event.optional_number("revised")
    threshold = settings["thresholds"][importance][unit]

    reasons, level = [], None
    surprise = None if consensus is None else actual - consensus
    if surprise is not None and abs(surprise) >= threshold:
        reasons.append("surprise")
        level = surprise_level(abs(surprise), threshold)
    revision = None if revised is None else revised - previous
    if revision is not None and abs(revision) >= threshold:
        reasons.append("revision")
        level = "info" if level is None else raise_level(level)
    if level is None:
        return None

    what, detail = [], []
    if "surprise" in reasons:
        what.append(f"actual {fmt.amount(actual, unit)} vs consensus {fmt.amount(consensus, unit)}")
        detail.append(f"surprise {fmt.signed(surprise, unit)}")
    else:
        what.append(f"actual {fmt.amount(actual, unit)}")
    if "revision" in reasons:
        what.append(f"previous revised from {fmt.amount(previous, unit)} to {fmt.amount(revised, unit)}")
        detail.append(f"revision {fmt.signed(revision, unit)}")
    return Finding(
        key=key(event),
        level=level,
        reasons=reasons,
        subject=f"{event.text('country')} {event.text('release')}",
        what=", ".join(what),
        detail=", ".join(detail),
        as_of=event.time("released_at"),
        stale_after=timedelta(minutes=settings["stale_after_minutes"]),
    )
