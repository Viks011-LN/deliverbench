"""Contribution to return by group, for ``folio report --since``.

For every line held on the valuation date we compare its base-currency value
at ``start`` (start price, start FX) with its value now. The change divided by
NAV at ``start`` is its contribution; summed over a group it is the group's
part of the portfolio's return over the period:

    contribution(group) = sum(value_now - value_start) / NAV_start

Holdings are fixed at the valuation date, the same simplification that
returns.nav_series makes, so trades inside the period are ignored. Cash only
moves through FX on non-base balances. It is reported under CASH_KEY, or
under its own currency when the breakdown counts cash as currency exposure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from folio.aggregate.rollup import rollup, share
from folio.calc.valuation import PositionValue, Valuation
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory

CASH_KEY = "Cash"


@dataclass(frozen=True)
class Contribution:
    key: str
    start_weight: Decimal   # group value at start / NAV at start
    contribution: Decimal   # group P&L / NAV at start


class _Line(NamedTuple):
    key: str
    start: Decimal  # base-currency value at the start date
    end: Decimal    # base-currency value at the valuation date


def contributions(
    valuation: Valuation,
    prices: PriceHistory,
    fx: FxRates,
    start: date,
    key: Callable[[PositionValue], str],
    *,
    cash_by_currency: bool = False,
) -> dict[str, Contribution]:
    """Contribution of each group (and of cash) from ``start`` to the valuation date."""
    if start >= valuation.as_of:
        raise ValueError(f"--since {start} must be before the valuation date {valuation.as_of}")
    base = valuation.base_currency

    lines: list[_Line] = []
    for position in valuation.positions:
        point = prices.latest(position.instrument.id, start)
        local = position.instrument.market_value(position.quantity, point.price)
        rate = fx.rate(position.instrument.currency, base, start)
        lines.append(_Line(key(position), local * rate, position.base_value.amount))
    for cash in valuation.cash:
        rate = fx.rate(cash.local_value.currency, base, start)
        label = cash.local_value.currency if cash_by_currency else CASH_KEY
        lines.append(_Line(label, cash.local_value.amount * rate, cash.base_value.amount))

    nav_start = sum((line.start for line in lines), Decimal(0))
    if nav_start <= 0:
        raise ValueError(f"NAV on {start} is not positive; contributions are undefined")
    result = {}
    for group in rollup(lines, key=lambda line: line.key, value=lambda line: line.start):
        pnl = sum((line.end - line.start for line in group.members), Decimal(0))
        result[group.key] = Contribution(group.key, share(group.total, nav_start), share(pnl, nav_start))
    return result


def total_return(parts: dict[str, Contribution]) -> Decimal:
    """Portfolio return over the period: the sum of all contributions."""
    return sum((part.contribution for part in parts.values()), Decimal(0))
