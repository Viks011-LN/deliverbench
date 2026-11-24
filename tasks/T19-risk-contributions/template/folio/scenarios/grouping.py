"""Scenario P&L grouped by a report dimension.

The dimensions are those of calc/exposure.py (DIMENSIONS), so a breakdown
the core learns is available to ``run --by`` as well, with the same labels.
As in the exposure report, cash belongs to no sector and no kind and gets a
row of its own, except by currency, where each balance joins its currency's
row; rows plus cash always add up to the total.

Rows come worst first (largest loss), ties by name, unless the dimension
has a fixed order of its own, such as kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple, Sequence

from folio.aggregate.attribution import CASH_KEY
from folio.aggregate.rollup import rollup, share
from folio.calc.exposure import Dimension
from folio.domain.money import Money
from folio.scenarios.engine import ScenarioResult

TOTAL_KEY = "Total"


@dataclass(frozen=True)
class GroupPnl:
    """One group's value before and after a scenario."""

    key: str
    positions: int
    value: Money     # before the scenario
    stressed: Money  # after it
    share: Decimal   # P&L as a fraction of NAV

    @property
    def pnl(self) -> Money:
        return self.stressed - self.value


@dataclass(frozen=True)
class StressBreakdown:
    """The groups of one scenario result, the cash that is in none of them, and the total."""

    dimension: Dimension
    rows: tuple[GroupPnl, ...]
    cash: GroupPnl | None  # None when cash is folded into the rows or there is none
    total: GroupPnl

    def row(self, key: str) -> GroupPnl | None:
        return next((row for row in self.rows if row.key == key), None)


class _Entry(NamedTuple):
    key: str
    value: Decimal
    stressed: Decimal
    is_position: bool


def group_pnl(result: ScenarioResult, dimension: Dimension) -> StressBreakdown:
    """Split ``result`` by ``dimension``."""
    entries = [_Entry(dimension.key(line.line), line.line.base_value.amount, line.stressed_value.amount, True)
               for line in result.positions]
    cash_entries = [
        _Entry(cash.currency if dimension.includes_cash else CASH_KEY, cash.cash.base_value.amount,
               cash.stressed_value.amount, False)
        for cash in result.cash
    ]
    if dimension.includes_cash:
        entries, cash_entries = entries + cash_entries, []

    # rollup puts the largest total first; totalling the loss puts the worst group first.
    groups = rollup(entries, key=lambda entry: entry.key, value=lambda entry: entry.value - entry.stressed,
                    order=dimension.order)
    nav = result.valuation.nav.amount
    base = result.valuation.base_currency
    rows = tuple(_group(group.key, group.members, nav, base) for group in groups)
    cash = _group(CASH_KEY, cash_entries, nav, base) if cash_entries else None
    total = _group(TOTAL_KEY, entries + cash_entries, nav, base)
    return StressBreakdown(dimension, rows, cash, total)


def _group(key: str, members: Sequence[_Entry], nav: Decimal, base: str) -> GroupPnl:
    value = sum((member.value for member in members), Decimal(0))
    stressed = sum((member.stressed for member in members), Decimal(0))
    return GroupPnl(
        key=key,
        positions=sum(1 for member in members if member.is_position),
        value=Money(value, base),
        stressed=Money(stressed, base),
        share=share(stressed - value, nav),
    )
