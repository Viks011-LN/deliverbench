"""Volatility, historical VaR and expected shortfall.

Everything is computed on the NAV series from returns.nav_series (current
holdings at historical prices). VaR and ES are positive numbers: the loss as
a fraction of NAV, and the same loss as an amount in the base currency.

Historical VaR at confidence c is the (1 - c) quantile of the daily returns
in the lookback window, with the sign flipped, scaled by sqrt(horizon) for
horizons longer than a day. The square-root rule assumes independent days;
it is the desk convention, not a view about markets.

tail_losses() splits the expected shortfall by group (sector, currency...),
to show where the worst days' losses came from. vol_shares() splits the
volatility by line, with the Euler allocation over the daily P&L shares
(docs/risk-notes.md).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from folio.aggregate.attribution import CASH_KEY
from folio.aggregate.rollup import Group, rollup
from folio.calc.returns import (
    Drawdown,
    Series,
    annualise,
    cumulative_return,
    daily_pnl_shares,
    history_dates,
    line_values,
    log_returns,
    max_drawdown,
    simple_returns,
)
from folio.calc.valuation import PositionValue, Valuation
from folio.config.settings import RiskSettings
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory
from folio.domain.money import Money, to_decimal
from folio.errors import RiskError


def percentile(values: Sequence[float], q: float) -> float:
    """The q-quantile of ``values`` with linear interpolation between ranks.

    Same as Excel's PERCENTILE.INC and numpy's default method, so figures can
    be checked by hand in a spreadsheet.
    """
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"quantile must be between 0 and 1, got {q}")
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _check_confidence(confidence: float) -> None:
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")


def confidence_label(confidence: float) -> str:
    """``0.99`` -> ``'99%'``, ``0.975`` -> ``'97.5%'``."""
    return f"{round(confidence * 100, 4):g}%"


def historical_var(returns: Sequence[float], confidence: float, horizon_days: int = 1) -> float:
    """Loss not exceeded with probability ``confidence``, as a positive fraction."""
    _check_confidence(confidence)
    cutoff = percentile(returns, 1.0 - confidence)
    return max(-cutoff, 0.0) * math.sqrt(horizon_days)


def expected_shortfall(returns: Sequence[float], confidence: float, horizon_days: int = 1) -> float:
    """Average loss on the days at or beyond the VaR cutoff, as a positive fraction."""
    _check_confidence(confidence)
    cutoff = percentile(returns, 1.0 - confidence)
    tail = [value for value in returns if value <= cutoff]
    return max(-statistics.fmean(tail), 0.0) * math.sqrt(horizon_days)


def annualised_volatility(returns: Sequence[float], periods_per_year: int) -> float:
    if len(returns) < 2:
        raise ValueError("volatility needs at least two returns")
    return statistics.stdev(returns) * math.sqrt(periods_per_year)


@dataclass(frozen=True)
class RiskSummary:
    """Everything ``folio risk`` prints. Fractions are of NAV; losses are positive."""

    start: date               # first NAV date in the window
    end: date
    observations: int         # daily returns in the window
    confidence: float
    horizon_days: int
    volatility: float         # annualised, from log returns
    var: float
    var_amount: Money
    expected_shortfall: float
    es_amount: Money
    period_return: float
    annualised_return: float
    drawdown: Drawdown | None
    worst_day: tuple[date, float]
    best_day: tuple[date, float]
    returns: tuple[float, ...]  # the window's simple returns, oldest first


def summarise_risk(series: Series, nav: Money, settings: RiskSettings) -> RiskSummary:
    """Risk figures for the last ``settings.var_lookback_days`` daily returns of ``series``."""
    dated = simple_returns(series)[-settings.var_lookback_days:]
    if len(dated) < settings.min_observations:
        raise RiskError(
            f"only {len(dated)} daily returns available, risk.min_observations is {settings.min_observations}; "
            f"load more price history or lower the setting"
        )
    window = series[-(len(dated) + 1):]
    values = [value for _, value in dated]
    logs = [value for _, value in log_returns(window)]

    var = historical_var(values, settings.var_confidence, settings.horizon_days)
    es = expected_shortfall(values, settings.var_confidence, settings.horizon_days)
    # Ties go to the earliest day, so the output does not depend on sort stability.
    worst = min(dated, key=lambda item: (item[1], item[0]))
    best = max(dated, key=lambda item: (item[1], -item[0].toordinal()))
    return RiskSummary(
        start=window[0][0],
        end=window[-1][0],
        observations=len(dated),
        confidence=settings.var_confidence,
        horizon_days=settings.horizon_days,
        volatility=annualised_volatility(logs, settings.annualisation_days),
        var=var,
        var_amount=Money(nav.amount * to_decimal(var), nav.currency),
        expected_shortfall=es,
        es_amount=Money(nav.amount * to_decimal(es), nav.currency),
        period_return=cumulative_return(values),
        annualised_return=annualise(cumulative_return(values), len(values), settings.annualisation_days),
        drawdown=max_drawdown(window),
        worst_day=worst,
        best_day=best,
        returns=tuple(values),
    )


@dataclass(frozen=True)
class TailLoss:
    key: str
    loss: float   # average loss on the tail days, as a fraction of NAV; negative if the group gained
    share: float  # of the total tail loss


def tail_losses(
    valuation: Valuation,
    prices: PriceHistory,
    fx: FxRates,
    settings: RiskSettings,
    key: Callable[[PositionValue], str],
    *,
    cash_by_currency: bool = False,
) -> list[TailLoss]:
    """Expected shortfall split by group, largest loss first.

    Takes the days in the lookback window whose return is at or below the VaR
    cutoff (the days expected shortfall averages over) and averages each
    group's P&L on them as a fraction of the previous day's NAV. The groups
    add up to the one-day expected shortfall. Cash is grouped under CASH_KEY,
    or under its currency when ``cash_by_currency`` is set.
    """
    days = history_dates(valuation, prices)
    values = [line_values(valuation, prices, fx, day) for day in days]
    navs = [sum(row, Decimal(0)) for row in values]
    window = range(max(1, len(days) - settings.var_lookback_days), len(days))
    if len(window) < settings.min_observations:
        raise RiskError(f"only {len(window)} daily returns available, risk.min_observations is "
                        f"{settings.min_observations}")
    returns = {t: float(navs[t] / navs[t - 1] - 1) for t in window}
    cutoff = percentile(list(returns.values()), 1.0 - settings.var_confidence)
    tail = [t for t in window if returns[t] <= cutoff]

    labels = [key(line) for line in valuation.positions]
    labels += [cash.local_value.currency if cash_by_currency else CASH_KEY for cash in valuation.cash]
    losses = []
    for index, label in enumerate(labels):
        pnl = sum(((values[t][index] - values[t - 1][index]) / navs[t - 1] for t in tail), Decimal(0))
        losses.append((label, -pnl / len(tail)))
    groups = rollup(losses, key=lambda item: item[0], value=lambda item: item[1])
    total = sum((group.total for group in groups), Decimal(0))
    return [TailLoss(group.key, float(group.total), float(group.total / total) if total else 0.0)
            for group in groups]


@dataclass(frozen=True)
class VolShares:
    """Each line's share of the portfolio's volatility, as fractions; all of them, cash included, add up to 1."""

    positions: tuple[float, ...]  # one per position, in valuation order
    cash: tuple[float, ...]       # one per cash balance, in valuation order
    start: date                   # the first and last daily return in the window
    end: date
    observations: int

    @property
    def cash_total(self) -> float:
        return math.fsum(self.cash)

    def by_group(self, valuation: Valuation, key: Callable[[PositionValue], str]) -> list[Group]:
        """The positions' shares summed by ``key``, largest first (ties by key). Cash is in no group."""
        if len(self.positions) != len(valuation.positions):
            raise ValueError("these shares belong to another valuation")
        pairs = zip(valuation.positions, self.positions)
        return rollup(pairs, key=lambda pair: key(pair[0]), value=lambda pair: to_decimal(pair[1]))


