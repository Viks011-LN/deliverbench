"""The price file, forward fill and returns, the --start/--end window, and the gap warnings."""
import pytest

from bt.data import apply_window, forward_fill, load_prices, simple_returns
from bt.data.benchmark import split_benchmark
from bt.data.quality import gap_warnings, missing_runs
from bt.data.series import first_price_index
from bt.errors import BacktestError, PriceFileError, WindowError


@pytest.mark.parametrize("text,message", [
    ("", "the price file is empty"),
    ("date\n2026-01-05\n2026-01-06\n", "the first column must be 'date', followed by at least one symbol"),
    ("day,AAA\n2026-01-05,10\n2026-01-06,11\n", "the first column must be 'date', followed by at least one symbol"),
    ("date,AAA,AAA\n2026-01-05,10,10\n2026-01-06,11,11\n", "a symbol appears twice in the header"),
    ("date,AAA,BBB\n2026-01-05,10,20\n2026-01-06,11\n", "3: expected 3 cells, found 2"),
    ("date,AAA\n2026-01-05,10\n2026-13-06,11\n", "3: '2026-13-06' is not a YYYY-MM-DD date"),
    ("date,AAA\n2026-01-06,10\n2026-01-06,11\n", "3: dates must increase (2026-01-06 comes after 2026-01-06)"),
    ("date,AAA\n2026-01-05,10\n2026-01-06,ten\n", "3: 'ten' is not a price (AAA)"),
    ("date,AAA\n2026-01-05,10\n2026-01-06,0\n", "3: prices must be positive (AAA 0)"),
    ("date,AAA\n2026-01-05,10\n", "at least two days of prices are needed"),
])
def test_price_file_problems(tmp_path, text, message):
    path = tmp_path / "prices.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PriceFileError) as caught:
        load_prices(str(path))
    assert str(caught.value) in (f"{path}: {message}", f"{path}:{message}")


def test_blank_lines_and_blank_cells(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,AAA,BBB\n2026-01-05,10,\n\n2026-01-06,11,21\n", encoding="utf-8")
    dates, symbols, prices = load_prices(str(path))
    assert dates == ["2026-01-05", "2026-01-06"]
    assert symbols == ["AAA", "BBB"]
    assert prices == {"AAA": [10.0, 11.0], "BBB": [None, 21.0]}


def test_the_sample_loads(sample):
    dates, symbols, prices = sample
    assert len(symbols) == 9 and symbols[-1] == "IDX"
    assert all(len(prices[s]) == len(dates) for s in symbols)
    assert dates == sorted(dates)


def test_forward_fill_stops_after_the_gap_limit():
    assert forward_fill([None, 1.0, None, None, 2.0, None, None, None], 2) == [
        None, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, None]


def test_forward_fill_with_no_gap_allowed():
    assert forward_fill([1.0, None, 3.0], 0) == [1.0, None, 3.0]


def test_simple_returns():
    returns = simple_returns([10.0, 11.0, None, 12.0])
    assert returns[0] is None
    assert returns[1] == 11.0 / 10.0 - 1.0
    assert returns[2] is None and returns[3] is None


def test_first_price_index():
    assert first_price_index([None, None, 3.0]) == 2
    assert first_price_index([None]) is None


DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
PRICES = {"AAA": [1.0, 2.0, 3.0, 4.0]}


def test_window_with_both_ends():
    dates, prices = apply_window(DATES, ["AAA"], PRICES, "2026-01-06", "2026-01-07")
    assert dates == ["2026-01-06", "2026-01-07"]
    assert prices == {"AAA": [2.0, 3.0]}


def test_window_with_start_only():
    dates, _ = apply_window(DATES, ["AAA"], PRICES, "2026-01-07", None)
    assert dates == ["2026-01-07", "2026-01-08"]


def test_window_with_end_only():
    dates, _ = apply_window(DATES, ["AAA"], PRICES, None, "2026-01-06")
    assert dates == ["2026-01-05", "2026-01-06"]


def test_no_window_keeps_everything():
    assert apply_window(DATES, ["AAA"], PRICES) == (DATES, PRICES)


def test_window_of_one_day_is_an_error():
    with pytest.raises(WindowError, match="fewer than two days between 2026-01-06 and 2026-01-06"):
        apply_window(DATES, ["AAA"], PRICES, "2026-01-06", "2026-01-06")


def test_no_benchmark_keeps_every_column():
    assert split_benchmark("p.csv", {"benchmark": None}, ["AAA"], PRICES) == (["AAA"], PRICES, None)


def test_the_benchmark_column_is_split_off():
    prices = {"AAA": [1.0, 2.0], "IDX": [10.0, 11.0], "BBB": [3.0, 4.0]}
    symbols, kept, benchmark = split_benchmark("p.csv", {"benchmark": "IDX"}, ["AAA", "IDX", "BBB"], prices)
    assert symbols == ["AAA", "BBB"]
    assert kept == {"AAA": [1.0, 2.0], "BBB": [3.0, 4.0]}
    assert benchmark == [10.0, 11.0]


def test_the_benchmark_must_be_a_column():
    with pytest.raises(BacktestError, match="benchmark 'SPX' is not a column of p.csv"):
        split_benchmark("p.csv", {"benchmark": "SPX"}, ["AAA"], PRICES)


def test_something_must_be_left_to_trade():
    with pytest.raises(BacktestError, match="no column to trade besides the benchmark 'AAA'"):
        split_benchmark("p.csv", {"benchmark": "AAA"}, ["AAA"], PRICES)


def test_missing_runs():
    assert missing_runs([None, 1.0, None, None, 2.0, None]) == [(2, 3), (5, 5)]


def test_gap_warnings():
    dates = [f"2026-02-{day:02d}" for day in range(2, 12)]
    prices = {"AAA": [1.0, None, None, None, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
              "BBB": [None] * 10,
              "CCC": [1.0] * 8 + [None, None]}
    assert gap_warnings(dates, ["AAA", "BBB", "CCC"], prices, 2) == [
        "warning: AAA has no price from 2026-02-03 to 2026-02-05 (3 days, more than max_fill_gap)",
        "warning: BBB has no price in the period",
    ]
    assert gap_warnings(dates, ["CCC"], prices, 1) == [
        "warning: CCC has no price from 2026-02-10 to 2026-02-11 (2 days, more than max_fill_gap)"]
