"""CSV export of a valuation: one row per position.

The column list is fixed (COLUMNS) because the risk team's spreadsheet reads
columns by name; add new ones next to the column they belong with and tell
whoever loads the file. Cash balances are not rows here; the JSON export has
them, and NAV = sum(base_value) + cash.

Numbers are plain (no thousands separators) so that any tool can parse them.

``vol_share`` is the position's share of the portfolio's volatility
(calc.risk.vol_shares), written like ``weight``. It is blank when the caller
passes no shares; ``folio export`` always does.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from typing import TextIO

from folio.calc.risk import VolShares
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
    "vol_share",
    "weight",
)

FX_PLACES = 6
WEIGHT_PLACES = 6


def _fraction(value: Decimal) -> str:
    """A share to WEIGHT_PLACES places; never "-0.000000"."""
    rounded = quantize(value, WEIGHT_PLACES)
    return str(rounded.copy_abs() if rounded == 0 else rounded)


def position_row(valuation: Valuation, line: PositionValue, money_places: int,
                 vol_share: Decimal | None = None) -> dict[str, str]:
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
        "vol_share": "" if vol_share is None else _fraction(vol_share),
        "weight": str(quantize(line.weight, WEIGHT_PLACES)),
    }


def write_csv(valuation: Valuation, out: TextIO, money_places: int = 2, vol_shares: VolShares | None = None) -> int:
    """Write the header and one row per position to ``out``; return the row count."""
    shares = vol_shares.positions if vol_shares is not None else (None,) * len(valuation.positions)
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for line, share in zip(valuation.positions, shares, strict=True):
        writer.writerow(position_row(valuation, line, money_places, share))
    return len(valuation.positions)
