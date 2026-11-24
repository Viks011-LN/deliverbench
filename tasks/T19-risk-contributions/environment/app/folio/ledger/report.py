"""Text output for the ledger commands.

As in folio's report/text_report.py, each renderer returns one string and
only formats: the numbers come from fifo.py and cash.py. Amounts in the
base currency get report.money_places decimals; amounts in a trade's own
currency get no more decimals than that currency has, so yen show none.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from folio.domain.money import Money, minor_units, sum_money
from folio.domain.portfolio import Portfolio
from folio.ledger.book import Ledger
from folio.ledger.cash import CurrencySummary, Movement
from folio.ledger.fifo import InstrumentPnl, SectorPnl
from folio.ledger.trades_csv import Trade
from folio.report.tables import Column, clip, format_money, format_quantity, render_table

REFERENCE_WIDTH = 36


def header(portfolio: Portfolio, title: str) -> list[str]:
    return [f"{portfolio.name} ({portfolio.code})", title, ""]


def period(since: date | None, until: date) -> str:
    return f"from {since} to {until}" if since is not None else f"up to {until}"


def _local(amount: Money, places: int) -> str:
    return format_money(amount.amount, min(places, minor_units(amount.currency)))


def _finish(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def render_trades(ledger: Ledger, portfolio: Portfolio, trades: Sequence[Trade], title: str, places: int) -> str:
    """One row per trade, in trade order, with the cash each one settled."""
    if not trades:
        return _finish(header(portfolio, title) + ["No trades."])
    columns = [
        Column("Date"),
        Column("Trade"),
        Column("Instrument"),
        Column("Side"),
        Column("Quantity", "right"),
        Column("Price", "right"),
        Column("Ccy"),
        Column("Fees", "right"),
        Column("Settlement", "right"),
    ]
    rows = [
        [trade.trade_date.isoformat(), trade.trade_id, trade.instrument_id, trade.side,
         format_quantity(trade.quantity), str(trade.price), trade.currency,
         _local(Money(trade.fees, trade.currency), places), _local(ledger.settlement(trade), places)]
        for trade in trades
    ]
    sales = sum(1 for trade in trades if not trade.is_buy)
    summary = f"{len(trades)} trades: {len(trades) - sales} buys, {sales} sales"
    return _finish(header(portfolio, title) + [render_table(columns, rows), "", summary])


def render_instrument_pnl(portfolio: Portfolio, lines: Sequence[InstrumentPnl], title: str, base_currency: str,
                          places: int) -> str:
    """Realised P&L in the instrument's currency and in base, and income in base, per instrument."""
    if not lines:
        return _finish(header(portfolio, title) + ["No sales and no income in the period."])
    columns = [
        Column("Instrument"),
        Column("Ccy"),
        Column("Sold", "right"),
        Column("Proceeds", "right"),
        Column("Cost", "right"),
        Column("Realised", "right"),
        Column(f"Realised {base_currency}", "right"),
        Column(f"Income {base_currency}", "right"),
        Column(f"Total {base_currency}", "right"),
    ]
    rows = []
    for line in lines:
        local = ["", "", "", ""]
        if line.sold:
            local = [format_quantity(line.sold), _local(line.proceeds, places), _local(line.cost, places),
                     _local(line.realised, places)]
        rows.append([line.instrument.id, line.instrument.currency] + local + [
            format_money(line.realised_base.amount, places),
            format_money(line.income_base.amount, places),
            format_money(line.total_base.amount, places),
        ])
    total = ["Total", "", "", "", "", ""] + _base_totals(lines, base_currency, places)
    return _finish(header(portfolio, title) + [render_table(columns, rows, total)])


def render_sector_pnl(portfolio: Portfolio, sectors: Sequence[SectorPnl], title: str, base_currency: str,
                      places: int) -> str:
    if not sectors:
        return _finish(header(portfolio, title) + ["No sales and no income in the period."])
    columns = [
        Column("Sector"),
        Column("Instruments", "right"),
        Column(f"Realised {base_currency}", "right"),
        Column(f"Income {base_currency}", "right"),
        Column(f"Total {base_currency}", "right"),
    ]
    rows = [
        [sector.sector, str(sector.instruments), format_money(sector.realised_base.amount, places),
         format_money(sector.income_base.amount, places), format_money(sector.total_base.amount, places)]
        for sector in sectors
    ]
    total = ["Total", str(sum(sector.instruments for sector in sectors))]
    total += _base_totals(sectors, base_currency, places)
    return _finish(header(portfolio, title) + [render_table(columns, rows, total)])


def _base_totals(lines: Sequence[InstrumentPnl | SectorPnl], base_currency: str, places: int) -> list[str]:
    realised = sum_money((line.realised_base for line in lines), base_currency)
    income = sum_money((line.income_base for line in lines), base_currency)
    return [format_money(amount.amount, places) for amount in (realised, income, realised + income)]


def render_cash(portfolio: Portfolio, summaries: Sequence[CurrencySummary], title: str, base_currency: str,
                places: int) -> str:
    """One row per currency: what moved the balance, the balance, and the balance in base."""
    if not summaries:
        return _finish(header(portfolio, title) + ["No cash movements."])
    columns = [Column("Ccy")] + [Column(name, "right") for name in ("Trades", "Income", "Fees", "Capital", "FX")]
    columns += [Column("Balance", "right"), Column(f"Balance {base_currency}", "right")]
    rows = [
        [summary.currency] + [_local(amount, places) for amount in (
            summary.trades, summary.income, summary.fees, summary.capital, summary.fx, summary.balance)]
        + [format_money(summary.base_balance.amount, places)]
        for summary in summaries
    ]
    total_base = sum_money((summary.base_balance for summary in summaries), base_currency)
    total = ["Total", "", "", "", "", "", "", format_money(total_base.amount, places)]
    return _finish(header(portfolio, title) + [render_table(columns, rows, total)])


def render_statement(portfolio: Portfolio, currency: str, entries: Sequence[tuple[Movement, Money]], title: str,
                     places: int) -> str:
    """Every movement in one currency with the running balance after it."""
    if not entries:
        return _finish(header(portfolio, title) + [f"No {currency} cash movements."])
    columns = [
        Column("Date"),
        Column("Kind"),
        Column("Instrument"),
        Column("Reference"),
        Column("Amount", "right"),
        Column("Balance", "right"),
    ]
    rows = [
        [movement.day.isoformat(), movement.kind, movement.instrument_id,
         clip(movement.reference, REFERENCE_WIDTH), _local(movement.amount, places), _local(balance, places)]
        for movement, balance in entries
    ]
    return _finish(header(portfolio, title) + [render_table(columns, rows)])
