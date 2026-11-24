"""The book against its benchmark (bt/metrics/benchmark.py, docs/metrics.md)."""
import math

import pytest

from bt.metrics.benchmark import benchmark_metrics, capture, covariance, paired_returns, total_return
from bt.metrics.returns import mean, sample_std

CONFIG = {"benchmark": "IDX", "max_fill_gap": 5}


def curve_of(navs):
    return [{"date": f"2026-04-{day:02d}", "nav": nav} for day, nav in enumerate(navs, start=1)]


def test_total_return_from_first_to_last_close():
    assert total_return([None, 100.0, 104.0, None, 110.0]) == 110.0 / 100.0 - 1.0
    assert total_return([None, 100.0, None]) is None


def test_returns_are_paired_on_the_days_the_benchmark_has_one():
    curve = curve_of([100.0, 101.0, 103.0, 102.0])
    ours, theirs = paired_returns(curve, [None, 0.01, None, -0.02])
    assert ours == [101.0 / 100.0 - 1.0, 102.0 / 103.0 - 1.0]
    assert theirs == [0.01, -0.02]


def test_covariance_of_a_series_with_itself_is_its_variance():
    values = [0.01, -0.02, 0.005, 0.012]
    assert math.sqrt(covariance(values, values)) == pytest.approx(sample_std(values), abs=1e-15)


def test_capture():
    assert capture([0.02, -0.01, 0.01], [0.01, -0.02, 0.01], True) == pytest.approx(0.015 / 0.01)
    assert capture([0.02, -0.01, 0.01], [0.01, -0.02, 0.01], False) == pytest.approx(0.5)
    assert capture([0.02], [0.01], False) is None


def test_a_book_that_is_the_benchmark():
    series = [100.0, 102.0, 101.0, 105.0, 104.0, 108.0]
    figures = benchmark_metrics(curve_of(series), series, CONFIG, 108.0 / 100.0 - 1.0)
    assert figures["beta"] == pytest.approx(1.0)
    assert figures["correlation"] == pytest.approx(1.0)
    assert figures["excess_return"] == 0.0
    assert figures["tracking_error"] is None and figures["information_ratio"] is None


def test_section_order():
    series = [100.0, 102.0, 101.0, 105.0]
    figures = benchmark_metrics(curve_of([100.0, 101.0, 100.5, 103.0]), series, CONFIG, 0.03)
    assert list(figures) == ["symbol", "total_return", "excess_return", "beta", "correlation", "tracking_error",
                             "information_ratio", "up_capture", "down_capture", "days"]
    assert figures["symbol"] == "IDX" and figures["days"] == 3


def test_information_ratio_is_the_active_return_over_tracking_error():
    series = [100.0, 102.0, 101.0, 105.0, 104.0]
    navs = [100.0, 101.0, 101.5, 103.0, 103.5]
    figures = benchmark_metrics(curve_of(navs), series, CONFIG, 0.035)
    ours, theirs = paired_returns(curve_of(navs), [None] + [series[i] / series[i - 1] - 1.0 for i in range(1, 5)])
    active = [r - b for r, b in zip(ours, theirs)]
    assert figures["information_ratio"] == pytest.approx(mean(active) * 252 / (sample_std(active) * math.sqrt(252)))


def test_a_flat_benchmark_has_no_beta():
    figures = benchmark_metrics(curve_of([100.0, 101.0, 102.0]), [50.0, 50.0, 50.0], CONFIG, 0.02)
    assert figures["beta"] is None and figures["correlation"] is None
    assert figures["total_return"] == 0.0


def test_gaps_in_the_benchmark_are_forward_filled():
    figures = benchmark_metrics(curve_of([100.0, 101.0, 102.0, 103.0]), [50.0, None, 51.0, 52.0], CONFIG, 0.03)
    assert figures["days"] == 3


def test_too_few_days_leaves_the_ratios_empty():
    figures = benchmark_metrics(curve_of([100.0, 101.0]), [50.0, 51.0], CONFIG, 0.01)
    assert figures["beta"] is None and figures["tracking_error"] is None and figures["days"] == 1
