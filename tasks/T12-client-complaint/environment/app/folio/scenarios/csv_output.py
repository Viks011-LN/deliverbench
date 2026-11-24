"""CSV export of scenario results: one row per holding per scenario.

The column list (COLUMNS) is its own, separate from report/csv_export.py:
the positions export feeds the risk team's spreadsheet and must not change
shape when a column is added here. Cash balances get a row each (instrument
CASH, kind cash), so that a scenario's pnl column adds up to its total P&L.
Rows come scenario by scenario in name order, then positions by instrument
id, then cash by currency.

Numbers are plain, without thousands separators. Changes and shares are
fractions (-0.2 is a 20% fall), like the weights in the positions export.
window_start and window_end are filled for historical scenarios only.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from typing import Sequence, TextIO

from folio.domain.money import quantize
from folio.scenarios.engine import ScenarioResult, StressedCash, StressedPosition

COLUMNS = (
    "scenario",
    "portfolio",
    "as_of",
    "instrument",
    "name",
    "kind",
    "sector",
    "currency",
    "base_value",
    "price_change",
    "fx_change",
    "stressed_value",
    "pnl",
    "pnl_share",
    "window_start",
    "window_end",
)

CHANGE_PLACES = 6
CASH_ID = "CASH"
CASH_KIND = "cash"


def _common(result: ScenarioResult) -> dict[str, str]:
    return {
        "scenario": result.scenario.name,
        "portfolio": result.valuation.portfolio_code,
        "as_of": result.valuation.as_of.isoformat(),
    }


def position_row(result: ScenarioResult, line: StressedPosition, money_places: int) -> dict[str, str]:
    """The CSV cells for one stressed position, keyed by column name."""
    instrument = line.line.instrument
    return {
        **_common(result),
        "instrument": instrument.id,
        "name": instrument.name,
        "kind": instrument.kind,
        "sector": instrument.sector,
        "currency": instrument.currency,
        "base_value": str(quantize(line.line.base_value.amount, money_places)),
        "price_change": str(quantize(line.price_change, CHANGE_PLACES)),
        "fx_change": str(quantize(line.fx_change, CHANGE_PLACES)),
        "stressed_value": str(quantize(line.stressed_value.amount, money_places)),
        "pnl": str(quantize(line.pnl.amount, money_places)),
        "pnl_share": str(quantize(line.pnl.amount / result.valuation.nav.amount, CHANGE_PLACES)),
        "window_start": "" if line.window is None else line.window.start.isoformat(),
        "window_end": "" if line.window is None else line.window.end.isoformat(),
    }


def cash_row(result: ScenarioResult, cash: StressedCash, money_places: int) -> dict[str, str]:
    """The CSV cells for one cash balance; it has no price, so only FX moves it."""
    return {
        **_common(result),
        "instrument": CASH_ID,
        "name": f"Cash {cash.currency}",
        "kind": CASH_KIND,
        "sector": "",
        "currency": cash.currency,
        "base_value": str(quantize(cash.cash.base_value.amount, money_places)),
        "price_change": str(quantize(Decimal(0), CHANGE_PLACES)),
        "fx_change": str(quantize(cash.fx_change, CHANGE_PLACES)),
        "stressed_value": str(quantize(cash.stressed_value.amount, money_places)),
        "pnl": str(quantize(cash.pnl.amount, money_places)),
        "pnl_share": str(quantize(cash.pnl.amount / result.valuation.nav.amount, CHANGE_PLACES)),
        # Only a whole-book replay moves currencies, and it does so over its one window.
        "window_start": "" if result.window is None else result.window.start.isoformat(),
        "window_end": "" if result.window is None else result.window.end.isoformat(),
    }


def write_csv(results: Sequence[ScenarioResult], out: TextIO, money_places: int = 2) -> int:
    """Write the header and the rows of every result, scenarios in name order; return the row count."""
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    count = 0
    for result in sorted(results, key=lambda result: result.scenario.name):
        for line in result.positions:
            writer.writerow(position_row(result, line, money_places))
        for cash in result.cash:
            writer.writerow(cash_row(result, cash, money_places))
        count += len(result.positions) + len(result.cash)
    return count
