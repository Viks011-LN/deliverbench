"""Active weights: the book's weight in each holding minus the index's.

compare() lines the valuation up against the index constituents: one
ActiveLine per instrument that the book holds or the index lists, plus one per
cash balance. Book weights are shares of NAV and the index weights were scaled
to add up to 1, so the active weights add up to zero.

Grouping reuses the dimensions of folio.calc.exposure, so a breakdown added
there works here without changes. A dimension's key is written for held lines
(PositionValue); a constituent the book does not hold is passed to it as an
_Unheld stand-in that has only ``instrument``, which is an Instrument when
instruments.csv knows the id and a weights_csv.Listing otherwise. When the key
reads something the stand-in lacks, or returns a blank, the line is grouped
under UNKNOWN rather than stopping the report.

Cash follows the core reports: a row of its own (CASH_KEY), except in a
breakdown that counts cash as currency exposure, where each balance joins its
currency's row. The index holds no cash.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from folio.aggregate.attribution import CASH_KEY
from folio.aggregate.rollup import rollup
from folio.benchmark.weights_csv import IndexWeights, Listing
from folio.calc.exposure import Dimension
from folio.calc.valuation import PositionValue, Valuation
from folio.domain.instruments import Instrument, Universe

UNKNOWN = "Unknown"
CASH_ID = "CASH"

# Columns of benchmark.csv that decide groups; checked against instruments.csv by describe().
GROUPING_FIELDS = ("kind", "sector", "country", "currency")


@dataclass(frozen=True)
class _Unheld:
    """What a dimension key sees for a constituent the book does not hold."""

    instrument: Instrument | Listing


def group_label(dimension: Dimension, subject) -> str:
    """``dimension``'s label for ``subject``, or UNKNOWN when there is none to give."""
    try:
        label = dimension.key(subject)
    except AttributeError:
        return UNKNOWN
    if not isinstance(label, str) or not label.strip():
        return UNKNOWN
    return label


@dataclass(frozen=True)
class ActiveLine:
    """One instrument held or listed, or one cash balance, with both weights."""

    id: str
    name: str
    currency: str
    book: Decimal                            # share of NAV; zero when not held
    index: Decimal                           # share of the index; zero when not listed
    instrument: Instrument | Listing | None  # None for a cash balance
    position: PositionValue | None = None    # None when the book does not hold it

    @property
    def active(self) -> Decimal:
        return self.book - self.index

    @property
    def held(self) -> bool:
        return self.position is not None

    @property
    def listed(self) -> bool:
        return self.index > 0

    @property
    def kind(self) -> str:
        return "cash" if self.instrument is None else self.instrument.kind

    @property
    def sector(self) -> str:
        return "" if self.instrument is None else self.instrument.sector

    def label(self, dimension: Dimension) -> str:
        """The group this line belongs to under ``dimension``."""
        if self.instrument is None:
            return self.currency if dimension.includes_cash else CASH_KEY
        subject = self.position if self.position is not None else _Unheld(self.instrument)
        return group_label(dimension, subject)


@dataclass(frozen=True)
class Comparison:
    """The book and the index side by side on the valuation date."""

    valuation: Valuation
    weights: IndexWeights
    lines: tuple[ActiveLine, ...]  # instruments, in id order
    cash: tuple[ActiveLine, ...]   # cash balances, in currency order
    notes: tuple[str, ...] = ()    # disagreements between benchmark.csv and instruments.csv

    @property
    def every_line(self) -> tuple[ActiveLine, ...]:
        return self.lines + self.cash


def describe(weights: IndexWeights, universe: Universe) -> tuple[dict[str, Instrument | Listing], list[str]]:
    """Reference data for every constituent, and notes on what benchmark.csv got wrong.

    instruments.csv is the reference for the ids it knows. If benchmark.csv
    also gives a kind, sector, country or currency for one of them and it
    differs, instruments.csv still wins and a note says so; a name that
    differs is normal (index providers spell names their own way).
    """
    described: dict[str, Instrument | Listing] = {}
    notes = []
    for item in weights.constituents:
        if item.id not in universe:
            described[item.id] = item.listing
            continue
        instrument = universe[item.id]
        for field in GROUPING_FIELDS:
            given, known = getattr(item.listing, field), getattr(instrument, field, "")
            if given and given != known:
                notes.append(f"{weights.source}:{item.line}: {item.id} has {field} {given!r} there but "
                             f"{known!r} in instruments.csv, which is used")
        described[item.id] = instrument
    return described, notes


def compare(valuation: Valuation, weights: IndexWeights, universe: Universe) -> Comparison:
    """Line ``valuation`` up against the index ``weights``."""
    described, notes = describe(weights, universe)
    held = {line.instrument.id: line for line in valuation.positions}
    index_weights = {item.id: item.weight for item in weights.constituents}
    lines = []
    for instrument_id in sorted(set(held) | set(described)):
        position = held.get(instrument_id)
        instrument = position.instrument if position is not None else described[instrument_id]
        lines.append(ActiveLine(
            id=instrument_id,
            name=instrument.name or instrument_id,
            currency=instrument.currency,
            book=position.weight if position is not None else Decimal(0),
            index=index_weights.get(instrument_id, Decimal(0)),
            instrument=instrument,
            position=position,
        ))
    cash = tuple(
        ActiveLine(CASH_ID, f"Cash {balance.local_value.currency}", balance.local_value.currency,
                   book=balance.weight, index=Decimal(0), instrument=None)
        for balance in valuation.cash
    )
    return Comparison(valuation, weights, tuple(lines), cash, tuple(notes))


def by_active_weight(lines: Iterable[ActiveLine]) -> list[ActiveLine]:
    """Largest overweight first, largest underweight last; ties by id."""
    return sorted(lines, key=lambda line: (-line.active, line.id))


@dataclass(frozen=True)
class ActiveGroup:
    """One group of a breakdown: how many names on each side and the two weights."""

    key: str
    held: int     # instruments the book holds in the group
    listed: int   # index constituents in the group
    book: Decimal
    index: Decimal

    @property
    def active(self) -> Decimal:
        return self.book - self.index


@dataclass(frozen=True)
class GroupedWeights:
    """Active weights by group, plus the book's cash that is in no group."""

    dimension: Dimension
    rows: tuple[ActiveGroup, ...]
    cash: Decimal  # zero when the dimension folds cash into its currency rows

    def row(self, key: str) -> ActiveGroup | None:
        return next((row for row in self.rows if row.key == key), None)


def by_group(comparison: Comparison, dimension: Dimension) -> GroupedWeights:
    """Group the comparison by ``dimension``.

    Rows come largest active weight first, ties by key, unless the dimension
    has a fixed order (kind); groups outside that order, such as UNKNOWN,
    follow it in key order. Nothing is folded into "Other": every group is a bet.
    """
    lines = list(comparison.lines)
    cash = sum((line.book for line in comparison.cash), Decimal(0))
    if dimension.includes_cash:
        lines += comparison.cash
        cash = Decimal(0)
    groups = rollup(lines, key=lambda line: line.label(dimension), value=lambda line: line.active,
                    order=dimension.order)
    rows = tuple(
        ActiveGroup(
            key=group.key,
            held=sum(1 for line in group.members if line.held),
            listed=sum(1 for line in group.members if line.listed),
            book=sum((line.book for line in group.members), Decimal(0)),
            index=sum((line.index for line in group.members), Decimal(0)),
        )
        for group in groups
    )
    return GroupedWeights(dimension, rows, cash)
