import dataclasses
import io
import math
import statistics
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from folio.benchmark import active, allocation, overlap, tracking
from folio.benchmark.levels_csv import IndexLevels, load_levels
from folio.benchmark.weights_csv import load_weights, parse_weights
from folio.calc import exposure
from folio.calc.exposure import Dimension
from folio.data.prices_csv import PricePoint
from folio.errors import RiskError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 30)
DAY_BEFORE = date(2026, 10, 29)

# Against the small book (AAA 48%, BBB 32%, CCC 16%, cash 4%): ZZZ is a name
# the book does not hold and instruments.csv does not know.
SMALL_INDEX = (
    "id,weight,name,kind,sector,country,currency\n"
    "AAA,0.30,,,,,\n"
    "BBB,0.40,,,,,\n"
    "ZZZ,0.30,Zeta Corp,equity,Energy,,USD\n"
)


def compare_small(small_book, small_valuation, text=SMALL_INDEX):
    return active.compare(small_valuation, parse_weights(io.StringIO(text)), small_book[0])


@pytest.fixture
def small_comparison(small_book, small_valuation):
    return compare_small(small_book, small_valuation)


def rows(grouped):
    return [(row.key, row.held, row.listed, row.book, row.index) for row in grouped.rows]


def test_lines_small_book(small_comparison):
    assert [(line.id, line.book, line.index, line.active) for line in small_comparison.lines] == [
        ("AAA", Decimal("0.48"), Decimal("0.3"), Decimal("0.18")),
        ("BBB", Decimal("0.32"), Decimal("0.4"), Decimal("-0.08")),
        ("CCC", Decimal("0.16"), 0, Decimal("0.16")),
        ("ZZZ", 0, Decimal("0.3"), Decimal("-0.3")),
    ]
    zeta = small_comparison.lines[-1]
    assert (zeta.name, zeta.kind, zeta.currency, zeta.held, zeta.listed) == ("Zeta Corp", "equity", "USD", False, True)
    [cash] = small_comparison.cash
    assert (cash.id, cash.name, cash.kind, cash.book, cash.index) == ("CASH", "Cash GBP", "cash", Decimal("0.04"), 0)
    assert sum(line.active for line in small_comparison.every_line) == 0
    assert [line.id for line in active.by_active_weight(small_comparison.lines)] == ["AAA", "CCC", "BBB", "ZZZ"]


def test_sector_keeps_cash_apart_and_currency_folds_it_in(small_comparison):
    by_sector = active.by_group(small_comparison, exposure.DIMENSIONS["sector"])
    assert rows(by_sector) == [
        ("Technology", 1, 1, Decimal("0.48"), Decimal("0.3")),
        ("Diversified", 1, 0, Decimal("0.16"), 0),
        ("Government", 1, 1, Decimal("0.32"), Decimal("0.4")),
        ("Energy", 0, 1, 0, Decimal("0.3")),
    ]
    assert by_sector.cash == Decimal("0.04")
    assert by_sector.row("Energy").active == Decimal("-0.3")
    by_currency = active.by_group(small_comparison, exposure.DIMENSIONS["currency"])
    assert rows(by_currency) == [
        ("GBP", 2, 1, Decimal("0.68"), Decimal("0.3")),  # AAA, CCC and the cash; cash is not a holding
        ("USD", 1, 2, Decimal("0.32"), Decimal("0.7")),
    ]
    assert by_currency.cash == 0


def test_kind_keeps_its_order_and_blank_listings_are_unknown(small_book, small_valuation):
    comparison = compare_small(small_book, small_valuation, "id,weight,name\nAAA,0.7,\nYYY,0.3,Yew Ltd\n")
    by_kind = active.by_group(comparison, exposure.DIMENSIONS["kind"])
    assert [(row.key, row.index) for row in by_kind.rows] == [
        ("equity", Decimal("0.7")), ("bond", 0), ("fund", 0), (active.UNKNOWN, Decimal("0.3"))]
    by_sector = active.by_group(comparison, exposure.DIMENSIONS["sector"])
    assert by_sector.row(active.UNKNOWN).index == Decimal("0.3")


def test_a_dimension_reading_what_index_names_lack_groups_them_as_unknown(small_comparison):
    # As a breakdown added to folio.calc.exposure later might: held lines have a price date, index names do not.
    by_price_date = Dimension("priced", "Priced", lambda line: line.price_date.isoformat())
    grouped = active.by_group(small_comparison, by_price_date)
    assert [(row.key, row.book, row.index) for row in grouped.rows] == [
        ("2026-10-30", Decimal("0.96"), Decimal("0.7")),
        (active.UNKNOWN, 0, Decimal("0.3")),
    ]
    by_rating = Dimension("rating", "Rating", lambda line: line.instrument.rating)
    assert [row.key for row in active.by_group(small_comparison, by_rating).rows] == [active.UNKNOWN]


