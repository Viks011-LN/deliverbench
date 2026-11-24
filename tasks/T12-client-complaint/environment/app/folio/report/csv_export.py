"""CSV export of a valuation: one row per position.

The column list is fixed (COLUMNS) because the risk team's spreadsheet reads
columns by name; add new ones next to the column they belong with and tell
whoever loads the file. Cash balances are not rows here; the JSON export has
them, and NAV = sum(base_value) + cash.

Numbers are plain (no thousands separators) so that any tool can parse them.
"""

from __future__ import annotations

import csv
from typing import TextIO

from folio.calc.valuation import PositionValue, Valuation
from folio.domain.money import quantize

COLUMNS = (
    "portfolio",
    "as_of",
    "instrument",
    "name",
    "kind",
    "sector",
    "currency",
    "quantity",
    "price",
    "price_date",
    "local_value",
    "fx_rate",
    "base_value",
    "weight",
)

FX_PLACES = 6
WEIGHT_PLACES = 6


def position_row(valuation: Valuation, line: PositionValue, money_places: int) -> dict[str, str]:
    """The CSV cells for one position, keyed by column name."""
    instrument = line.instrument
    return {
        "portfolio": valuation.portfolio_code,
        "as_of": valuation.as_of.isoformat(),
        "instrument": instrument.id,
        "name": instrument.name,
        "kind": instrument.kind,
        "sector": instrument.sector,
        "currency": instrument.currency,
        "quantity": str(line.quantity),
        "price": str(line.price),
        "price_date": line.price_date.isoformat(),
        "local_value": str(quantize(line.local_value.amount, money_places)),
        "fx_rate": str(quantize(line.fx_rate, FX_PLACES)),
        "base_value": str(quantize(line.base_value.amount, money_places)),
        "weight": str(quantize(line.weight, WEIGHT_PLACES)),
    }


def write_csv(valuation: Valuation, out: TextIO, money_places: int = 2) -> int:
    """Write the header and one row per position to ``out``; return the row count."""
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for line in valuation.positions:
        writer.writerow(position_row(valuation, line, money_places))
    return len(valuation.positions)
