"""Economic releases: a figure far from what the market expected, or a revision of the previous figure big enough to
matter (docs/desk/release-alerts.md)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from alertd import format as fmt
from alertd.levels import raise_level
from alertd.model import Finding

KIND = "release"
COUNTRIES = ("VD", "QM", "XR")
IMPORTANCES = ("high", "medium", "low")
UNITS = ("pct", "k", "bn")
# A surprise of at least three times its threshold is critical, of at least twice a warning, of at least it info.
SURPRISE_LEVELS = ((3, "critical"), (2, "warning"), (1, "info"))


def key(event) -> str:
    return f"{KIND}:{event.choice('country', COUNTRIES)}:{event.text('release')}"


def exact(value: float) -> Decimal:
    """A figure as it is written: 0.3 is 0.3, not the float nearest to it."""
    return Decimal(repr(float(value)))


def difference(value: float, base: float) -> Decimal:
    """``value`` less ``base``, exactly as the two figures are written. With floats 0.3 less 0.2 would be
    0.09999999999999998, short of a threshold of 0.10 it is equal to."""
    return exact(value) - exact(base)


def surprise_level(size: Decimal, threshold: Decimal) -> str | None:
    """The level a surprise of ``size`` (its absolute value) reaches, or None below the threshold."""
    for multiple, level in SURPRISE_LEVELS:
        if size >= threshold * multiple:
            return level
    return None


def evaluate(event, settings: dict) -> Finding | None:
    country = event.choice("country", COUNTRIES)
    release = event.text("release")
    importance = event.choice("importance", IMPORTANCES)
    unit = event.choice("unit", UNITS)
    released_at = event.time("released_at")
    actual = event.number("actual")
    consensus = event.optional_number("consensus")
    previous = event.number("previous")
    revised = event.optional_number("revised")
    threshold = exact(settings["thresholds"][importance][unit])

    level, reasons = None, []
    what, detail = [f"actual {fmt.amount(actual, unit)}"], []
    # No consensus, no surprise.
    if consensus is not None:
        surprise = difference(actual, consensus)
        level = surprise_level(abs(surprise), threshold)
        if level is not None:
            reasons.append("surprise")
            what[0] += f" vs consensus {fmt.amount(consensus, unit)}"
            detail.append(f"surprise {fmt.signed(float(surprise), unit)}")
    # A revision big enough to matter is a reason too and raises the level one step; alone, it is info.
    if revised is not None:
        revision = difference(revised, previous)
        if abs(revision) >= threshold:
            reasons.append("revision")
            level = "info" if level is None else raise_level(level)
            what.append(f"previous revised from {fmt.amount(previous, unit)} to {fmt.amount(revised, unit)}")
            detail.append(f"revision {fmt.signed(float(revision), unit)}")
    if level is None:
        return None
    return Finding(
        key=key(event),
        level=level,
        reasons=reasons,
        subject=f"{country} {release}",
        what=", ".join(what),
        detail=", ".join(detail),
        as_of=released_at,
        stale_after=timedelta(minutes=settings["stale_after_minutes"]),
    )
