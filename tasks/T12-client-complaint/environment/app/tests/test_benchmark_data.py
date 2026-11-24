import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.benchmark.levels_csv import load_levels, parse_levels
from folio.benchmark.weights_csv import load_weights, parse_weights
from folio.errors import DataError, MissingPriceError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = "id,weight,name,kind,sector,country,currency\n"


def test_sample_weights():
    weights = load_weights(DATA_DIR / "benchmark.csv")
    assert weights.source == "benchmark.csv"
    assert len(weights) == 53
    assert sum(item.weight for item in weights.constituents) == 1
    ids = [item.id for item in weights.constituents]
    assert ids == sorted(ids)
    assert weights.weight("UST31") == Decimal("0.072")
    assert weights.weight("GEIF") == 0  # a fund the book holds and the index does not
    orvelle = next(item.listing for item in weights.constituents if item.id == "ORVL")
    assert (orvelle.name, orvelle.kind, orvelle.sector, orvelle.country, orvelle.currency) == (
        "Orvelle Networks Inc", "equity", "Technology", "US", "USD")
    adzel = next(item.listing for item in weights.constituents if item.id == "ADZM")
    assert (adzel.name, adzel.sector) == ("", "")  # instruments.csv describes it


def test_comments_blank_lines_unknown_columns_and_tidying():
    weights = parse_weights(io.StringIO(
        "ID,Weight,Provider code,Name,Kind,Currency\n"
        "AAA,0.6,X1, Alpha Corp ,Equity,usd\n"
        "\n"
        "#BBB,0.2,X2,,,\n"
        "CCC,0.4,,,,,\n"))
    assert [(item.id, item.weight, item.line) for item in weights.constituents] == [
        ("AAA", Decimal("0.6"), 2), ("CCC", Decimal("0.4"), 5)]
    alpha = weights.constituents[0].listing
    assert (alpha.name, alpha.kind, alpha.currency, alpha.issuer_key) == ("Alpha Corp", "equity", "USD", "AAA")


def test_weights_within_the_tolerance_are_scaled_to_one():
    weights = parse_weights(io.StringIO("id,weight\nAAA,0.5004\nBBB,0.5\n"))
    assert weights.weight("BBB") == Decimal("0.5") / Decimal("1.0004")
    assert abs(sum(item.weight for item in weights.constituents) - 1) < Decimal("1e-20")


@pytest.mark.parametrize("text, message", [
    ("", "test.csv: file is empty"),
    ("weight,name\n0.5,A\n", "test.csv:1: missing column(s): id"),
    ("id,weight\n", "test.csv: no constituents in file"),
    (HEADER + "AAA,,,,,,\n", "test.csv:2: AAA: weight is empty"),
    (HEADER + "AAA,half,,,,,\n", "test.csv:2: weight of AAA 'half' is not a number"),
    (HEADER + "AAA,-0.1,,,,,\n", "test.csv:2: weight of AAA must be above 0, got -0.1"),
    (HEADER + "AAA,0.5,,,,,\nAAA,0.5,,,,,\n", "test.csv:3: AAA is listed twice (first on line 2)"),
    (HEADER + "ZZZ,1,Zeta,share,Energy,US,USD\n", "test.csv:2: ZZZ: unknown kind 'share'"),
    (HEADER + "ZZZ,1,Zeta,equity,Energy,US,dollar\n", "test.csv:2: ZZZ: invalid currency code 'DOLLAR'"),
    (HEADER + "AAA,1,,,,,,surprise\n", "test.csv:2: row has more cells than the header has columns"),
    (HEADER + "AAA,0.6,,,,,\nBBB,0.3,,,,,\n", "test.csv: weights add up to 0.9, not 1 (tolerance 0.001)"),
    ("id,weight\nAAA,60\nBBB,40\n", "they look like percentages"),
])
def test_weight_errors_name_file_and_line(text, message):
    with pytest.raises(DataError) as caught:
        parse_weights(io.StringIO(text), source="test.csv")
    assert message in str(caught.value)


def test_missing_files_point_at_their_option(tmp_path):
    with pytest.raises(DataError, match=r"benchmark weights file not found: .* \(use --benchmark\)"):
        load_weights(tmp_path / "benchmark.csv")
    with pytest.raises(DataError, match=r"benchmark levels file not found: .* \(use --levels\)"):
        load_levels(tmp_path / "benchmark_levels.csv")


def test_sample_levels_are_on_the_price_dates(prices):
    levels = load_levels(DATA_DIR / "benchmark_levels.csv")
    assert levels.code == "HGB6040"
    assert len(levels) == len(prices.dates())
    assert (levels.first_date(), levels.last_date()) == (prices.first_date(), prices.last_date())
    assert all(levels.latest(day).day == day for day in prices.dates())


def test_level_gaps_use_the_latest_earlier_level():
    levels = parse_levels(io.StringIO("date,IDX\n2026-10-26,100\n2026-10-27,\n\n2026-10-28,110.5\n"))
    assert len(levels) == 2
    point = levels.latest(date(2026, 10, 27))
    assert (point.day, point.price) == (date(2026, 10, 26), Decimal(100))
    assert levels.latest(date(2026, 11, 2)).price == Decimal("110.5")
    assert levels.period_return(date(2026, 10, 26), date(2026, 10, 30)) == Decimal("0.105")
    with pytest.raises(MissingPriceError, match="no level for IDX on or before 2026-10-23"):
        levels.latest(date(2026, 10, 23))


@pytest.mark.parametrize("text, message", [
    ("", "levels.csv: file is empty"),
    ("day,IDX\n", "levels.csv:1: the first column must be 'date', not 'day'"),
    ("date,IDX,OTHER\n", "levels.csv:1: expected a date column and one level column"),
    ("date,IDX\n26/10/2026,100\n", "levels.csv:2: date '26/10/2026' is not a date in YYYY-MM-DD form"),
    ("date,IDX\n2026-10-24,100\n", "levels.csv:2: 2026-10-24 is a Saturday"),
    ("date,IDX\n2026-10-27,100\n2026-10-26,101\n", "levels.csv:3: dates must increase"),
    ("date,IDX\n2026-10-26,0\n", "levels.csv:2: level of IDX must be positive, got 0"),
    ("date,IDX\n2026-10-26,abc\n", "levels.csv:2: level of IDX 'abc' is not a number"),
    ("date,IDX\n2026-10-26,100,7\n", "levels.csv:2: 3 cells but the header has 2 columns"),
    ("date,IDX\n2026-10-26,\n", "levels.csv: no levels for IDX"),
])
def test_level_errors_name_file_and_line(text, message):
    with pytest.raises(DataError) as caught:
        parse_levels(io.StringIO(text), source="levels.csv")
    assert message in str(caught.value)
