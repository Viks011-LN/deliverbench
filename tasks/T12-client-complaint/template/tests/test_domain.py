from datetime import date
from decimal import Decimal

import pytest

from folio.domain.instruments import Bond, Equity, Fund, Universe, make_instrument
from folio.domain.portfolio import Portfolio
from folio.domain.positions import Lot, Position


def lot(day, quantity, price):
    return Lot(date.fromisoformat(day), Decimal(quantity), Decimal(price))


def test_market_value_depends_on_kind():
    equity = Equity("EQ", "Equity", "Energy", "GBP")
    bond = Bond("BD", "Bond", "Government", "GBP", maturity=date(2027, 1, 1))
    assert equity.market_value(Decimal(100), Decimal("12.5")) == Decimal("1250")
    assert bond.market_value(Decimal(100000), Decimal("98.5")) == Decimal("98500")
    assert bond.is_matured(date(2027, 1, 1)) and not bond.is_matured(date(2026, 12, 31))


@pytest.mark.parametrize("build, message", [
    (lambda: Equity("A B", "Name", "Energy", "GBP"), "invalid instrument id"),
    (lambda: Equity("X", "Name", "Energy", "gbp"), "instrument X: invalid currency code"),
    (lambda: Bond("BD", "Bond", "Government", "GBP"), "maturity is required"),
    (lambda: Bond("BD", "B", "Government", "GBP", coupon_rate=Decimal("4.25"), maturity=date(2030, 1, 1)),
     "coupon_rate"),
    (lambda: Fund("F", "Fund", "Diversified", "GBP", expense_ratio=Decimal("0.75")), "expense_ratio"),
    (lambda: make_instrument("swap", id="S", name="S", sector="Rates", currency="EUR"), "unknown instrument kind"),
])
def test_instrument_validation(build, message):
    with pytest.raises(ValueError, match=message):
        build()


def test_universe_is_ordered_and_rejects_duplicates():
    universe = Universe([Equity("ZZZ", "Z", "Energy", "GBP"),
                         Bond("AAA", "A", "Consumer", "GBP", issuer="ZZZ", maturity=date(2030, 1, 1))])
    assert [instrument.id for instrument in universe] == ["AAA", "ZZZ"]
    assert universe["AAA"].issuer_key == "ZZZ" and universe["ZZZ"].issuer_key == "ZZZ"
    with pytest.raises(ValueError, match="duplicate instrument id AAA"):
        universe.add(Equity("AAA", "A", "Consumer", "GBP"))
    with pytest.raises(KeyError, match="unknown instrument 'NOPE'"):
        universe["NOPE"]


def test_position_quantity_and_average_cost_as_of():
    position = Position("X", (
        lot("2026-03-01", "100", "12"),
        lot("2026-01-10", "100", "10"),   # out of order on purpose
        lot("2026-05-01", "-50", "15"),
    ))
    assert position.first_trade_date == date(2026, 1, 10)
    assert position.quantity(date(2026, 2, 1)) == 100
    assert position.quantity() == 150
    assert position.average_price() == Decimal(11)  # a sale does not change average cost
    assert position.average_price(date(2025, 12, 31)) is None


def test_closed_position_and_short_sale():
    closed = Position("X", (lot("2026-01-10", "100", "10"), lot("2026-02-10", "-100", "11")))
    assert not closed.is_open() and closed.average_price() is None
    with pytest.raises(ValueError, match="short positions are not supported"):
        Position("X", (lot("2026-01-10", "100", "10"), lot("2026-02-10", "-150", "11")))


def test_portfolio_holdings():
    universe = Universe([Equity("AAA", "A", "Consumer", "GBP"), Equity("BBB", "B", "Energy", "GBP")])
    book = Portfolio("BOOK-1", "Book", cash={"USD": Decimal(0), "GBP": Decimal(50)})
    book.add_position(Position("BBB", (lot("2026-01-10", "10", "5"),)))
    book.add_position(Position("AAA", (lot("2026-03-10", "20", "4"),)))
    assert [h.instrument.id for h in book.holdings(universe, date(2026, 4, 1))] == ["AAA", "BBB"]
    assert [h.instrument.id for h in book.holdings(universe, date(2026, 2, 1))] == ["BBB"]
    assert [m.currency for m in book.cash_balances()] == ["GBP"]
    with pytest.raises(ValueError, match="more than one position in AAA"):
        book.add_position(Position("AAA", (lot("2026-03-11", "1", "4"),)))
    book.add_position(Position("CCC", (lot("2026-03-11", "1", "4"),)))
    with pytest.raises(ValueError, match="not in the instrument file: CCC"):
        book.holdings(universe, date(2026, 4, 1))
