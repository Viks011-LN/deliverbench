"""Price moves: an instrument's price, or its yield, has moved further than the desk wants to miss
(docs/desk/price-moves.md)."""
from __future__ import annotations

from datetime import timedelta

from alertd import format as fmt
from alertd.errors import EventError
from alertd.model import Finding

KIND = "price_move"
MEASURES = ("pct", "bp")
WORDS = {"pct": "price", "bp": "yield"}
# Prices are written with two decimals; yields, quoted in percent, with three.
PLACES = {"pct": 2, "bp": 3}


def key(event) -> str:
    return f"{KIND}:{event.text('instrument')}"


def move(last: float, reference: float, measure: str) -> float:
    """The move from ``reference`` to ``last``: in percent of the reference for a price, in basis points for a yield
    (a yield is quoted in percent, so a hundredth of a point is one basis point)."""
    if measure == "pct":
        return (last - reference) / reference * 100
    return (last - reference) * 100


def evaluate(event, settings: dict) -> Finding | None:
    measure = event.choice("measure", MEASURES)
    last = event.number("last")
    reference = event.number("reference")
    if measure == "pct" and reference == 0:
        raise EventError("reference must not be zero for a price")
    size = move(last, reference, measure)
    threshold = settings["threshold_pct"] if measure == "pct" else settings["threshold_bp"]
    if abs(size) < threshold:
        return None
    level = "critical" if abs(size) >= threshold * settings["critical_multiple"] else "warning"
    places = PLACES[measure]
    return Finding(
        key=key(event),
        level=level,
        reasons=["move"],
        subject=event.text("instrument"),
        what=f"{WORDS[measure]} {fmt.change(size, measure)}",
        detail=f"last {fmt.number(last, places)}, from {fmt.number(reference, places)}",
        as_of=event.time("quoted_at"),
        stale_after=timedelta(minutes=settings["stale_after_minutes"]),
    )
