"""What a proposal does to cash and to the weights.

Cash moves in the currency of each trade: selling a USD bond adds USD,
buying a JPY share takes JPY. cash_moves() gives each currency's balance
before and after the trades. The cash buffer is checked on the total in the
base currency, so one currency can still end below zero; that balance has to
be bought with another currency before the trades settle, and the report
says so rather than inventing the FX trade itself.

weights_after() applies the trades to the book at the same prices and rates,
and the targets are measured again on the result, so the report can show a
target that is still outside its band (a trade left out for its size, or
lots that round the wrong way).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from folio.domain.money import Money, sum_money
from folio.rebalance.drift import Drift, Holding, measure_drift
from folio.rebalance.engine import BUY, SELL, Proposal


@dataclass(frozen=True)
class CashMove:
    """One currency's cash before and after the trades."""

    currency: str
    fx_rate: Decimal  # base currency per unit, on the valuation date
    before: Money
    sold: Money       # proceeds of the sells in this currency
    bought: Money     # cost of the buys in this currency

    @property
    def after(self) -> Money:
        return self.before + self.sold - self.bought

    @property
    def is_short(self) -> bool:
        return self.after.amount < 0


@dataclass(frozen=True)
class Effect:
    """The book after the proposal: cash by currency, holdings and every target."""

    base_currency: str
    nav: Money
    cash: tuple[CashMove, ...]   # in currency order
    holdings: tuple[Holding, ...]  # weights after, in instrument id order
    after: tuple[Drift, ...]

    @property
    def cash_after(self) -> Money:
        return _in_base(self.cash, self.base_currency)

    @property
    def cash_weight(self) -> Decimal:
        return self.cash_after.amount / self.nav.amount

    @property
    def short_currencies(self) -> list[str]:
        return [move.currency for move in self.cash if move.is_short]


def cash_moves(proposal: Proposal) -> tuple[CashMove, ...]:
    """Each currency with a balance or a trade, in currency order."""
    rates: dict[str, Decimal] = {}
    before: dict[str, Decimal] = {}
    flows: dict[str, dict[str, Decimal]] = {}
    for line in proposal.valuation.cash:
        currency = line.local_value.currency
        rates[currency] = line.fx_rate
        before[currency] = line.local_value.amount
    for trade in proposal.trades:
        currency = trade.instrument.currency
        rates.setdefault(currency, trade.fx_rate)
        side = flows.setdefault(currency, {SELL: Decimal(0), BUY: Decimal(0)})
        side[trade.side] += trade.local_value.amount
    moves = []
    for currency in sorted(rates):
        flow = flows.get(currency, {SELL: Decimal(0), BUY: Decimal(0)})
        moves.append(CashMove(currency, rates[currency], Money(before.get(currency, Decimal(0)), currency),
                              Money(flow[SELL], currency), Money(flow[BUY], currency)))
    return tuple(moves)


def weights_after(proposal: Proposal) -> tuple[Holding, ...]:
    """Every instrument held after the trades with its weight, in id order.

    NAV does not change (trades at the valuation's prices, no costs), so the
    weights are over the same NAV. A holding sold out drops off the list.
    """
    nav = proposal.valuation.nav.amount
    values = {line.instrument.id: (line.instrument, line.base_value.amount) for line in proposal.valuation.positions}
    for trade in proposal.trades:
        instrument, value = values.get(trade.instrument.id, (trade.instrument, Decimal(0)))
        change = trade.base_value.amount if trade.side == BUY else -trade.base_value.amount
        values[trade.instrument.id] = (instrument, value + change)
    return tuple((instrument, value / nav) for instrument_id, (instrument, value) in sorted(values.items())
                 if value != 0)


def effect_of(proposal: Proposal) -> Effect:
    """Cash, holdings and drift after ``proposal``'s trades."""
    valuation = proposal.valuation
    cash = cash_moves(proposal)
    holdings = weights_after(proposal)
    cash_weight = _in_base(cash, valuation.base_currency).amount / valuation.nav.amount
    after = measure_drift(proposal.targets, holdings, cash_weight)
    return Effect(valuation.base_currency, valuation.nav, cash, holdings, after)


def _in_base(moves: tuple[CashMove, ...], base: str) -> Money:
    """The balances after the trades, converted and added up in ``base``."""
    return sum_money((Money(move.after.amount * move.fx_rate, base) for move in moves), base)
