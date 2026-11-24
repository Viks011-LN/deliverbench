import dataclasses
import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from folio.calc import exposure
from folio.calc.returns import cumulative_return, max_drawdown, nav_series, simple_returns
from folio.calc.risk import (
    expected_shortfall,
    historical_var,
    percentile,
    summarise_risk,
    tail_losses,
)
from folio.errors import RiskError

RETURNS = [0.01, -0.02, 0.005, -0.01, 0.0, 0.015, -0.03, 0.02, 0.004, -0.001]


def series_of(values, start=date(2026, 1, 5)):
    return [(start + timedelta(days=i), Decimal(str(v))) for i, v in enumerate(values)]


def test_percentile_interpolates_like_excel():
    assert percentile([1, 2, 3, 4], 0.0) == 1
    assert percentile([1, 2, 3, 4], 1.0) == 4
    assert percentile([4, 1, 3, 2], 0.5) == 2.5
    assert percentile([10, 20], 0.25) == 12.5


def test_var_and_expected_shortfall():
    # 10% quantile of RETURNS: between -0.03 and -0.02, 0.9 of the way to -0.02.
    assert historical_var(RETURNS, 0.9) == pytest.approx(0.021)
    assert historical_var(RETURNS, 0.9, horizon_days=4) == pytest.approx(0.042)
    assert expected_shortfall(RETURNS, 0.9) == pytest.approx(0.03)
    assert historical_var([0.01, 0.02, 0.03], 0.99) == 0.0  # no losses, no VaR
    with pytest.raises(ValueError, match="confidence"):
        historical_var(RETURNS, 1.0)


def test_returns_and_drawdown():
    series = series_of([100, 110, 99, 105, 120, 90, 100])
    assert [round(r, 4) for _, r in simple_returns(series)] == [0.1, -0.1, 0.0606, 0.1429, -0.25, 0.1111]
    assert cumulative_return([0.1, -0.1]) == pytest.approx(-0.01)
    drawdown = max_drawdown(series)
    assert drawdown.depth == pytest.approx(-0.25)
    assert (drawdown.peak, drawdown.trough, drawdown.recovered) == (date(2026, 1, 9), date(2026, 1, 10), None)
    assert max_drawdown(series_of([1, 2, 3])) is None
    recovered = max_drawdown(series_of([100, 95, 101]))
    assert recovered.recovered == date(2026, 1, 7)


def test_nav_series_on_sample(valuation, prices, fx):
    series = nav_series(valuation, prices, fx)
    # PCRF prices monthly and its first price is 2026-06-30, so that is where the series starts.
    assert series[0][0] == date(2026, 6, 30)
    assert series[-1][0] == valuation.as_of
    assert series[-1][1] == pytest.approx(valuation.nav.amount)
    assert all(earlier[0] < later[0] for earlier, later in zip(series, series[1:]))


def test_summarise_risk_on_sample(valuation, prices, fx, settings):
    series = nav_series(valuation, prices, fx)
    risk = summarise_risk(series, valuation.nav, settings.risk)
    assert risk.observations == settings.risk.var_lookback_days == 60
    assert risk.end == valuation.as_of
    assert 0 < risk.var < risk.expected_shortfall < 0.05
    assert risk.var_amount.amount == pytest.approx(valuation.nav.amount * Decimal(repr(risk.var)))
    assert risk.worst_day[1] == min(risk.returns) and risk.best_day[1] == max(risk.returns)
    assert 0.02 < risk.volatility < 0.3
    assert math.isclose(risk.period_return, cumulative_return(list(risk.returns)))


def test_risk_needs_enough_history(valuation, prices, fx, settings):
    series = nav_series(valuation, prices, fx)[:15]
    with pytest.raises(RiskError, match="only 14 daily returns available"):
        summarise_risk(series, valuation.nav, settings.risk)
    relaxed = dataclasses.replace(settings.risk, min_observations=10, var_lookback_days=20)
    assert summarise_risk(series, valuation.nav, relaxed).observations == 14


def test_tail_losses_add_up_to_expected_shortfall(valuation, prices, fx, settings):
    risk = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    losses = tail_losses(valuation, prices, fx, settings.risk, exposure.SECTOR.key)
    assert sum(loss.loss for loss in losses) == pytest.approx(risk.expected_shortfall)
    assert sum(loss.share for loss in losses) == pytest.approx(1.0)
    assert [loss.loss for loss in losses] == sorted((loss.loss for loss in losses), reverse=True)
    by_currency = tail_losses(valuation, prices, fx, settings.risk, exposure.CURRENCY.key, cash_by_currency=True)
    assert {loss.key for loss in by_currency} == {"GBP", "USD", "EUR", "JPY"}