def vol_shares(valuation: Valuation, prices: PriceHistory, fx: FxRates, settings: RiskSettings) -> VolShares:
    """Each line's share of the portfolio's volatility (docs/risk-notes.md).

    The Euler allocation of the volatility of the daily simple returns over the
    window summarise_risk() uses: a line's share is the covariance of its daily
    P&L share with the portfolio's return, over the variance of that return.
    Both are sample estimates, so the divisor cancels. The lines' P&L shares add
    up to the portfolio's return every day, so the shares add up to 1.
    """
    table = daily_pnl_shares(valuation, prices, fx, settings.var_lookback_days)
    if len(table) < settings.min_observations:
        raise RiskError(
            f"only {len(table)} daily returns available, risk.min_observations is {settings.min_observations}; "
            f"load more price history or lower the setting"
        )
    returns = [row.portfolio_return for row in table]
    variance = statistics.variance(returns)
    if variance == 0:
        raise RiskError("the portfolio's daily returns do not vary over the window; shares of volatility are undefined")
    lines = len(table[0].shares)
    shares = [statistics.covariance([row.shares[index] for row in table], returns) / variance
              for index in range(lines)]
    count = len(valuation.positions)
    return VolShares(tuple(shares[:count]), tuple(shares[count:]), table[0].day, table[-1].day, len(table))
