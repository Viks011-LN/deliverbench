"""Limit usage: a desk is using a large share of one of its risk limits (docs/desk/limit-usage.md)."""
from __future__ import annotations

from datetime import timedelta

from alertd import format as fmt
from alertd.errors import EventError
from alertd.model import Finding

KIND = "limit_usage"


def key(event) -> str:
    return f"{KIND}:{event.text('desk')}:{event.text('limit')}"


def usage_pct(used: float, limit_amount: float) -> float:
    return used / limit_amount * 100


def level_for(usage: float, settings: dict) -> str | None:
    """The level a usage (in percent) reaches, or None below the lowest."""
    if usage >= settings["critical_at_pct"]:
        return "critical"
    if usage >= settings["warn_at_pct"]:
        return "warning"
    if usage >= settings["info_at_pct"]:
        return "info"
    return None


def evaluate(event, settings: dict) -> Finding | None:
    used = event.number("used")
    limit_amount = event.number("limit_amount")
    if limit_amount <= 0:
        raise EventError(f"limit_amount must be more than zero, got {limit_amount!r}")
    usage = usage_pct(used, limit_amount)
    level = level_for(usage, settings)
    if level is None:
        return None
    reasons = ["usage"]
    if used > limit_amount:
        reasons.append("breach")
    return Finding(
        key=key(event),
        level=level,
        reasons=reasons,
        subject=f"{event.text('desk')} {event.text('limit')}",
        what=f"{fmt.share(used, limit_amount)} of limit used",
        detail=f"{fmt.amount(used, 'm')} of {fmt.amount(limit_amount, 'm')}",
        as_of=event.time("measured_at"),
        stale_after=timedelta(minutes=settings["stale_after_minutes"]),
    )
