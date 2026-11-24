"""Portfolio construction: ranking, the price floor, the weight cap, volatility scaling, the drawdown control,
the schedule and target units."""
import statistics
from datetime import date

import pytest

from bt.data.calendar import month_key, new_month, new_week, parse_day, year_key
from bt.portfolio import (apply_price_floor, apply_weight_cap, drawdown_control, is_rebalance_day,
                          scores_to_weights, target_units, trailing_vol, volatility_scale)
from bt.portfolio.drawdown import drawdown
from bt.portfolio.ranking import ranked
from bt.portfolio.schedule import trades_today


def test_long_only_weights_follow_the_scores():
    weights = scores_to_weights({"A": 0.3, "B": 0.1, "C": -0.2, "D": None}, 3, False)
    assert weights == {"A": 0.3 / 0.4, "B": 0.1 / 0.4}


def test_long_short_books_have_half_on_each_side():
    weights = scores_to_weights({"A": 0.3, "B": 0.1, "C": -0.2, "D": -0.6}, 2, True)
    assert weights["A"] + weights["B"] == pytest.approx(0.5)
    assert weights["C"] + weights["D"] == pytest.approx(-0.5)


def test_only_the_top_n_are_held():
    weights = scores_to_weights({"A": 0.3, "B": 0.2, "C": 0.1}, 2, False)
    assert set(weights) == {"A", "B"}


def test_ties_are_broken_by_symbol():
    assert ranked({"B": 0.1, "A": 0.1, "C": 0.2}) == [(0.2, "C"), (0.1, "A"), (0.1, "B")]


def test_a_zero_score_is_neither_long_nor_short():
    assert scores_to_weights({"A": 0.0, "B": -0.1}, 3, True) == {"B": -0.5}


def test_no_scores_no_book():
    assert scores_to_weights({"A": None, "B": None}, 3, True) == {}


def test_price_floor_leaves_out_cheap_names():
    scores = apply_price_floor({"A": 0.2, "B": 0.1, "C": None}, {"A": 4.0, "B": 9.0, "C": 1.0}, 5.0)
    assert scores == {"A": None, "B": 0.1, "C": None}


def test_no_price_floor_by_default():
    scores = {"A": 0.2}
    assert apply_price_floor(scores, {"A": 0.01}, 0.0) is scores


def test_weight_cap_hands_the_excess_to_the_others():
    capped = apply_weight_cap({"A": 0.6, "B": 0.3, "C": 0.1}, 0.4)
    assert capped["A"] == 0.4
    assert capped["B"] > 0.3 and capped["C"] > 0.1
    assert abs(sum(capped.values()) - 1.0) < 1e-12


def test_weight_cap_keeps_the_rest_in_cash_when_every_name_is_capped():
    capped = apply_weight_cap({"A": 0.7, "B": 0.3}, 0.25)
    assert capped == {"A": 0.25, "B": 0.25}


def test_weight_cap_works_on_shorts():
    capped = apply_weight_cap({"A": -0.45, "B": -0.05}, 0.4)
    assert capped["A"] == -0.4
    assert capped["B"] == pytest.approx(-0.1)


def test_trailing_vol_is_the_sample_standard_deviation():
    returns = [None, 0.01, -0.02, 0.015, 0.003, -0.007, 0.012]
    assert trailing_vol(returns, 6, 5) == pytest.approx(statistics.stdev(returns[2:7]), abs=1e-15)


def test_trailing_vol_is_none_with_a_missing_return():
    assert trailing_vol([None, 0.01, None, 0.02], 3, 3) is None


def test_no_vol_target_no_scaling():
    assert volatility_scale({"A": 1.0}, {"A": 0.01}, None, 1.5) == 1.0


def test_vol_target_scales_the_book():
    scale = volatility_scale({"A": 1.0}, {"A": 0.01}, 0.1, 5.0)
    assert scale == pytest.approx(0.1 / (0.01 * 252 ** 0.5))


def test_vol_target_scaling_is_capped_at_max_leverage():
    assert volatility_scale({"A": 1.0}, {"A": 0.0001}, 0.2, 1.5) == 1.5


def test_no_scaling_when_a_volatility_is_unknown():
    assert volatility_scale({"A": 0.5, "B": 0.5}, {"A": 0.01, "B": None}, 0.1, 1.5) == 1.0


def test_no_scaling_without_volatility():
    assert volatility_scale({"A": 1.0}, {"A": 0.0}, 0.1, 1.5) == 1.0


def test_drawdown():
    assert drawdown(90.0, 100.0) == 90.0 / 100.0 - 1.0


def test_drawdown_control_cuts_the_book_beyond_the_limit():
    assert drawdown_control(1.2, -0.15, 0.1, 0.5) == 0.6
    assert drawdown_control(1.2, -0.05, 0.1, 0.5) == 1.2
    assert drawdown_control(1.2, -0.5, None, 0.5) == 1.2


def test_target_units():
    assert target_units(0.25, 1.0, 1000000.0, 50.0) == 0.25 * 1.0 * 1000000.0 / 50.0


def test_calendar_helpers():
    assert parse_day("2026-03-02") == date(2026, 3, 2)
    assert month_key("2026-03-02") == "2026-03"
    assert year_key("2026-03-02") == "2026"
    assert new_month(date(2026, 3, 2), date(2026, 2, 27))
    assert not new_month(date(2026, 3, 3), date(2026, 3, 2))


def test_new_week_on_a_monday():
    assert new_week(date(2026, 3, 9), date(2026, 3, 6))
    assert not new_week(date(2026, 3, 10), date(2026, 3, 9))


DATES = ["2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-09"]


def test_rebalance_schedules():
    assert is_rebalance_day(DATES, 3, "daily")
    assert is_rebalance_day(DATES, 2, "monthly") and not is_rebalance_day(DATES, 3, "monthly")
    assert is_rebalance_day(DATES, 2, "weekly") and is_rebalance_day(DATES, 5, "weekly")
    assert not is_rebalance_day(DATES, 4, "weekly")


def test_trades_on_the_first_day_then_on_schedule():
    assert not trades_today(DATES, 0, 1, "monthly")
    assert trades_today(DATES, 1, 1, "monthly")
    assert trades_today(DATES, 2, 1, "monthly")
    assert not trades_today(DATES, 3, 1, "monthly")