def test_instruments_csv_wins_over_the_benchmark_file(small_book, small_valuation):
    text = "id,weight,sector\nAAA,0.5,Energy\nBBB,0.5,Government\n"
    comparison = active.compare(small_valuation, parse_weights(io.StringIO(text), source="index.csv"), small_book[0])
    assert comparison.notes == (
        "index.csv:2: AAA has sector 'Energy' there but 'Technology' in instruments.csv, which is used",)
    assert active.by_group(comparison, exposure.DIMENSIONS["sector"]).row("Technology").index == Decimal("0.5")


def test_active_share_and_largest_bets(small_comparison):
    result = overlap.overlap(small_comparison, top=1)
    assert result.active_share == Decimal("0.38")  # (18 + 8 + 16 + 30 + 4) / 2 points
    assert result.in_common == Decimal("0.62")
    assert (result.held, result.listed, result.common) == (3, 3, 2)
    assert [line.id for line in result.overweights] == ["AAA"]
    assert [line.id for line in result.underweights] == ["ZZZ"]
    wide = overlap.overlap(small_comparison, top=10)
    assert [line.id for line in wide.overweights] == ["AAA", "CCC"]
    assert [line.id for line in wide.underweights] == ["ZZZ", "BBB"]
    with pytest.raises(ValueError, match="top must be 1 or more"):
        overlap.overlap(small_comparison, top=0)


def test_sample_weights_add_up_in_every_breakdown(valuation, universe):
    comparison = active.compare(valuation, load_weights(DATA_DIR / "benchmark.csv"), universe)
    assert comparison.notes == ()
    assert len(comparison.lines) == 62  # 38 held, 24 more in the index
    assert sum(line.active for line in comparison.every_line) == pytest.approx(0, abs=1e-20)
    for name in ("sector", "currency", "kind"):
        grouped = active.by_group(comparison, exposure.DIMENSIONS[name])
        assert sum(row.book for row in grouped.rows) + grouped.cash == pytest.approx(1), name
        assert sum(row.index for row in grouped.rows) == pytest.approx(1), name
    result = overlap.overlap(comparison)
    assert result.active_share + result.in_common == pytest.approx(1)
    assert len(result.overweights) == len(result.underweights) == 5


WEEK = [date(2026, 10, 26) + timedelta(days=offset) for offset in range(5)]
BOOK = ["100", "101", "103.02", "101.9898", "101.9898"]     # +1%, +2%, -1%, 0%
INDEX = ["1000", "1010", "1020.1", "1020.1", "1009.899"]    # +1%, +1%, 0%, -1%


def series_of(values, days=WEEK):
    return [(day, Decimal(value)) for day, value in zip(days, values)]


def levels_of(values, days=WEEK):
    return IndexLevels("IDX", [PricePoint(day, Decimal(value)) for day, value in zip(days, values)])


@pytest.fixture
def relaxed(settings):
    return dataclasses.replace(settings.risk, min_observations=2)


def test_tracking_error_relative_return_and_beta(relaxed):
    summary = tracking.summarise_tracking(series_of(BOOK), levels_of(INDEX), 60, relaxed)
    assert (summary.code, summary.start, summary.end, summary.observations) == ("IDX", WEEK[0], WEEK[-1], 4)
    assert summary.book_return == pytest.approx(0.019898)
    assert summary.index_return == pytest.approx(0.009899)
    assert summary.relative_return == pytest.approx(0.009999)
    assert summary.tracking_error == pytest.approx(statistics.stdev([0.0, 0.01, -0.01, 0.01]) * math.sqrt(252))
    assert summary.beta == pytest.approx(10 / 11)
    assert summary.worst_day == (WEEK[3], pytest.approx(-0.01))
    assert summary.best_day[1] == pytest.approx(0.01)
    flat = tracking.summarise_tracking(series_of(BOOK), levels_of(["1000"] * 5), 60, relaxed)
    assert flat.beta is None


def test_window_keeps_the_latest_returns(relaxed):
    summary = tracking.summarise_tracking(series_of(BOOK), levels_of(INDEX), 2, relaxed)
    assert (summary.start, summary.observations) == (WEEK[2], 2)
    assert summary.book_return == pytest.approx(-0.01)


