"""CSV export of active weights: one row per instrument held or listed, then one per cash balance.

The column list (COLUMNS) belongs to this export alone; it is not the
positions export of folio/report/csv_export.py, and a column added there does
not appear here. Rows come in instrument id order, cash last, so two exports
of different dates can be compared line by line.

Weights are plain fractions with WEIGHT_PLACES decimals and no percent signs,
so a spreadsheet can check them: active = book - index, and the three columns
add up to 1, 1 and 0 (up to rounding). Constituents that only benchmark.csv
describes carry whatever it says about them, blanks included.
"""

from __future__ import annotations

import csv
from typing import TextIO

from folio.benchmark.active import ActiveLine, Comparison
from folio.domain.money import quantize

COLUMNS = (
    "portfolio",
    "as_of",
    "instrument",
    "name",
    "kind",
    "sector",
    "currency",
    "book_weight",
    "index_weight",
    "active_weight",
)

WEIGHT_PLACES = 6


def active_row(comparison: Comparison, line: ActiveLine) -> dict[str, str]:
    """The CSV cells for one line, keyed by column name."""
    valuation = comparison.valuation
    return {
        "portfolio": valuation.portfolio_code,
        "as_of": valuation.as_of.isoformat(),
        "instrument": line.id,
        "name": line.name,
        "kind": line.kind,
        "sector": line.sector,
        "currency": line.currency,
        "book_weight": _plain(line.book),
        "index_weight": _plain(line.index),
        "active_weight": _plain(line.active),
    }


def _plain(weight) -> str:
    rounded = quantize(weight, WEIGHT_PLACES)
    return str(rounded.copy_abs() if rounded == 0 else rounded)  # never "-0.000000"


def write_active_csv(comparison: Comparison, out: TextIO) -> int:
    """Write the header and one row per line to ``out``; return the row count."""
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for line in comparison.every_line:
        writer.writerow(active_row(comparison, line))
    return len(comparison.every_line)
