"""The rebalancing proposal: the trades that bring the book back to its model.

propose() follows the desk's rules, in this order:

1. Only targets outside their band trade, and they trade all the way back to
   the model weight, not just back inside the band. A target inside its band
   is left alone, however close to the edge.
2. An instrument target trades that instrument; it may buy one the book does
   not hold yet. A sector target is spread over the sector's holdings in
   proportion to their current weights, so the mix inside the sector stays
   as it is. It never buys a name the book does not already hold.
3. Each trade is rounded to the nearest round lot. A model weight of zero
   sells the whole holding, odd lot and all.
4. Trades worth less than the minimum ticket are left out.
5. Cash must not end below the buffer. Sells come first and pay for the
   buys; when cash would end below the buffer, every buy is cut back by the
   same factor and rounded down to whole lots, and a buy that no longer
   clears the minimum ticket is left out too. Nothing extra is sold to raise
   cash: a book that starts below its buffer simply gets no buys.

Trades are valued at the valuation's prices and rates and costs are not
modelled, so NAV is the same before and after. Every trade left out is kept
in Proposal.skipped with its reason, so the report can say why a target that
was outside its band is still outside after the trades.

The cash target is never traded: cash is what the trades leave behind, and
effect.py reports it against its model weight like any other target.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import NamedTuple

from folio.calc.valuation import PositionValue, Valuation
from folio.domain.instruments import Instrument
from folio.domain.money import Money
from folio.errors import DataError
from folio.rebalance.dealing import DealingRules
from folio.rebalance.drift import Drift, cash_weight_of, holdings_of, measure_drift
from folio.rebalance.sizing import Quote, Quotes, quantity_for
from folio.rebalance.targets import INSTRUMENT, Target, TargetSet

SELL, BUY = "sell", "buy"

# Why a trade was left out; the text report prints these as they are.
UNDER_LOT = "less than one round lot"
UNDER_TICKET = "under the minimum ticket"
CUT_TO_NOTHING = "cut to less than one round lot to keep the cash buffer"
CUT_UNDER_TICKET = "under the minimum ticket once cut to keep the cash buffer"


@dataclass(frozen=True)
class Trade:
    """One proposed order, valued at the quote it was sized with."""

    target: Target
    instrument: Instrument
    side: str                 # SELL or BUY
    quantity: Decimal         # always positive; units, or nominal for bonds
    price: Decimal
    fx_rate: Decimal
    local_value: Money
    base_value: Money
    weight_before: Decimal
    weight_after: Decimal


@dataclass(frozen=True)
class Skipped:
    """A trade the targets asked for that the dealing rules left out."""

    target: Target
    instrument: Instrument
    side: str
    quantity: Decimal   # after rounding to lots; 0 when it rounded away
    base_value: Money   # of the rounded trade, or of what was asked for when it rounded away
    reason: str


@dataclass(frozen=True)
class Proposal:
    """What propose() decided: the trades, what it left out and the drift it started from."""

    valuation: Valuation
    targets: TargetSet
    rules: DealingRules
    before: tuple[Drift, ...]
    trades: tuple[Trade, ...]         # sells first, then buys; largest first within each
    skipped: tuple[Skipped, ...]      # in instrument id order
    buy_scale: Decimal | None = None  # set when buys were cut back to keep the cash buffer

    @property
    def sells(self) -> tuple[Trade, ...]:
        return tuple(trade for trade in self.trades if trade.side == SELL)

    @property
    def buys(self) -> tuple[Trade, ...]:
        return tuple(trade for trade in self.trades if trade.side == BUY)

    def total(self, side: str) -> Money:
        amount = sum((trade.base_value.amount for trade in self.trades if trade.side == side), Decimal(0))
        return Money(amount, self.valuation.base_currency)

    @property
    def traded_share(self) -> Decimal:
        """Sells plus buys, as a share of NAV."""
        return (self.total(SELL).amount + self.total(BUY).amount) / self.valuation.nav.amount


class _Order(NamedTuple):
    """A trade being sized, with what the holding is worth now."""

    target: Target
    quote: Quote
    side: str
    quantity: Decimal    # positive, in whole lots (or the whole holding)
    held_value: Decimal  # base currency
    wanted: Decimal      # base-currency value the target asked for, before rounding
    lot: Decimal

    @property
    def value(self) -> Decimal:
        return self.quote.base_value(self.quantity)


def propose(valuation: Valuation, targets: TargetSet, rules: DealingRules, quotes: Quotes) -> Proposal:
    """Propose trades for every target outside its band; see the module docstring for the rules."""
    nav, base = valuation.nav.amount, valuation.base_currency
    before = measure_drift(targets, holdings_of(valuation), cash_weight_of(valuation))
    held = {line.instrument.id: line for line in valuation.positions}
    skipped: list[Skipped] = []
    orders: list[_Order] = []
    for drift in before:
        if drift.target.is_cash or not drift.outside:
            continue
        for instrument_id, goal in _goals(drift, held, targets.source):
            order = _size(drift.target, quotes.quote(instrument_id), goal * nav, held.get(instrument_id), rules)
            if order.quantity == 0:
                skipped.append(_skip(order, order.wanted, UNDER_LOT, base))
            elif order.value < rules.min_ticket.amount:
                skipped.append(_skip(order, order.value, UNDER_TICKET, base))
            else:
                orders.append(order)

    sells = [order for order in orders if order.side == SELL]
    buys = [order for order in orders if order.side == BUY]
    room = valuation.cash_total.amount + sum((order.value for order in sells), Decimal(0)) - rules.cash_buffer * nav
    bought = sum((order.value for order in buys), Decimal(0))
    scale = None
    if buys and bought > room:
        scale = max(room, Decimal(0)) / bought
        buys = _cut(buys, scale, rules, base, skipped)

    trades = tuple(_trade(order, nav, base) for order in _largest_first(sells) + _largest_first(buys))
    skipped.sort(key=lambda item: (item.instrument.id, item.target.label))
    return Proposal(valuation, targets, rules, before, trades, tuple(skipped), scale)


def _goals(drift: Drift, held: dict[str, PositionValue], source: str) -> list[tuple[str, Decimal]]:
    """(instrument id, weight to reach) for each instrument that ``drift``'s target trades."""
    target = drift.target
    if target.scope == INSTRUMENT:
        return [(target.key, target.weight)]
    if drift.current == 0:
        raise DataError(f"sector {target.key} has a model weight of {target.weight} but the book holds nothing "
                        f"in it; give its instruments targets of their own", source=source, line=target.line)
    return [(member, target.weight * held[member].weight / drift.current) for member in drift.members]


