"""Relative return split into allocation and selection, group by group.

A two-way Brinson split over the tracking window, for one dimension of
folio.calc.exposure. For each group:

    allocation = (book weight - index weight) x (index return in the group - index return)
    selection  = book weight x (book return in the group - index return in the group)

Allocation rewards being overweight in groups that beat the index; selection
rewards holding names that beat the index's names in the same group. The
interaction term is left inside selection.

Book weights and returns come from aggregate.attribution.contributions():
today's holdings valued at the start of the window, the same simplification as
the NAV series behind the tracking error. The index weights are those of
benchmark.csv, kept for the whole window. The total index return comes from
the levels.

The index return within a group is the weighted return, in the base currency,
of its constituents that prices.csv has prices for. Constituents without
prices are taken to have done what the priced ones in their group did, and a
group with no priced constituent what the whole index did, so it shows no
allocation effect. A group the index does not have at all (funds, cash) has
nothing to select against, so its whole difference from the index is
allocation.

Allocation plus selection adds up to the book's return minus the index return
rebuilt from the constituents. What separates that from the relative return
measured with the levels is the residual: unpriced constituents, weights that
drifted during the window and index fees all end up there. A large residual
means benchmark.csv covers the index poorly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from folio.aggregate.attribution import CASH_KEY, contributions, total_return
from folio.benchmark.active import ActiveLine, Comparison, group_label
from folio.benchmark.levels_csv import IndexLevels
from folio.calc.exposure import Dimension
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory
from folio.domain.instruments import Instrument
from folio.errors import MissingPriceError


@dataclass(frozen=True)
class GroupEffect:
    """One group's part of the relative return."""

    key: str
    book_weight: Decimal          # at the start of the window
    index_weight: Decimal
    book_return: Decimal | None   # None when the book holds nothing in the group
    index_return: Decimal | None  # None when the index has nothing in the group
    allocation: Decimal
    selection: Decimal

    @property
    def total(self) -> Decimal:
        return self.allocation + self.selection


@dataclass(frozen=True)
class AllocationSplit:
    """The relative return over a window, split by group."""

    dimension: Dimension
    start: date
    end: date
    book_return: Decimal
    index_return: Decimal          # from the levels
    rebuilt_return: Decimal        # the index return rebuilt from the constituents
    priced_weight: Decimal         # share of the index with prices in prices.csv
    rows: tuple[GroupEffect, ...]  # a separate cash row comes last

    @property
    def relative_return(self) -> Decimal:
        return self.book_return - self.index_return

    @property
    def allocation(self) -> Decimal:
        return sum((row.allocation for row in self.rows), Decimal(0))

    @property
    def selection(self) -> Decimal:
        return sum((row.selection for row in self.rows), Decimal(0))

    @property
    def residual(self) -> Decimal:
        """Relative return not explained by the groups: rebuilt minus measured index return."""
        return self.relative_return - self.allocation - self.selection


def constituent_return(line: ActiveLine, prices: PriceHistory, fx: FxRates, start: date, end: date,
                       base_currency: str) -> Decimal | None:
    """Return of one constituent from ``start`` to ``end`` in the base currency.

    None when it cannot be priced: instruments.csv does not know it, or
    prices.csv or fx.csv have nothing for it on or before ``start``.
    """
    instrument = line.instrument
    if not isinstance(instrument, Instrument) or instrument.id not in prices:
        return None
    try:
        before = prices.latest(instrument.id, start).price * fx.rate(instrument.currency, base_currency, start)
        after = prices.latest(instrument.id, end).price * fx.rate(instrument.currency, base_currency, end)
    except MissingPriceError:
        return None
    return after / before - 1


def split_by_group(comparison: Comparison, prices: PriceHistory, fx: FxRates, levels: IndexLevels,
                   start: date, dimension: Dimension) -> AllocationSplit:
    """Split the relative return from ``start`` to the valuation date by ``dimension``.

    Raises ValueError when ``start`` is not before the valuation date.
    """
    valuation = comparison.valuation
    end = valuation.as_of
    parts = contributions(valuation, prices, fx, start, lambda line: group_label(dimension, line),
                          cash_by_currency=dimension.includes_cash)
    index_return = levels.period_return(start, end)

    index_weight: dict[str, Decimal] = {}
    priced: dict[str, tuple[Decimal, Decimal]] = {}  # label -> (priced weight, weighted return)
    for line in comparison.lines:
        if not line.listed:
            continue
        label = line.label(dimension)
        index_weight[label] = index_weight.get(label, Decimal(0)) + line.index
        result = constituent_return(line, prices, fx, start, end, valuation.base_currency)
        if result is not None:
            weight, weighted = priced.get(label, (Decimal(0), Decimal(0)))
            priced[label] = (weight + line.index, weighted + line.index * result)
    group_return = {
        label: priced[label][1] / priced[label][0] if label in priced else index_return
        for label in index_weight
    }

    rows = []
    for label in sorted(set(parts) | set(index_weight)):
        part = parts.get(label)
        book_weight = part.start_weight if part is not None else Decimal(0)
        book_return = part.contribution / part.start_weight if part is not None and part.start_weight else None
        index_return_in = group_return.get(label)
        # The return the group is measured against: the index's own in the group if it has one.
        reference = next(value for value in (index_return_in, book_return, index_return) if value is not None)
        rows.append(GroupEffect(
            key=label,
            book_weight=book_weight,
            index_weight=index_weight.get(label, Decimal(0)),
            book_return=book_return,
            index_return=index_return_in,
            allocation=(book_weight - index_weight.get(label, Decimal(0))) * (reference - index_return),
            selection=book_weight * (book_return - reference) if book_return is not None else Decimal(0),
        ))

    return AllocationSplit(
        dimension=dimension,
        start=start,
        end=end,
        book_return=total_return(parts),
        index_return=index_return,
        rebuilt_return=sum((index_weight[label] * group_return[label] for label in index_weight), Decimal(0)),
        priced_weight=sum((weight for weight, _ in priced.values()), Decimal(0)),
        rows=_ordered(rows, dimension),
    )


def _ordered(rows: list[GroupEffect], dimension: Dimension) -> tuple[GroupEffect, ...]:
    """Largest total effect first, ties by key, or the dimension's fixed order; cash last."""
    cash = [row for row in rows if row.key == CASH_KEY and not dimension.includes_cash]
    groups = [row for row in rows if row.key != CASH_KEY or dimension.includes_cash]
    if dimension.order is None:
        groups.sort(key=lambda row: (-row.total, row.key))
    else:
        rank = {key: position for position, key in enumerate(dimension.order)}
        groups.sort(key=lambda row: (rank.get(row.key, len(rank)), row.key))
    return tuple(groups + cash)
