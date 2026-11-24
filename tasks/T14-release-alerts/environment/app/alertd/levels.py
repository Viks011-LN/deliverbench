"""Alert levels. Every kind uses the same three, lowest first: info, warning, critical.

A critical alert is the one the desk must see whatever it is doing: it passes mutes, quiet hours and the daily cap
(alertd/suppress.py)."""
from __future__ import annotations

LEVELS = ("info", "warning", "critical")


def check(level: str) -> str:
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; levels are {', '.join(LEVELS)}")
    return level


def rank(level: str) -> int:
    """0 for info, 1 for warning, 2 for critical."""
    return LEVELS.index(check(level))


def higher(a: str, b: str) -> str:
    """The more serious of two levels."""
    return a if rank(a) >= rank(b) else b


def raise_level(level: str, steps: int = 1) -> str:
    """The level ``steps`` above ``level``. Nothing is above critical, so critical stays critical."""
    return LEVELS[min(rank(level) + steps, len(LEVELS) - 1)]


def is_critical(level: str | None) -> bool:
    return level == "critical"
