"""The rules alertd knows, by kind (rules/__init__.py says what a rule module provides).

An event whose kind is not here is skipped with a note (engine.py)."""
from __future__ import annotations

from alertd.rules import limit_usage, news, price_move, release, stale_feed

RULES = {module.KIND: module for module in (price_move, limit_usage, stale_feed, news, release)}


def rule_for(kind: str):
    """The rule module for a kind, or None."""
    return RULES.get(kind)


def kinds() -> list[str]:
    return sorted(RULES)
