"""The summary metrics, and the drawdown periods."""
import math

import pytest

from bt.metrics import compute_metrics, max_drawdown, monthly_returns, sharpe_ratio, sortino_ratio, yearly_returns
from bt.metrics.drawdowns import drawdown_periods, worst_drawdowns
from bt.metrics.holding import position_stats
from bt.metrics.ratios import calmar_ratio
from bt.metrics.returns import daily_returns, mean, sample_std, wins_and_losses

CURVE = [
    {"date": "2025-12-30", "nav": 100.0, "gross": 0.0, "net": 0.0, "holdings": 0},
    {"date": "2025-12-31", "nav": 102.0, "gross": 1.0, "net": 1.0, "holdings": 1},
    {"date": "2026-01-02", "nav": 101.0, "gross": 1.0, "net": 1.0, "holdings": 1},
    {"date": "2026-01-05", "nav": 104.0, "gross": 1.0, "net": 0.5, "holdings": 2},
    {"date": "2026-02-02", "nav": 104.0, "gross": 0.5, "net": 0.5, "holdings": 1},
]
STATS = {"trades": 4, "forced_exits": 1, "stop_losses": 0, "traded_notional": 300.0, "commissions": 1.5, "slippage": 0.6,
         "borrow_fees": 0.0, "interest": 0.25}


def curve_of(navs):
    return [{"date": f"2026-03-{day:02d}", "nav": nav} for day, nav in enumerate(navs, start=2)]


def test_daily_returns():
    assert daily_returns(CURVE) == [102.0 / 100.0 - 1.0, 101.0 / 102.0 - 1.0, 104.0 / 101.0 - 1.0, 0.0]


def test_mean_and_sample_std():
    assert mean([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert sample_std([1.0, 2.0, 3.0, 4.0]) == pytest.approx(math.sqrt(5.0 / 3.0))


def test_wins_and_losses_leave_out_flat_days():
    assert wins_and_losses([0.1, -0.1, 0.0, 0.2]) == (2, 1)


def test_max_drawdown():
    assert max_drawdown([100.0, 120.0, 90.0, 130.0]) == 90.0 / 120.0 - 1.0
    assert max_drawdown([100.0, 101.0, 102.0]) == 0.0


def test_sharpe_is_undefined_without_variation():
    assert sharpe_ratio([0.0, 0.0, 0.0], 0.0) is None
    assert sharpe_ratio([0.01], 0.0) is None


def test_sharpe_uses_the_daily_risk_free_rate():
    returns = [0.01, -0.005, 0.002, 0.004]
    excess = [r - 0.0252 / 252 for r in returns]
    assert sharpe_ratio(returns, 0.0252) == pytest.approx(mean(excess) / sample_std(excess) * math.sqrt(252))


def test_sortino_is_undefined_without_a_down_day():
    assert sortino_ratio([0.01, 0.02, 0.0], 0.0) is None


def test_sortino_counts_only_down_days():
    value = sortino_ratio([0.02, -0.01, 0.01, -0.02], 0.0)
    downside = math.sqrt((0.0001 + 0.0004) / 4)
    assert value == pytest.approx(mean([0.02, -0.01, 0.01, -0.02]) / downside * math.sqrt(252))


def test_calmar():
    assert calmar_ratio(0.1, -0.2) == 0.5
    assert calmar_ratio(0.1, 0.0) is None


def test_monthly_returns_compound_the_days():
    months = monthly_returns(CURVE)
    assert list(months) == ["2025-12", "2026-01", "2026-02"]
    assert months["2025-12"] == pytest.approx(0.02)
    assert months["2026-01"] == pytest.approx(104.0 / 102.0 - 1.0)
    assert months["2026-02"] == 0.0


def test_yearly_returns():
    assert yearly_returns(CURVE) == pytest.approx({"2025": 0.02, "2026": 104.0 / 102.0 - 1.0})


def test_compute_metrics_keys_in_report_order():
    metrics = compute_metrics(CURVE, STATS, {"risk_free_rate": 0.0})
    assert list(metrics) == ["total_return", "annual_return", "annual_volatility", "sharpe", "sortino",
                             "max_drawdown", "calmar", "hit_rate", "best_day", "worst_day", "average_gross",
                             "average_net", "average_holdings", "turnover", "trades", "forced_exits", "stop_losses",
                             "commissions", "slippage", "borrow_fees", "interest"]


def test_compute_metrics_values():
    metrics = compute_metrics(CURVE, STATS, {"risk_free_rate": 0.0})
    assert metrics["total_return"] == 104.0 / 100.0 - 1.0
    assert metrics["hit_rate"] == 2 / 3
    assert metrics["best_day"] == 104.0 / 101.0 - 1.0
    assert metrics["trades"] == 4 and metrics["forced_exits"] == 1
    assert metrics["average_gross"] == pytest.approx(3.5 / 5)
    assert metrics["average_holdings"] == 5 / 5
    assert metrics["interest"] == 0.25


def test_volatility_is_none_for_a_single_return():
    curve = CURVE[:2]
    assert compute_metrics(curve, STATS, {"risk_free_rate": 0.0})["annual_volatility"] is None


def test_drawdown_periods_from_high_to_recovery():
    periods = drawdown_periods(curve_of([100.0, 110.0, 99.0, 105.0, 112.0, 108.0]))
    assert periods == [
        {"peak": "2026-03-03", "trough": "2026-03-04", "recovery": "2026-03-06", "depth": 99.0 / 110.0 - 1.0,
         "days": 3},
        {"peak": "2026-03-06", "trough": "2026-03-07", "recovery": None, "depth": 108.0 / 112.0 - 1.0, "days": 1},
    ]


def test_a_return_to_the_high_ends_a_period():
    periods = drawdown_periods(curve_of([100.0, 90.0, 100.0, 95.0]))
    assert [p["recovery"] for p in periods] == ["2026-03-04", None]


def test_no_fall_no_period():
    assert drawdown_periods(curve_of([100.0, 100.0, 101.0])) == []
    assert worst_drawdowns(curve_of([100.0, 100.0, 101.0])) == []


def test_worst_drawdowns_deepest_first():
    navs = [100.0, 95.0, 101.0, 80.0, 102.0, 99.0, 103.0, 90.0, 104.0]
    worst = worst_drawdowns(curve_of(navs))
    assert [round(p["depth"], 6) for p in worst] == [round(80.0 / 101.0 - 1.0, 6), round(90.0 / 103.0 - 1.0, 6),
                                                      round(95.0 / 100.0 - 1.0, 6)]


DAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]


def trade(day, symbol, after):
    return {"date": day, "symbol": symbol, "after": after}


def test_positions_open_and_close():
    trades = [trade(DAYS[0], "A", 10.0), trade(DAYS[0], "B", -5.0), trade(DAYS[2], "A", 12.0),
              trade(DAYS[3], "A", 0.0), trade(DAYS[4], "B", 0.0), trade(DAYS[4], "C", 3.0)]
    assert position_stats(trades, DAYS) == {"opened": 3, "closed": 2, "still_open": 1, "average_days_held": 3.5,
                                            "longest_held": {"symbol": "B", "days": 4}}


def test_a_flip_keeps_the_position_open():
    stats = position_stats([trade(DAYS[0], "A", 10.0), trade(DAYS[1], "A", -10.0)], DAYS)
    assert stats["opened"] == 1 and stats["closed"] == 0 and stats["still_open"] == 1


def test_no_trades_no_positions():
    assert position_stats([], DAYS) == {"opened": 0, "closed": 0, "still_open": 0, "average_days_held": None,
                                        "longest_held": None}
