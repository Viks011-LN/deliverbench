"""CSV export of the ledger: one row per trade, with the realised P&L of each sale.

The column list (COLUMNS) belongs to this export alone, not to folio's
position export: a row here is a trade, not a holding. Add a new column
next to the column it belongs with, so that the file still reads in order.

``settlement`` is the cash the trade moved, signed like a cash flow. The
last four columns are filled for sales only: the FIFO cost of the lots sold,
the realised P&L in the trade currency, the FX rate of the sale date into
the base currency and the realised P&L at that rate. Amounts are plain
numbers rounded to report.money_places; quantities and prices are written
as they were read.
"""

from __future__ import annotations

import csv
from typing import Sequence, TextIO

from folio.data.fx_csv import FxRates
from folio.domain.money import quantize
from folio.ledger.book import Ledger
from folio.ledger.fifo import Sale, match_fifo
from folio.ledger.trades_csv import Trade

COLUMNS = (
    "portfolio",
    "trade_id",
    "date",
    "instrument",
    "side",
    "quantity",
    "price",
    "currency",
    "fees",
    "settlement",
    "cost",
    "realised",
    "fx_rate",
    "realised_base",
)

FX_PLACES = 6


def trade_row(ledger: Ledger, trade: Trade, sale: Sale | None, fx: FxRates, *, portfolio_code: str,
              base_currency: str, money_places: int) -> dict[str, str]:
    """The CSV cells for one trade; ``sale`` is its FIFO match, None for a buy."""
    def money(amount) -> str:
        return str(quantize(amount, money_places))

    row = {
        "portfolio": portfolio_code,
        "trade_id": trade.trade_id,
        "date": trade.trade_date.isoformat(),
        "instrument": trade.instrument_id,
        "side": trade.side,
        "quantity": str(trade.quantity),
        "price": str(trade.price),
        "currency": trade.currency,
        "fees": money(trade.fees),
        "settlement": money(ledger.settlement(trade).amount),
        "cost": "",
        "realised": "",
        "fx_rate": "",
        "realised_base": "",
    }
    if sale is not None:
        rate = fx.rate(trade.currency, base_currency, trade.trade_date)
        row.update(
            cost=money(sale.cost),
            realised=money(sale.realised),
            fx_rate=str(quantize(rate, FX_PLACES)),
            realised_base=money(sale.realised * rate),
        )
    return row


def write_csv(ledger: Ledger, trades: Sequence[Trade], fx: FxRates, out: TextIO, *, portfolio_code: str,
              base_currency: str, money_places: int = 2) -> int:
    """Write the header and one row per trade in ``trades``; return the row count.

    ``trades`` must be the whole history up to some date, as
    Ledger.trades_between(None, day) gives it, so that every sale finds its lots.
    """
    sales = {sale.trade.trade_id: sale for sale in match_fifo(trades, ledger.universe).sales}
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for trade in trades:
        writer.writerow(trade_row(ledger, trade, sales.get(trade.trade_id), fx, portfolio_code=portfolio_code,
                                  base_currency=base_currency, money_places=money_places))
    return len(trades)
