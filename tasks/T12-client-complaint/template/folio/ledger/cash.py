"""Cash by currency, rebuilt from the trades and cash_flows.csv.

positions.json holds one balance per currency and no history. The ledger has
the history: each trade settles in its own currency on its trade date, and
cash_flows.csv has everything else. A balance is the sum of every movement
up to a date, starting from nothing, so the files have to go back to the
first subscription.

Within one day, cash flows come before trades. A conversion bought for a
purchase is then in the balance before the purchase is paid for, and the
statement does not dip below zero for a moment that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from folio.data.fx_csv import FxRates
from folio.domain.money import Money
from folio.ledger.book import Ledger

# The summary columns of `cash`, and the column of each cash-flow kind.
# Trades go under "trades" at their value and under "fees" for their fees.
GROUPS = ("trades", "income", "fees", "capital", "fx")
KIND_GROUPS = {
    "dividend": "income",
    "coupon": "income",
    "interest": "income",
    "fee": "fees",
    "subscription": "capital",
    "redemption": "capital",
    "fx": "fx",
}


@dataclass(frozen=True)
class Movement:
    """One line of a cash statement."""

    day: date
    amount: Money
    kind: str           # "buy" or "sell" for a trade, otherwise the cash-flow kind
    instrument_id: str  # "" when there is none
    reference: str      # the trade id, or the cash flow's note


@dataclass(frozen=True)
class CurrencySummary:
    """All movements in one currency up to a date, by what they were for."""

    currency: str
    trades: Money   # bought and sold, before fees
    income: Money   # dividends, coupons and interest
    fees: Money     # trade fees and fee rows
    capital: Money  # subscriptions less redemptions
    fx: Money       # conversions in and out
    base_balance: Money

    @property
    def balance(self) -> Money:
        return self.trades + self.income + self.fees + self.capital + self.fx


def movements(ledger: Ledger, until: date, currency: str | None = None) -> list[Movement]:
    """Every movement up to ``until``, optionally in one currency, in statement order."""
    entries: list[tuple[date, int, Movement]] = []
    for flow in ledger.cash_flows_between(None, until):
        if currency is None or flow.currency == currency:
            entries.append((flow.value_date, 0, Movement(flow.value_date, flow.amount, flow.kind,
                                                         flow.instrument_id, flow.note)))
    for trade in ledger.trades_between(None, until):
        if currency is None or trade.currency == currency:
            entries.append((trade.trade_date, 1, Movement(trade.trade_date, ledger.settlement(trade), trade.side,
                                                          trade.instrument_id, trade.trade_id)))
    # Stable sort: within a day and a file, the file order stays.
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    return [movement for _, _, movement in entries]


def balances(ledger: Ledger, until: date) -> dict[str, Money]:
    """Balance per currency on ``until``, in currency order, zero balances included."""
    totals: dict[str, Decimal] = {}
    for movement in movements(ledger, until):
        currency = movement.amount.currency
        totals[currency] = totals.get(currency, Decimal(0)) + movement.amount.amount
    return {currency: Money(totals[currency], currency) for currency in sorted(totals)}


def statement(ledger: Ledger, currency: str, until: date) -> list[tuple[Movement, Money]]:
    """The movements in ``currency`` up to ``until``, each with the balance after it."""
    balance = Money.zero(currency)
    lines = []
    for movement in movements(ledger, until, currency):
        balance = balance + movement.amount
        lines.append((movement, balance))
    return lines


def summarise(ledger: Ledger, until: date, fx: FxRates, base_currency: str) -> list[CurrencySummary]:
    """One summary per currency with any movement up to ``until``, in currency order.

    The base-currency balance uses the FX rate of ``until``.
    """
    groups: dict[str, dict[str, Decimal]] = {}

    def add(currency: str, group: str, amount: Decimal) -> None:
        totals = groups.setdefault(currency, {})
        totals[group] = totals.get(group, Decimal(0)) + amount

    for trade in ledger.trades_between(None, until):
        value = ledger.gross_value(trade).amount
        add(trade.currency, "trades", -value if trade.is_buy else value)
        add(trade.currency, "fees", -trade.fees)
    for flow in ledger.cash_flows_between(None, until):
        add(flow.currency, KIND_GROUPS[flow.kind], flow.amount.amount)

    summaries = []
    for currency in sorted(groups):
        totals = groups[currency]
        amounts = {group: Money(totals.get(group, Decimal(0)), currency) for group in GROUPS}
        balance = sum(totals.values(), Decimal(0))
        base_balance = Money(balance * fx.rate(currency, base_currency, until), base_currency)
        summaries.append(CurrencySummary(currency=currency, base_balance=base_balance, **amounts))
    return summaries
