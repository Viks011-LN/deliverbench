"""CSV export of a proposal's trades, one row per order.

Rows come in the order the report prints them: sells first, then buys,
largest first. The column list (COLUMNS) belongs to this file and is not the
position export's (report/csv_export.py): the two go to different readers,
and a column added to one must not move the other. Numbers are plain, with
no thousands separators, as in the position export.
"""

from __future__ import annotations

import csv
from typing import TextIO

from folio.domain.money import quantize
from folio.rebalance.engine import Proposal, Trade

COLUMNS = (
    "portfolio",
    "as_of",
    "side",
    "instrument",
    "name",
    "kind",
    "currency",
    "quantity",
    "price",
    "local_value",
    "fx_rate",
    "base_value",
    "weight_before",
    "weight_after",
    "target_scope",
    "target",
)

FX_PLACES = 6
WEIGHT_PLACES = 6


def trade_row(proposal: Proposal, trade: Trade, money_places: int) -> dict[str, str]:
    """The CSV cells for one trade, keyed by column name."""
    instrument = trade.instrument
    return {
        "portfolio": proposal.valuation.portfolio_code,
        "as_of": proposal.valuation.as_of.isoformat(),
        "side": trade.side,
        "instrument": instrument.id,
        "name": instrument.name,
        "kind": instrument.kind,
        "currency": instrument.currency,
        "quantity": str(trade.quantity),
        "price": str(trade.price),
        "local_value": str(quantize(trade.local_value.amount, money_places)),
        "fx_rate": str(quantize(trade.fx_rate, FX_PLACES)),
        "base_value": str(quantize(trade.base_value.amount, money_places)),
        "weight_before": str(quantize(trade.weight_before, WEIGHT_PLACES)),
        "weight_after": str(quantize(trade.weight_after, WEIGHT_PLACES)),
        "target_scope": trade.target.scope,
        "target": trade.target.key,
    }


def write_trades(proposal: Proposal, out: TextIO, money_places: int = 2) -> int:
    """Write the header and one row per trade to ``out``; return the row count."""
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for trade in proposal.trades:
        writer.writerow(trade_row(proposal, trade, money_places))
    return len(proposal.trades)
