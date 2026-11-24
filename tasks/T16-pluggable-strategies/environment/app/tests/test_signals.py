"""Scoring: the momentum and reversion signals, their rolling statistics, and compute_scores."""
import math
import statistics

import pytest

from bt.signals import compute_scores
from bt.signals.momentum import momentum_score
from bt.signals.reversion import reversion_score
from bt.signals.stats import rolling_mean, rolling_std, window_values, zscore

SERIES = [10.0, 10.5, 11.0, 10.8, 11.6, 12.0, 11.7, 12.4]


def test_momentum_is_the_return_between_two_past_days():
    assert momentum_score(SERIES, 7, 6, 2) == SERIES[5] / SERIES[1] - 1.0


def test_momentum_without_skip_uses_today():
    assert momentum_score(SERIES, 7, 7, 0) == SERIES[7] / SERIES[0] - 1.0


def test_momentum_is_none_when_a_price_is_missing():
    assert momentum_score([None, 2.0, 3.0, 4.0], 3, 3, 1) is None


def test_window_values():
    assert window_values(SERIES, 4, 3) == [11.0, 10.8, 11.6]


def test_rolling_mean():
    assert rolling_mean(SERIES, 4, 5) == pytest.approx(statistics.fmean(SERIES[:5]), abs=1e-12)


def test_rolling_mean_is_none_with_a_gap():
    assert rolling_mean([1.0, None, 3.0], 2, 3) is None


def test_rolling_std():
    assert rolling_std(SERIES, 7, 8) == pytest.approx(statistics.stdev(SERIES), abs=1e-12)


def test_zscore():
    assert zscore(12.0, 10.0, 2.0) == 1.0


def test_reversion_is_minus_the_zscore():
    std = rolling_std(SERIES, 7, 5)
    mean = rolling_mean(SERIES, 7, 5)
    assert reversion_score(SERIES, 7, 5, 0.0) == -((SERIES[7] - mean) / std)


def test_reversion_is_zero_inside_the_band():
    assert reversion_score(SERIES, 7, 5, 10.0) == 0.0


def test_reversion_scores_a_cheap_name_high():
    falling = [10.0, 10.0, 10.2, 9.9, 10.1, 8.0]
    assert reversion_score(falling, 5, 6, 0.5) > 0.0


def test_reversion_is_none_for_a_flat_price():
    assert reversion_score([5.0] * 6, 5, 4, 1.0) is None


def test_reversion_is_none_for_an_incomplete_window():
    assert reversion_score([5.0, None, 5.5, 6.0], 3, 4, 1.0) is None


PRICES = {"AAA": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0], "BBB": [20.0, 19.0, 18.0, 17.0, 16.0, None]}


def test_compute_scores_momentum():
    scores = compute_scores(PRICES, ["AAA", "BBB"], 4, {"type": "momentum", "lookback": 3, "skip": 1})
    assert scores == {"AAA": 13.0 / 11.0 - 1.0, "BBB": 17.0 / 19.0 - 1.0}


def test_compute_scores_gives_none_without_a_price_today():
    scores = compute_scores(PRICES, ["AAA", "BBB"], 5, {"type": "momentum", "lookback": 3, "skip": 1})
    assert scores["BBB"] is None
    assert scores["AAA"] == 14.0 / 12.0 - 1.0


def test_compute_scores_reversion():
    prices = {"AAA": SERIES}
    scores = compute_scores(prices, ["AAA"], 7, {"type": "reversion", "window": 5, "entry_z": 0.0})
    assert scores == {"AAA": reversion_score(SERIES, 7, 5, 0.0)}


def test_compute_scores_keeps_symbol_order():
    scores = compute_scores(PRICES, ["BBB", "AAA"], 4, {"type": "momentum", "lookback": 3, "skip": 1})
    assert list(scores) == ["BBB", "AAA"]


def test_compute_scores_uses_the_default_parameters():
    series = [100.0 + i for i in range(70)]
    scores = compute_scores({"AAA": series}, ["AAA"], 69, {"type": "momentum"})
    assert scores["AAA"] == series[64] / series[9] - 1.0


def test_scores_are_plain_floats():
    scores = compute_scores(PRICES, ["AAA"], 4, {"type": "momentum", "lookback": 3, "skip": 1})
    assert isinstance(scores["AAA"], float) and math.isfinite(scores["AAA"])
