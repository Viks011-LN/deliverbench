from datetime import date
from decimal import Decimal

import pytest

from folio.aggregate.attribution import CASH_KEY, contributions, total_return
from folio.calc import exposure
from folio.domain.money import Money


def summary(breakdown):
    return [(row.key, row.positions, row.value.amount, row.share) for row in breakdown.rows]


def test_by_sector_small_book(small_valuation):
    result = exposure.by_sector(small_valuation)
    assert summary(result) == [
        ("Technology", 1, Decimal(12000), Decimal("0.48")),
        ("Government", 1, Decimal(8000), Decimal("0.32")),
        ("Diversified", 1, Decimal(4000), Decimal("0.16")),
    ]
    assert result.cash == Money(1000, "GBP")
    assert result.positions == 3
    assert result.share_of("Government") == Decimal("0.32")
    assert result.share_of("Energy") == 0


def test_currency_breakdown_includes_cash(small_valuation):
    result = exposure.by_currency(small_valuation)
    assert summary(result) == [
        ("GBP", 2, Decimal(17000), Decimal("0.68")),
        ("USD", 1, Decimal(8000), Decimal("0.32")),
    ]
    assert result.cash.is_zero()


def test_kind_breakdown_has_a_fixed_order(valuation):
    result = exposure.breakdown(valuation, exposure.KIND, top=1)  # fixed order: never folded
    assert [row.key for row in result.rows] == ["equity", "bond", "fund"]


def test_sample_rows_and_cash_add_up_to_nav(valuation):
    for dimension in exposure.DIMENSIONS.values():
        result = exposure.breakdown(valuation, dimension)
        total = sum(row.value.amount for row in result.rows) + result.cash.amount
        assert total == pytest.approx(valuation.nav.amount), dimension.name
        assert result.positions == len(valuation.positions)


def test_top_n_folds_small_sectors(valuation):
    result = exposure.breakdown(valuation, exposure.SECTOR, top=3)
    assert [row.key for row in result.rows][-1] == "Other"
    assert len(result.rows) == 4
    assert result.positions == len(valuation.positions)


def test_contributions_small_book(small_book, small_valuation):
    _, _, prices, fx = small_book
    parts = contributions(small_valuation, prices, fx, date(2026, 10, 29), exposure.SECTOR.key)
    # AAA went from 10 to 12: +2,000 GBP on a starting NAV of 23,000.
    assert parts["Technology"].contribution == Decimal(2000) / Decimal(23000)
    assert parts["Technology"].start_weight == Decimal(10000) / Decimal(23000)
    assert parts["Government"].contribution == 0
    assert parts[CASH_KEY].contribution == 0
    assert total_return(parts) == Decimal(2000) / Decimal(23000)
    by_currency = contributions(small_valuation, prices, fx, date(2026, 10, 29), exposure.CURRENCY.key,
                                cash_by_currency=True)
    assert CASH_KEY not in by_currency and set(by_currency) == {"GBP", "USD"}
    with pytest.raises(ValueError, match="must be before the valuation date"):
        contributions(small_valuation, prices, fx, date(2026, 10, 30), exposure.SECTOR.key)
