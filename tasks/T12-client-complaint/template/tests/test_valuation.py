from datetime import date
from decimal import Decimal

import pytest

from folio.calc import fees
from folio.calc.valuation import resolve_as_of, value_portfolio
from folio.domain.money import Money
from folio.errors import ValuationError

AS_OF = date(2026, 10, 30)


def test_small_book_values_and_weights(small_valuation):
    v = small_valuation
    assert v.nav == Money(25000, "GBP")
    assert [line.instrument.id for line in v.positions] == ["AAA", "BBB", "CCC"]
    bond = v.position("BBB")
    assert bond.local_value == Money(10000, "USD")
    assert bond.fx_rate == Decimal("0.8")
    assert bond.base_value == Money(8000, "GBP")
    assert [line.weight for line in v.positions] == [Decimal("0.48"), Decimal("0.32"), Decimal("0.16")]
    assert v.cash[0].weight == Decimal("0.04")
    assert v.invested + v.cash_total == v.nav


def test_unrealised_on_cost(small_valuation):
    equity = small_valuation.position("AAA")
    assert equity.cost_value == Money(10000, "GBP")
    assert equity.unrealised == Money(2000, "GBP")
    assert equity.unrealised_pct == Decimal("0.2")


def test_sample_valuation(valuation, portfolio):
    assert valuation.as_of == AS_OF
    assert len(valuation.positions) == 38
    ids = [line.instrument.id for line in valuation.positions]
    assert ids == sorted(ids)
    assert "NYQV" not in ids and "FRXL" not in ids  # sold in August / never bought
    total = sum(line.weight for line in valuation.positions) + sum(cash.weight for cash in valuation.cash)
    assert abs(total - 1) < Decimal("1e-20")
    assert not valuation.stale_positions()


def test_quantities_follow_the_valuation_date(universe, portfolio, prices, fx):
    before = value_portfolio(portfolio, universe, prices, fx, date(2026, 9, 14), base_currency="GBP",
                             stale_after_days=3)
    after = value_portfolio(portfolio, universe, prices, fx, date(2026, 9, 16), base_currency="GBP",
                            stale_after_days=3)
    assert after.position("ADZM").quantity - before.position("ADZM").quantity == 1510
    assert before.position("PCRF").stale  # month-end price from 2026-08-28
    with pytest.raises(KeyError, match="holds no NYQV"):
        after.position("NYQV")


def test_matured_bond_must_be_redeemed(small_book):
    universe, book, prices, fx = small_book
    with pytest.raises(ValuationError, match="BBB matured on 2030-01-01"):
        value_portfolio(book, universe, prices, fx, date(2030, 1, 2), base_currency="GBP", stale_after_days=3)


def test_resolve_as_of(prices):
    assert resolve_as_of(date(2026, 10, 30), prices) == (date(2026, 10, 30), None)
    day, note = resolve_as_of(date(2026, 11, 19), prices)
    assert day == date(2026, 10, 30) and "last date in the price file" in note
    day, note = resolve_as_of(date(2026, 10, 25), prices)
    assert day == date(2026, 10, 23) and "not a business day" in note
    with pytest.raises(ValuationError, match="first prices are for 2026-06-01"):
        resolve_as_of(date(2026, 5, 29), prices)


def test_fund_costs(small_valuation):
    costs = fees.fund_costs(small_valuation)
    assert [cost.line.instrument.id for cost in costs] == ["CCC"]
    assert fees.total_fund_cost(small_valuation) == Money(40, "GBP")
    assert fees.cost_ratio(small_valuation) == Decimal("0.0016")
    assert fees.accrue(Decimal("0.01"), Decimal(36500), date(2026, 1, 1), date(2026, 1, 11)) == Decimal(10)
    with pytest.raises(ValueError, match="unknown day count"):
        fees.accrue(Decimal("0.01"), Decimal(1), date(2026, 1, 1), date(2026, 1, 2), basis="30/360")
