"""Text output for the benchmark commands.

Each renderer returns one string for the CLI to print, under the same header
as the core reports. Weights and returns get one decimal more than
report.percent_places: active weights of a few tenths of a percent are what
these reports are about, and at one decimal they would round away. Cash rows
follow report.show_cash, as in ``folio report``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from folio.aggregate.attribution import CASH_KEY
from folio.benchmark.active import ActiveLine, Comparison, GroupedWeights, by_active_weight
from folio.benchmark.allocation import AllocationSplit
from folio.benchmark.overlap import Overlap
from folio.benchmark.tracking import TrackingSummary
from folio.calc.valuation import Valuation
from folio.config.settings import ReportSettings
from folio.report.tables import Column, clip, format_pct, render_table
from folio.report.text_report import NAME_WIDTH, header


def _against(comparison: Comparison) -> str:
    return f"against {comparison.weights.source} ({len(comparison.weights)} constituents)"


def _pairs(pairs: Sequence[tuple[str, str]]) -> list[str]:
    """``label  value`` lines with the values lined up, as in ``folio risk``."""
    width = max(len(label) for label, _ in pairs)
    return [f"{label.ljust(width)}  {value}".rstrip() for label, value in pairs]


def _lines_table(lines: Sequence[ActiveLine], places: int, with_total: bool = False) -> str:
    columns = [
        Column("Instrument"),
        Column("Name"),
        Column("Kind"),
        Column("Book", "right"),
        Column("Index", "right"),
        Column("Active", "right"),
    ]
    rows = [
        [line.id, clip(line.name, NAME_WIDTH), line.kind, format_pct(line.book, places),
         format_pct(line.index, places), format_pct(line.active, places, signed=True)]
        for line in lines
    ]
    total = None
    if with_total:
        book = sum((line.book for line in lines), Decimal(0))
        index = sum((line.index for line in lines), Decimal(0))
        total = ["Total", "", "", format_pct(book, places), format_pct(index, places),
                 format_pct(book - index, places, signed=True)]
    return render_table(columns, rows, total)


def render_holdings(comparison: Comparison, settings: ReportSettings) -> str:
    """Every instrument held or listed, largest overweight first, then the cash balances."""
    shown = by_active_weight(comparison.lines) + (list(comparison.cash) if settings.show_cash else [])
    lines = header(comparison.valuation) + [
        f"Active weights by holding {_against(comparison)}",
        _lines_table(shown, settings.percent_places + 1, with_total=True),
    ]
    return "\n".join(lines) + "\n"


def render_groups(comparison: Comparison, grouped: GroupedWeights, settings: ReportSettings) -> str:
    """Active weights by group for ``active --by ...``."""
    places = settings.percent_places + 1
    dimension = grouped.dimension
    columns = [
        Column(dimension.title),
        Column("Held", "right"),
        Column("In index", "right"),
        Column("Book", "right"),
        Column("Index", "right"),
        Column("Active", "right"),
    ]
    rows = [
        [row.key, str(row.held), str(row.listed), format_pct(row.book, places), format_pct(row.index, places),
         format_pct(row.active, places, signed=True)]
        for row in grouped.rows
    ]
    book = sum((row.book for row in grouped.rows), Decimal(0))
    index = sum((row.index for row in grouped.rows), Decimal(0))
    if settings.show_cash and grouped.cash != 0:
        rows.append([CASH_KEY, "", "", format_pct(grouped.cash, places), format_pct(Decimal(0), places),
                     format_pct(grouped.cash, places, signed=True)])
        book += grouped.cash
    total = ["Total", str(sum(row.held for row in grouped.rows)), str(sum(row.listed for row in grouped.rows)),
             format_pct(book, places), format_pct(index, places), format_pct(book - index, places, signed=True)]
    lines = header(comparison.valuation) + [
        f"Active weights by {dimension.name} {_against(comparison)}",
        render_table(columns, rows, total),
    ]
    return "\n".join(lines) + "\n"


def render_overlap(comparison: Comparison, result: Overlap, settings: ReportSettings) -> str:
    """Active share, what the book and the index have in common, and the largest bets."""
    places = settings.percent_places + 1
    lines = header(comparison.valuation) + [f"Overlap {_against(comparison)}"]
    lines += _pairs([
        ("Active share", format_pct(result.active_share, places)),
        ("In common", format_pct(result.in_common, places)),
        ("Book", f"{result.held} instruments, {result.common} of them in the index"),
        ("Index", f"{result.listed} constituents, {result.common} of them held"),
    ])
    for title, chosen in (("Largest overweights", result.overweights), ("Largest underweights", result.underweights)):
        lines += ["", title, _lines_table(chosen, places) if chosen else "(none)"]
    return "\n".join(lines) + "\n"


def render_tracking(valuation: Valuation, summary: TrackingSummary, settings: ReportSettings,
                    split: AllocationSplit | None = None) -> str:
    """Relative return and tracking error, optionally followed by the allocation/selection split."""
    places = settings.percent_places + 1

    def signed(value) -> str:
        return format_pct(value, places, signed=True)

    beta = "n/a (the index did not move)" if summary.beta is None else f"{summary.beta:.2f}"
    lines = header(valuation) + [f"Tracking against {summary.code}"]
    lines += _pairs([
        ("Window", f"{summary.start} to {summary.end}, {summary.observations} daily returns"),
        ("Book return", signed(summary.book_return)),
        ("Index return", signed(summary.index_return)),
        ("Relative return", signed(summary.relative_return)),
        ("Tracking error (ann.)", format_pct(summary.tracking_error, places)),
        ("Beta", beta),
        ("Worst relative day", f"{signed(summary.worst_day[1])}  {summary.worst_day[0]}"),
        ("Best relative day", f"{signed(summary.best_day[1])}  {summary.best_day[0]}"),
    ])
    if split is not None:
        lines += [""] + split_lines(split, places)
    return "\n".join(lines) + "\n"


def split_lines(split: AllocationSplit, places: int) -> list[str]:
    """The allocation/selection table and the lines that reconcile it with the relative return.

    The total row's index return is the one rebuilt from the constituents, so
    that its Total column is book return minus index return, as in every row.
    """
    def signed(value) -> str:
        return "" if value is None else format_pct(value, places, signed=True)

    columns = [Column(split.dimension.title)] + [
        Column(title, "right")
        for title in ("Book wt", "Index wt", "Book ret", "Index ret", "Allocation", "Selection", "Total")
    ]
    rows = [
        [row.key, format_pct(row.book_weight, places), format_pct(row.index_weight, places),
         signed(row.book_return), signed(row.index_return), signed(row.allocation), signed(row.selection),
         signed(row.total)]
        for row in split.rows
    ]
    explained = split.allocation + split.selection
    total = ["Total",
             format_pct(sum((row.book_weight for row in split.rows), Decimal(0)), places),
             format_pct(sum((row.index_weight for row in split.rows), Decimal(0)), places),
             signed(split.book_return), signed(split.rebuilt_return),
             signed(split.allocation), signed(split.selection), signed(explained)]
    lines = [f"Relative return by {split.dimension.name}, {split.start} to {split.end}",
             render_table(columns, rows, total), ""]
    lines += _pairs([
        ("Allocation + selection", signed(explained)),
        ("Residual", f"{signed(split.residual)}  (index rebuilt from constituents {signed(split.rebuilt_return)}, "
                     f"levels {signed(split.index_return)}; {format_pct(split.priced_weight, places)} "
                     f"of the index priced)"),
        ("Relative return", signed(split.relative_return)),
    ])
    return lines