def test_levels_that_start_late_or_end_early(relaxed, settings):
    late = levels_of(INDEX[2:], WEEK[2:])
    summary = tracking.summarise_tracking(series_of(BOOK), late, 60, relaxed)
    assert (summary.start, summary.observations) == (WEEK[2], 2)
    with pytest.raises(RiskError, match=r"only 2 daily returns in the window .*\(levels start on 2026-10-28\)"):
        tracking.summarise_tracking(series_of(BOOK), late, 60, settings.risk)
    early = tracking.summarise_tracking(series_of(BOOK), levels_of(INDEX[:4], WEEK[:4]), 60, relaxed)
    assert early.last_level == WEEK[3]
    assert early.index_return == pytest.approx(0.0201)  # the last day reuses the level before it


def small_split(small_book, comparison, name):
    _, _, prices, fx = small_book
    levels = levels_of(["1000", "1050"], [DAY_BEFORE, AS_OF])  # the index made 5%
    return allocation.split_by_group(comparison, prices, fx, levels, DAY_BEFORE, exposure.DIMENSIONS[name])


def test_split_by_sector_small_book(small_book, small_comparison):
    # The day before, AAA was at 10 and NAV 23,000: AAA 10,000, BBB 8,000, CCC 4,000, cash 1,000.
    split = small_split(small_book, small_comparison, "sector")
    assert [row.key for row in split.rows] == ["Technology", "Government", "Energy", "Diversified", "Cash"]
    effects = {row.key: row for row in split.rows}
    assert float(effects["Technology"].allocation) == pytest.approx((10 / 23 - 0.3) * (0.20 - 0.05))
    assert float(effects["Government"].allocation) == pytest.approx((8 / 23 - 0.4) * (0.0 - 0.05))
    assert float(effects["Diversified"].allocation) == pytest.approx(4 / 23 * (0.0 - 0.05))
    assert effects["Diversified"].index_return is None  # the index has no funds: all allocation
    assert effects["Energy"].index_return == Decimal("0.05")  # ZZZ has no prices: it did what the index did
    assert (effects["Energy"].allocation, effects["Energy"].book_return) == (0, None)
    assert float(effects["Cash"].allocation) == pytest.approx(1 / 23 * (0.0 - 0.05))
    assert split.selection == pytest.approx(0, abs=1e-20)  # every held group did what its index names did
    assert split.book_return == Decimal(2000) / Decimal(23000)
    assert split.index_return == Decimal("0.05")
    assert split.priced_weight == Decimal("0.7")
    assert split.rebuilt_return == Decimal("0.075")  # 30% x 20% + 40% x 0% + 30% x 5%
    assert split.residual == pytest.approx(split.rebuilt_return - split.index_return)


def test_split_by_currency_has_selection(small_book, small_comparison):
    split = small_split(small_book, small_comparison, "currency")
    assert [row.key for row in split.rows] == ["USD", "GBP"]  # cash is in GBP, no row of its own
    gbp = split.rows[1]
    assert float(gbp.book_return) == pytest.approx(2000 / 15000)
    assert float(gbp.selection) == pytest.approx(15 / 23 * (2000 / 15000 - 0.20))
    assert float(gbp.allocation) == pytest.approx((15 / 23 - 0.3) * (0.20 - 0.05))
    assert split.rows[0].index_return == 0  # ZZZ takes BBB's return, the only priced USD name
    assert float(split.residual) == pytest.approx(0.06 - 0.05)
    assert float(split.allocation + split.selection) == pytest.approx(2 / 23 - 0.06)
    with pytest.raises(ValueError, match="must be before the valuation date"):
        allocation.split_by_group(small_comparison, small_book[2], small_book[3], levels_of(["1"], [AS_OF]),
                                  AS_OF, exposure.DIMENSIONS["sector"])


def test_sample_split_by_kind(valuation, universe, prices, fx):
    comparison = active.compare(valuation, load_weights(DATA_DIR / "benchmark.csv"), universe)
    levels = load_levels(DATA_DIR / "benchmark_levels.csv")
    split = allocation.split_by_group(comparison, prices, fx, levels, date(2026, 9, 1), exposure.DIMENSIONS["kind"])
    assert [row.key for row in split.rows] == ["equity", "bond", "fund", "Cash"]  # fixed order, cash last
    assert sum(row.book_weight for row in split.rows) == pytest.approx(1)
    assert sum(row.index_weight for row in split.rows) == pytest.approx(1)
    assert split.residual == pytest.approx(split.rebuilt_return - split.index_return)
    assert abs(split.residual) < Decimal("0.01")
