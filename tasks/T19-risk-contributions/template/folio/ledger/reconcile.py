"""Check the ledger against positions.json.

positions.json is what folio values; trades.csv is what was dealt. They are
kept in two places, so they drift apart: a fill booked at the wrong price, a
sale typed into one file and not the other. reconcile() rebuilds the open
lots from the trades with FIFO, does the same with the lots in
positions.json, and reports every difference on the valuation date:

* an instrument open on one side only;
* a different open quantity;
* an open lot (date, quantity, price) on one side only.

Comparing open lots rather than every trade lets trades.csv hold round trips
that positions.json never booked, once they are closed. On a date in the
middle of such a round trip the instrument is reported as open on one side
only, which on that date it was.

Cash is compared too, but only when nothing in the ledger is dated after the
valuation date: positions.json holds today's balances, not a history.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from folio.domain.instruments import Universe
from folio.domain.money import minor_units
from folio.domain.portfolio import Portfolio
from folio.ledger.book import FILES, Ledger
from folio.ledger.cash import balances
from folio.ledger.fifo import OpenLot, match_fifo
from folio.ledger.trades_csv import Trade
from folio.report.tables import format_money, format_quantity

TRADES = FILES["trades"]
POSITIONS = "positions.json"

LotKey = tuple[date, Decimal, Decimal]  # trade date, open quantity, price


@dataclass(frozen=True)
class Difference:
    subject: str  # an instrument id, or "cash" and a currency
    detail: str

    def format(self) -> str:
        return f"DIFF {self.subject}: {self.detail}"


@dataclass(frozen=True)
class Reconciliation:
    as_of: date
    instruments: int        # instruments compared
    currencies: int | None  # cash balances compared, or None when cash was not compared
    differences: tuple[Difference, ...]
    cash_note: str | None = None  # why cash was not compared

    @property
    def ok(self) -> bool:
        return not self.differences

    def summary(self) -> str:
        compared = f"{self.instruments} instruments"
        if self.currencies is not None:
            compared += f" and {self.currencies} cash balances"
        return f"{compared} agree with {POSITIONS} on {self.as_of}"


def reconcile(ledger: Ledger, portfolio: Portfolio, as_of: date) -> Reconciliation:
    """Compare the open lots, and the cash when it can be, of the ledger and ``portfolio`` on ``as_of``."""
    trades = ledger.trades_between(None, as_of)
    booked_trades = booked_as_trades(portfolio, ledger.universe, as_of)
    traded = match_fifo(trades, ledger.universe)
    booked = match_fifo(booked_trades, ledger.universe)
    traded_ids = {trade.instrument_id for trade in trades}
    booked_ids = {trade.instrument_id for trade in booked_trades}
    compared = sorted(traded_ids | booked_ids)

    differences = []
    for instrument_id in compared:
        differences += _compare_lots(instrument_id, traded.open_lots.get(instrument_id, ()),
                                     booked.open_lots.get(instrument_id, ()),
                                     has_trades=instrument_id in traded_ids, has_position=instrument_id in booked_ids)

    last = ledger.last_date()
    if last is not None and last > as_of:
        note = f"cash not compared: {POSITIONS} holds current balances and the ledger runs to {last}"
        return Reconciliation(as_of, len(compared), None, tuple(differences), note)
    ledger_cash = balances(ledger, as_of)
    currencies = sorted(set(ledger_cash) | set(portfolio.cash))
    for currency in currencies:
        ours = ledger_cash[currency].amount if currency in ledger_cash else Decimal(0)
        theirs = portfolio.cash.get(currency, Decimal(0))
        if ours != theirs:
            places = minor_units(currency)
            differences.append(Difference(f"cash {currency}", f"{format_money(ours, places)} in the ledger, "
                                                              f"{format_money(theirs, places)} in {POSITIONS}"))
    return Reconciliation(as_of, len(compared), len(currencies), tuple(differences))


def booked_as_trades(portfolio: Portfolio, universe: Universe, as_of: date) -> list[Trade]:
    """The lots in positions.json up to ``as_of``, as trades without fees, so that FIFO can match them."""
    trades = []
    for instrument_id in sorted(portfolio.positions):
        currency = universe[instrument_id].currency
        for number, lot in enumerate(portfolio.positions[instrument_id].lots_as_of(as_of), 1):
            trades.append(Trade(
                trade_id=f"{instrument_id}/{number}",
                trade_date=lot.trade_date,
                instrument_id=instrument_id,
                side="buy" if lot.is_buy else "sell",
                quantity=abs(lot.quantity),
                price=lot.price,
                currency=currency,
            ))
    return trades


def _compare_lots(instrument_id: str, traded: tuple[OpenLot, ...], booked: tuple[OpenLot, ...], *,
                  has_trades: bool, has_position: bool) -> list[Difference]:
    traded_quantity = sum((lot.quantity for lot in traded), Decimal(0))
    booked_quantity = sum((lot.quantity for lot in booked), Decimal(0))
    if not (has_trades and has_position):
        # Only one side knows the instrument; that is fine once it is closed.
        if has_trades and traded_quantity:
            return [Difference(instrument_id, f"{format_quantity(traded_quantity)} open from {TRADES}, "
                                              f"no position in {POSITIONS}")]
        if has_position and booked_quantity:
            return [Difference(instrument_id, f"{format_quantity(booked_quantity)} open in {POSITIONS}, "
                                              f"no trades in {TRADES}")]
        return []

    differences = []
    if traded_quantity != booked_quantity:
        differences.append(Difference(instrument_id, f"open quantity {format_quantity(traded_quantity)} from "
                                                     f"{TRADES}, {format_quantity(booked_quantity)} in {POSITIONS}"))
    traded_lots, booked_lots = Counter(map(_key, traded)), Counter(map(_key, booked))
    for key in sorted((traded_lots - booked_lots).elements()):
        differences.append(Difference(instrument_id, f"open lot {_describe(key)} in {TRADES} only"))
    for key in sorted((booked_lots - traded_lots).elements()):
        differences.append(Difference(instrument_id, f"open lot {_describe(key)} in {POSITIONS} only"))
    return differences


def _key(lot: OpenLot) -> LotKey:
    return (lot.trade_date, lot.quantity, lot.price)


def _describe(key: LotKey) -> str:
    day, quantity, price = key
    return f"{day} {format_quantity(quantity)} @ {price}"
