"""Exposure breakdowns: how NAV splits by sector, currency or instrument kind.

A Dimension says how to label each position (its key), what to call the
column and in what order the rows go. breakdown() groups the valuation's
positions with aggregate.rollup and gives every group as a share of NAV.
Rows come largest first, ties by name, unless the dimension has a fixed order.

Cash belongs to no sector and no kind, so those breakdowns leave it out of the
rows and carry it separately (Breakdown.cash); rows plus cash add up to NAV.
Cash *is* currency exposure, so the currency breakdown folds each balance
into its currency's row instead and its Breakdown.cash is zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, NamedTuple

from folio.aggregate.rollup import rollup, share, top_n
from folio.calc.valuation import PositionValue, Valuation
from folio.domain.instruments import KINDS
from folio.domain.money import Money


@dataclass(frozen=True)
class Dimension:
    """A way of slicing the portfolio, e.g. by sector."""

    name: str                                # as typed after --by
    title: str                               # column heading in reports
    key: Callable[[PositionValue], str]      # label of one position
    order: tuple[str, ...] | None = None     # fixed row order; None means largest first
    includes_cash: bool = False              # cash balances are rows of their own currency


@dataclass(frozen=True)
class ExposureRow:
    """One group of a breakdown: its label, how many positions, value and share of NAV."""

    key: str
    positions: int
    value: Money
    share: Decimal  # of NAV


@dataclass(frozen=True)
class Breakdown:
    """The rows of one breakdown, plus the cash that is in none of them."""

    dimension: Dimension
    rows: tuple[ExposureRow, ...]
    cash: Money  # cash that is in no row
    nav: Money

    def row(self, key: str) -> ExposureRow | None:
        return next((row for row in self.rows if row.key == key), None)

    def share_of(self, key: str) -> Decimal:
        row = self.row(key)
        return row.share if row is not None else Decimal(0)

    @property
    def positions(self) -> int:
        return sum(row.positions for row in self.rows)


def _sector(line: PositionValue) -> str:
    return line.instrument.sector


def _currency(line: PositionValue) -> str:
    return line.instrument.currency


def _kind(line: PositionValue) -> str:
    return line.instrument.kind


SECTOR = Dimension("sector", "Sector", _sector)
CURRENCY = Dimension("currency", "Currency", _currency, includes_cash=True)
KIND = Dimension("kind", "Kind", _kind, order=KINDS)

DIMENSIONS = {dimension.name: dimension for dimension in (SECTOR, CURRENCY, KIND)}


class _Entry(NamedTuple):
    key: str
    amount: Decimal
    is_position: bool


def breakdown(valuation: Valuation, dimension: Dimension, top: int = 0) -> Breakdown:
    """Group ``valuation`` by ``dimension``.

    ``top`` > 0 keeps the largest ``top`` rows and folds the rest into
    "Other" (report.top_n). Dimensions with a fixed order are never folded.
    """
    entries = [_Entry(dimension.key(line), line.base_value.amount, True) for line in valuation.positions]
    cash = valuation.cash_total
    if dimension.includes_cash:
        entries += [_Entry(line.local_value.currency, line.base_value.amount, False) for line in valuation.cash]
        cash = Money.zero(valuation.base_currency)

    groups = rollup(entries, key=lambda entry: entry.key, value=lambda entry: entry.amount, order=dimension.order)
    if dimension.order is None:
        groups = top_n(groups, top)
    rows = tuple(
        ExposureRow(
            key=group.key,
            positions=sum(1 for entry in group.members if entry.is_position),
            value=Money(group.total, valuation.base_currency),
            share=share(group.total, valuation.nav.amount),
        )
        for group in groups
    )
    return Breakdown(dimension, rows, cash, valuation.nav)


def by_sector(valuation: Valuation) -> Breakdown:
    return breakdown(valuation, SECTOR)


def by_currency(valuation: Valuation) -> Breakdown:
    return breakdown(valuation, CURRENCY)


def by_kind(valuation: Valuation) -> Breakdown:
    return breakdown(valuation, KIND)
