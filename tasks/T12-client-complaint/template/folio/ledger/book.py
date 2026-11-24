"""The ledger of one data folder: trades.csv and cash_flows.csv, checked against the instruments.

Each reader checks its own file. load_ledger() checks what needs
instruments.csv as well, and stops at the first problem:

* every instrument traded, or paying income, is in instruments.csv;
* a trade is in its instrument's currency, and so is a dividend or coupon;
* no sale is larger than what is held at the time. FIFO cannot match it,
  and it nearly always means a buy is missing or was typed as a sale.

Only the ledger commands call this, so a data folder without the two files
still works for everything else in folio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from folio.domain.instruments import Universe
from folio.domain.money import Money
from folio.errors import DataError, FolioError
from folio.ledger.cash_flows_csv import INCOME_KINDS, CashFlow, load_cash_flows
from folio.ledger.trades_csv import Trade, load_trades

FILES = {"trades": "trades.csv", "cash_flows": "cash_flows.csv"}


class LedgerError(FolioError):
    """A ledger command was asked about something the ledger does not have."""


@dataclass(frozen=True)
class Ledger:
    """Trades and cash flows, each in file order, with the instruments they refer to."""

    universe: Universe
    trades: tuple[Trade, ...]
    cash_flows: tuple[CashFlow, ...]

    def gross_value(self, trade: Trade) -> Money:
        """Quantity times price (per 100 nominal for bonds), before fees, in the trade currency."""
        instrument = self.universe[trade.instrument_id]
        return Money(instrument.market_value(trade.quantity, trade.price), trade.currency)

    def settlement(self, trade: Trade) -> Money:
        """The cash a trade moves: a buy pays its value plus fees, a sale receives its value less fees."""
        value = self.gross_value(trade).amount
        return Money(-(value + trade.fees) if trade.is_buy else value - trade.fees, trade.currency)

    def trades_between(self, since: date | None, until: date) -> tuple[Trade, ...]:
        """Trades dated from ``since`` (None: the first) to ``until``, both included."""
        return tuple(trade for trade in self.trades if _within(trade.trade_date, since, until))

    def cash_flows_between(self, since: date | None, until: date) -> tuple[CashFlow, ...]:
        return tuple(flow for flow in self.cash_flows if _within(flow.value_date, since, until))

    def last_date(self) -> date | None:
        """The latest date of any trade or cash flow, or None for an empty ledger."""
        days = [trade.trade_date for trade in self.trades] + [flow.value_date for flow in self.cash_flows]
        return max(days, default=None)


def _within(day: date, since: date | None, until: date) -> bool:
    return (since is None or day >= since) and day <= until


def load_ledger(folder, universe: Universe) -> Ledger:
    """Read both ledger files from ``folder`` and check them against ``universe``."""
    folder = Path(folder)
    absent = [name for name in FILES.values() if not (folder / name).is_file()]
    if absent:
        raise DataError(f"data folder {folder} has no {', '.join(absent)}, which the ledger needs")
    ledger = Ledger(
        universe=universe,
        trades=load_trades(folder / FILES["trades"]),
        cash_flows=load_cash_flows(folder / FILES["cash_flows"]),
    )
    cross_check(ledger)
    return ledger


def cross_check(ledger: Ledger) -> None:
    """Raise DataError, with file and line, for the first trade or cash flow that does not fit."""
    trades_file, flows_file = FILES["trades"], FILES["cash_flows"]
    held: dict[str, Decimal] = {}
    for trade in ledger.trades:
        if trade.instrument_id not in ledger.universe:
            raise DataError(f"trade {trade.trade_id}: {trade.instrument_id} is not in instruments.csv",
                            source=trades_file, line=trade.line)
        expected = ledger.universe[trade.instrument_id].currency
        if trade.currency != expected:
            raise DataError(f"trade {trade.trade_id}: {trade.instrument_id} trades in {expected}, "
                            f"not {trade.currency}", source=trades_file, line=trade.line)
        before = held.get(trade.instrument_id, Decimal(0))
        if not trade.is_buy and trade.quantity > before:
            raise DataError(f"trade {trade.trade_id}: the sale of {trade.quantity} {trade.instrument_id} on "
                            f"{trade.trade_date} is more than the {before} held; short positions are not supported",
                            source=trades_file, line=trade.line)
        held[trade.instrument_id] = before + trade.signed_quantity

    for flow in ledger.cash_flows:
        if not flow.instrument_id:
            continue
        if flow.instrument_id not in ledger.universe:
            raise DataError(f"{flow.instrument_id} is not in instruments.csv", source=flows_file, line=flow.line)
        expected = ledger.universe[flow.instrument_id].currency
        if flow.kind in INCOME_KINDS and flow.currency != expected:
            raise DataError(f"{flow.instrument_id} pays in {expected}, but this {flow.kind} is in {flow.currency}",
                            source=flows_file, line=flow.line)