def _size(target: Target, quote: Quote, goal_value: Decimal, line: PositionValue | None,
          rules: DealingRules) -> _Order:
    held_quantity = line.quantity if line is not None else Decimal(0)
    held_value = line.base_value.amount if line is not None else Decimal(0)
    lot = rules.lot_for(quote.instrument)
    wanted = goal_value - held_value
    if goal_value == 0:
        quantity = -held_quantity  # sell out, whatever the lot
    else:
        quantity = max(quantity_for(wanted, quote, lot), -held_quantity)
    return _Order(target, quote, BUY if wanted > 0 else SELL, abs(quantity), held_value, abs(wanted), lot)


def _cut(buys: list[_Order], scale: Decimal, rules: DealingRules, base: str,
         skipped: list[Skipped]) -> list[_Order]:
    """Shrink every buy by ``scale``, rounding down to lots; return those still worth dealing."""
    kept = []
    for order in buys:
        target_value = order.value * scale
        cut = order._replace(quantity=quantity_for(target_value, order.quote, order.lot, rounding=ROUND_DOWN))
        if cut.quantity == 0:
            skipped.append(_skip(cut, target_value, CUT_TO_NOTHING, base))
        elif cut.value < rules.min_ticket.amount:
            skipped.append(_skip(cut, cut.value, CUT_UNDER_TICKET, base))
        else:
            kept.append(cut)
    return kept


def _largest_first(orders: list[_Order]) -> list[_Order]:
    return sorted(orders, key=lambda order: (-order.value, order.quote.instrument.id))


def _skip(order: _Order, value: Decimal, reason: str, base: str) -> Skipped:
    return Skipped(order.target, order.quote.instrument, order.side, order.quantity, Money(value, base), reason)


def _trade(order: _Order, nav: Decimal, base: str) -> Trade:
    value = order.value
    after = order.held_value + value if order.side == BUY else order.held_value - value
    return Trade(
        target=order.target,
        instrument=order.quote.instrument,
        side=order.side,
        quantity=order.quantity,
        price=order.quote.price,
        fx_rate=order.quote.fx_rate,
        local_value=order.quote.local_value(order.quantity),
        base_value=Money(value, base),
        weight_before=order.held_value / nav,
        weight_after=after / nav,
    )
