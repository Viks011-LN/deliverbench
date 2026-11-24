"""FIFO matching, realised P&L, cash and reconciliation.

The small cases use the instruments of the ``small_book`` fixture: AAA (a
GBP share), BBB (a USD bond, priced per 100) and CCC (a GBP fund), with
GBPUSD at 1.25 on 2026-10-29 and 2026-10-30.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.domain.money import Money, quantize
from folio.ledger.book import Ledger, load_ledger
from folio.ledger.cash import balances, statement, summarise
from folio.ledger.cash_flows_csv import CashFlow
from folio.ledger.fifo import Match, OpenLot, instrument_pnl, match_fifo, sector_pnl
from folio.ledger.reconcile import reconcile
from folio.ledger.trades_csv import Trade

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 30)
DAY_BEFORE = date(2026, 10, 29)


def trade(trade_id, day, side, instrument, quantity, price, fees="0", currency="GBP"):
    return Trade(trade_id=trade_id, trade_date=day, instrument_id=instrument, side=side,
                 quantity=Decimal(quantity), price=Decimal(price), currency=currency, fees=Decimal(fees))


def flow(day, currency, amount, kind, instrument="", note=""):
    return CashFlow(value_date=day, amount=Money(Decimal(amount), currency), kind=kind,
                    instrument_id=instrument, note=note)


@pytest.fixture(scope="module")
def sample_ledger(universe):
    return load_ledger(DATA_DIR, universe)


def test_a_sale_closes_the_oldest_lots_first(small_book):
    first, second = date(2026, 10, 1), date(2026, 10, 5)
    result = match_fifo([
        trade("T1", first, "buy", "AAA", "100", "10", fees="5"),
        trade("T2", second, "buy", "AAA", "100", "12"),
        trade("T3", DAY_BEFORE, "sell", "AAA", "150", "13", fees="15"),
    ], small_book[0])
    (sale,) = result.sales
    assert sale.matches == (Match("T1", first, Decimal(100), Decimal(1005)),
                            Match("T2", second, Decimal(50), Decimal(600)))
    # Proceeds 150 x 13 less 15 of fees; cost 1,000 plus 5 of fees, and half of 1,200.
    assert (sale.proceeds, sale.cost, sale.realised) == (Decimal(1935), Decimal(1605), Decimal(330))
    assert result.open_lots == {"AAA": (OpenLot("T2", second, "AAA", Decimal(50), Decimal(12), Decimal(600)),)}


def test_buying_fees_are_spread_over_the_units_without_dust(small_book):
    result = match_fifo([
        trade("T1", date(2026, 10, 1), "buy", "AAA", "3", "10", fees="1"),
        trade("T2", date(2026, 10, 2), "sell", "AAA", "1", "11"),
        trade("T3", date(2026, 10, 5), "sell", "AAA", "2", "11"),
    ], small_book[0])
    first, second = result.sales
    assert first.cost == Decimal(31) / 3
    assert first.cost + second.cost == Decimal(31)
    assert result.open_lots == {}


def test_selling_more_than_is_held_is_refused(small_book):
    with pytest.raises(ValueError, match="the sale of 150 AAA is more than the 100 held"):
        match_fifo([trade("T1", date(2026, 10, 1), "buy", "AAA", "100", "10"),
                    trade("T2", DAY_BEFORE, "sell", "AAA", "150", "10")], small_book[0])


def test_pnl_in_local_and_base_currency(small_book):
    universe, _, _, fx = small_book
    ledger = Ledger(universe, trades=(
        trade("T1", date(2026, 10, 1), "buy", "AAA", "100", "10"),
        trade("T2", date(2026, 10, 1), "buy", "BBB", "10000", "98", currency="USD"),
        trade("T3", DAY_BEFORE, "sell", "AAA", "40", "12"),
        trade("T4", AS_OF, "sell", "BBB", "4000", "101", currency="USD"),
    ), cash_flows=(
        flow(AS_OF, "USD", "250", "coupon", "BBB"),
        flow(AS_OF, "GBP", "50", "dividend", "CCC"),
        flow(AS_OF, "GBP", "-30", "fee", "CCC", note="platform fee"),
    ))
    result = match_fifo(ledger.trades, universe)
    aaa, bbb, ccc = instrument_pnl(ledger, result, fx, "GBP", AS_OF)
    assert (aaa.sold, aaa.realised, aaa.realised_base) == (Decimal(40), Money(80, "GBP"), Money(80, "GBP"))
    # Per 100 nominal: 4,000 bought at 98 and sold at 101 is USD 120, or GBP 96 at 1.25.
    assert (bbb.proceeds, bbb.cost, bbb.realised) == (Money(4040, "USD"), Money(3920, "USD"), Money(120, "USD"))
    assert (bbb.realised_base, bbb.income_base, bbb.total_base) == (
        Money(96, "GBP"), Money(200, "GBP"), Money(296, "GBP"))
    # A fee is not income, even when it names an instrument.
    assert (ccc.sold, ccc.income, ccc.total_base) == (0, Money(50, "GBP"), Money(50, "GBP"))

    since = instrument_pnl(ledger, result, fx, "GBP", AS_OF, since=AS_OF)
    assert [line.instrument.id for line in since] == ["BBB", "CCC"]
    sectors = sector_pnl(instrument_pnl(ledger, result, fx, "GBP", AS_OF), "GBP")
    assert [(s.sector, s.instruments, s.total_base) for s in sectors] == [
        ("Diversified", 1, Money(50, "GBP")), ("Government", 1, Money(296, "GBP")),
        ("Technology", 1, Money(80, "GBP"))]


def test_cash_balances_statement_and_summary(small_book):
    universe, _, _, fx = small_book
    ledger = Ledger(universe, trades=(
        trade("T1", date(2026, 10, 1), "buy", "AAA", "100", "10", fees="5"),
        trade("T2", DAY_BEFORE, "sell", "AAA", "40", "12", fees="2"),
    ), cash_flows=(
        flow(date(2026, 9, 30), "GBP", "2000", "subscription"),
        flow(DAY_BEFORE, "GBP", "-20", "fee", note="custody"),
        flow(DAY_BEFORE, "GBP", "-800", "fx", note="bought USD at 1.25"),
        flow(DAY_BEFORE, "USD", "1000", "fx", note="bought USD at 1.25"),
    ))
    assert balances(ledger, AS_OF) == {"GBP": Money(653, "GBP"), "USD": Money(1000, "USD")}
    assert balances(ledger, date(2026, 10, 1)) == {"GBP": Money(995, "GBP")}
    # Within a day, cash flows come before trades.
    assert [(movement.kind, movement.reference, balance.amount)
            for movement, balance in statement(ledger, "GBP", AS_OF)] == [
        ("subscription", "", 2000), ("buy", "T1", 995), ("fee", "custody", 975),
        ("fx", "bought USD at 1.25", 175), ("sell", "T2", 653)]

    gbp, usd = summarise(ledger, AS_OF, fx, "GBP")
    assert (gbp.trades, gbp.income, gbp.fees, gbp.capital, gbp.fx) == (
        Money(-520, "GBP"), Money(0, "GBP"), Money(-27, "GBP"), Money(2000, "GBP"), Money(-800, "GBP"))
    assert (gbp.balance, gbp.base_balance) == (Money(653, "GBP"), Money(653, "GBP"))
    assert (usd.balance, usd.base_balance) == (Money(1000, "USD"), Money(800, "GBP"))


def test_reconcile_lists_every_difference(small_book):
    universe, book, _, _ = small_book
    opened = date(2026, 1, 5)
    ledger = Ledger(universe, trades=(
        trade("T1", opened, "buy", "AAA", "1000", "10"),
        trade("T2", opened, "buy", "BBB", "10000", "100.5", currency="USD"),
        trade("T3", DAY_BEFORE, "buy", "AAA", "100", "12"),
    ), cash_flows=())
    result = reconcile(ledger, book, AS_OF)
    assert not result.ok
    assert [difference.format() for difference in result.differences] == [
        "DIFF AAA: open quantity 1,100 from trades.csv, 1,000 in positions.json",
        "DIFF AAA: open lot 2026-10-29 100 @ 12 in trades.csv only",
        "DIFF BBB: open lot 2026-01-05 10,000 @ 100.5 in trades.csv only",
        "DIFF BBB: open lot 2026-01-05 10,000 @ 100 in positions.json only",
        "DIFF CCC: 2,000 open in positions.json, no trades in trades.csv",
        "DIFF cash GBP: -11,200.00 in the ledger, 1,000.00 in positions.json",
        "DIFF cash USD: -10,050.00 in the ledger, 0.00 in positions.json",
    ]
    # Before T3 the lots of AAA agree; cash is left alone because the ledger runs on past that date.
    earlier = reconcile(ledger, book, date(2026, 10, 28))
    assert [difference.subject for difference in earlier.differences] == ["BBB", "BBB", "CCC"]
    assert earlier.currencies is None and "the ledger runs to 2026-10-29" in earlier.cash_note


def test_sample_fifo_matches(sample_ledger):
    result = match_fifo(sample_ledger.trades_between(None, AS_OF), sample_ledger.universe)
    frxl = [sale for sale in result.sales if sale.trade.instrument_id == "FRXL"]
    assert [[(match.buy_id, match.quantity) for match in sale.matches] for sale in frxl] == [
        [("T0065", 200)], [("T0065", 400), ("T0067", 300)], [("T0067", 100), ("T0068", 200)]]
    assert "FRXL" not in result.open_lots and "NYQV" not in result.open_lots
    (mxtb,) = result.open_lots["MXTB"]
    assert (mxtb.trade_id, mxtb.quantity, mxtb.price) == ("T0015", Decimal(160500), Decimal("4.427"))


def test_sample_realised_pnl(sample_ledger, fx):
    result = match_fifo(sample_ledger.trades_between(None, AS_OF), sample_ledger.universe)
    lines = {line.instrument.id: line for line in instrument_pnl(sample_ledger, result, fx, "GBP", AS_OF)}
    frxl = lines["FRXL"]
    assert (frxl.sold, frxl.proceeds.rounded(), frxl.cost.rounded()) == (
        Decimal(1200), Money(Decimal("431654.06"), "USD"), Money(Decimal("383357.59"), "USD"))
    assert frxl.realised.rounded() == Money(Decimal("48296.47"), "USD")
    assert lines["NYQV"].realised.rounded() == Money(Decimal("37349.91"), "USD")
    assert lines["MXTB"].realised_base.rounded() == Money(Decimal("403.32"), "GBP")
    assert lines["JGB30"].income == Money(342000, "JPY")


def test_sample_ledger_agrees_with_positions_json(sample_ledger, portfolio, fx, valuation):
    result = reconcile(sample_ledger, portfolio, AS_OF)
    assert result.ok, [difference.format() for difference in result.differences]
    assert (result.instruments, result.currencies) == (40, 4)
    base_cash = sum((summary.base_balance.amount for summary in summarise(sample_ledger, AS_OF, fx, "GBP")),
                    Decimal(0))
    assert quantize(base_cash, 2) == quantize(valuation.cash_total.amount, 2)
