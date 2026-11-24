"""FIFO lot matching, and the realised P&L and income it leads to.

Every buy opens a lot. A sale closes the oldest open lots in its instrument
first (first in, first out), splitting a lot when it needs only part of it.
What is left open afterwards is the inventory that reconcile.py compares
with positions.json.

Costs and proceeds are in the instrument's currency and include fees. A
lot's cost is what the buy paid, fees included; a sale's proceeds are what
it received, fees deducted. A sale that takes part of a lot takes the same
fraction of the lot's cost, so buying fees are spread over the units.
Realised P&L is proceeds less cost.

positions.json values holdings at average cost (domain/positions.py). The two
methods agree for a position that is only bought, or sold in full; they
differ once part of a position bought at several prices is sold.

Realised P&L in the base currency is the local amount at the FX rate of the
sale date: what the gain was worth on the day it was made. The FX move on
the cost between buying and selling is not split out. Income (dividends and
coupons from cash_flows.csv) is converted at the rate of its payment date.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from folio.data.fx_csv import FxRates
from folio.domain.instruments import Instrument, Universe
from folio.domain.money import Money, sum_money
from folio.ledger.book import Ledger
from folio.ledger.cash_flows_csv import INCOME_KINDS
from folio.ledger.trades_csv import Trade


@dataclass(frozen=True)
class OpenLot:
    """What is left of one buy after the sales matched against it."""

    trade_id: str
    trade_date: date
    instrument_id: str
    quantity: Decimal  # still open
    price: Decimal
    cost: Decimal      # of the open quantity, buying fees included, in the instrument's currency


@dataclass(frozen=True)
class Match:
    """The part of a sale closed against one lot."""

    buy_id: str
    buy_date: date
    quantity: Decimal
    cost: Decimal


@dataclass(frozen=True)
class Sale:
    """A sale and the lots it closed, oldest first. Amounts are in the trade currency."""

    trade: Trade
    proceeds: Decimal  # value less selling fees
    matches: tuple[Match, ...]

    @property
    def cost(self) -> Decimal:
        return sum((match.cost for match in self.matches), Decimal(0))

    @property
    def realised(self) -> Decimal:
        return self.proceeds - self.cost


@dataclass(frozen=True)
class FifoResult:
    """What matching leaves open, and every sale with the lots it closed."""

    open_lots: dict[str, tuple[OpenLot, ...]]  # by instrument id, oldest first; closed instruments left out
    sales: tuple[Sale, ...]                    # in trade order


@dataclass
class _Lot:
    trade: Trade
    quantity: Decimal
    cost: Decimal


def match_fifo(trades: Iterable[Trade], universe: Universe) -> FifoResult:
    """Match ``trades``, given in trade order, first in first out within each instrument.

    Raises ValueError for a sale of more than is held; load_ledger() has
    already refused such a file, so this only fires for hand-built trades.
    """
    queues: dict[str, deque[_Lot]] = {}
    sales = []
    for trade in trades:
        value = universe[trade.instrument_id].market_value(trade.quantity, trade.price)
        queue = queues.setdefault(trade.instrument_id, deque())
        if trade.is_buy:
            queue.append(_Lot(trade, trade.quantity, value + trade.fees))
            continue
        held = sum((lot.quantity for lot in queue), Decimal(0))
        if trade.quantity > held:
            raise ValueError(f"trade {trade.trade_id}: the sale of {trade.quantity} {trade.instrument_id} "
                             f"is more than the {held} held")
        sales.append(Sale(trade, value - trade.fees, _close(queue, trade.quantity)))
    open_lots = {
        instrument_id: tuple(OpenLot(lot.trade.trade_id, lot.trade.trade_date, instrument_id,
                                     lot.quantity, lot.trade.price, lot.cost) for lot in queues[instrument_id])
        for instrument_id in sorted(queues)
        if queues[instrument_id]
    }
    return FifoResult(open_lots, tuple(sales))


def _close(queue: deque[_Lot], quantity: Decimal) -> tuple[Match, ...]:
    matches = []
    while quantity > 0:
        lot = queue[0]
        take = min(quantity, lot.quantity)
        # Taking the whole remainder takes the whole remaining cost, so a lot's
        # cost is used up exactly, with no rounding dust left behind.
        cost = lot.cost if take == lot.quantity else lot.cost * take / lot.quantity
        matches.append(Match(lot.trade.trade_id, lot.trade.trade_date, take, cost))
        lot.quantity -= take
        lot.cost -= cost
        quantity -= take
        if lot.quantity == 0:
            queue.popleft()
    return tuple(matches)


@dataclass(frozen=True)
class InstrumentPnl:
    """Realised P&L and income of one instrument over a period."""

    instrument: Instrument
    sold: Decimal  # quantity sold in the period
    proceeds: Money
    cost: Money
    realised_base: Money
    income: Money  # dividends and coupons, in the instrument's currency
    income_base: Money

    @property
    def realised(self) -> Money:
        return self.proceeds - self.cost

    @property
    def total_base(self) -> Money:
        return self.realised_base + self.income_base


@dataclass(frozen=True)
class SectorPnl:
    sector: str
    instruments: int
    realised_base: Money
    income_base: Money

    @property
    def total_base(self) -> Money:
        return self.realised_base + self.income_base


@dataclass
class _Totals:
    sold: Decimal = Decimal(0)
    proceeds: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)
    realised_base: Decimal = Decimal(0)
    income: Decimal = Decimal(0)
    income_base: Decimal = Decimal(0)


def instrument_pnl(ledger: Ledger, result: FifoResult, fx: FxRates, base_currency: str, until: date,
                   since: date | None = None) -> list[InstrumentPnl]:
    """P&L of the sales and income from ``since`` to ``until`` (both included), in instrument id order.

    Only instruments with a sale or income in the period get a line. The
    period picks the sales, not the lots they close: a lot bought before
    ``since`` still counts at its own cost.
    """
    totals: dict[str, _Totals] = {}
    for sale in result.sales:
        day = sale.trade.trade_date
        if (since is not None and day < since) or day > until:
            continue
        line = totals.setdefault(sale.trade.instrument_id, _Totals())
        line.sold += sale.trade.quantity
        line.proceeds += sale.proceeds
        line.cost += sale.cost
        line.realised_base += sale.realised * fx.rate(sale.trade.currency, base_currency, day)
    for flow in ledger.cash_flows_between(since, until):
        if flow.kind in INCOME_KINDS:
            line = totals.setdefault(flow.instrument_id, _Totals())
            line.income += flow.amount.amount
            line.income_base += flow.amount.amount * fx.rate(flow.currency, base_currency, flow.value_date)

    lines = []
    for instrument_id in sorted(totals):
        total, instrument = totals[instrument_id], ledger.universe[instrument_id]
        currency = instrument.currency
        lines.append(InstrumentPnl(
            instrument=instrument,
            sold=total.sold,
            proceeds=Money(total.proceeds, currency),
            cost=Money(total.cost, currency),
            realised_base=Money(total.realised_base, base_currency),
            income=Money(total.income, currency),
            income_base=Money(total.income_base, base_currency),
        ))
    return lines


def sector_pnl(lines: Iterable[InstrumentPnl], base_currency: str) -> list[SectorPnl]:
    """Add up instrument lines by sector, in sector name order."""
    by_sector: dict[str, list[InstrumentPnl]] = {}
    for line in lines:
        by_sector.setdefault(line.instrument.sector, []).append(line)
    return [
        SectorPnl(
            sector=sector,
            instruments=len(by_sector[sector]),
            realised_base=sum_money((line.realised_base for line in by_sector[sector]), base_currency),
            income_base=sum_money((line.income_base for line in by_sector[sector]), base_currency),
        )
        for sector in sorted(by_sector)
    ]
