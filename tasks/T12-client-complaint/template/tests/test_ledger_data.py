import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.domain.money import Money
from folio.errors import DataError
from folio.ledger.book import Ledger, cross_check, load_ledger
from folio.ledger.cash_flows_csv import KINDS, parse_cash_flows
from folio.ledger.trades_csv import parse_trades

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRADES = "trade_id,date,instrument,side,quantity,price,fees,currency\n"
FLOWS = "date,currency,amount,kind,instrument,note\n"


def test_sample_ledger(universe):
    ledger = load_ledger(DATA_DIR, universe)
    assert (len(ledger.trades), len(ledger.cash_flows)) == (76, 100)
    assert ledger.trades[0].trade_id == "T0001"
    assert ledger.last_date() == date(2026, 10, 30)
    assert {flow.kind for flow in ledger.cash_flows} == set(KINDS)


def test_every_booked_lot_is_a_trade(universe, portfolio):
    ledger = load_ledger(DATA_DIR, universe)
    traded = {(trade.instrument_id, trade.trade_date, trade.signed_quantity, trade.price) for trade in ledger.trades}
    booked = {(instrument_id, lot.trade_date, lot.quantity, lot.price)
              for instrument_id, position in portfolio.positions.items() for lot in position.lots}
    assert booked <= traded
    # The rest are round trips, closed before the valuation date.
    assert sorted({instrument_id for instrument_id, *_ in traded - booked}) == ["FRXL", "NYQV"]


def test_reading_trades():
    first, second = parse_trades(io.StringIO(
        "Trade_ID,date,instrument,side,quantity,price,currency,venue\n"
        "A1,2026-10-29,AAA,BUY,100,10.5,gbp,XLON\n"
        "\n"
        "A2,2026-10-30,AAA,sell,40,11,GBP,\n"))
    assert (first.side, first.currency, first.price, first.fees, first.line) == ("buy", "GBP", Decimal("10.5"), 0, 2)
    assert (second.signed_quantity, second.line) == (Decimal(-40), 4)


@pytest.mark.parametrize("text, message", [
    ("trade_id,date,side\n", "t.csv:1: missing column(s): instrument, quantity, price, currency"),
    (TRADES + "A1,2026-10-31,AAA,buy,1,1,0,GBP\n", "t.csv:2: trade A1: 2026-10-31 is a Saturday"),
    (TRADES + "A1,2026-10-30,AAA,short,1,1,0,GBP\n", "t.csv:2: trade A1: side must be buy or sell, not 'short'"),
    (TRADES + "A1,2026-10-30,AAA,buy,-5,1,0,GBP\n", "t.csv:2: trade A1: quantity must be positive"),
    (TRADES + "A1,2026-10-30,AAA,buy,ten,1,0,GBP\n", "t.csv:2: trade A1: quantity 'ten' is not a number"),
    (TRADES + "A1,2026-10-30,AAA,buy,1,1,-2,GBP\n", "t.csv:2: trade A1: fees -2 are negative"),
    (TRADES + "A1,2026-10-30,AAA,buy,1,1,0,GBP\nA1,2026-10-30,AAA,buy,1,1,0,GBP\n",
     "t.csv:3: trade id A1 is already used on line 2"),
    (TRADES + "A1,2026-10-30,AAA,buy,1,1,0,GBP\nA2,2026-10-29,AAA,buy,1,1,0,GBP\n",
     "t.csv:3: dates must not go backwards: 2026-10-29 comes after 2026-10-30"),
    (TRADES + "A1,2026-10-30,AAA,buy,1,1,0,GBP,XLON\n", "t.csv:2: row has more cells than the header"),
])
def test_trade_errors_name_file_and_line(text, message):
    with pytest.raises(DataError) as caught:
        parse_trades(io.StringIO(text), source="t.csv")
    assert str(caught.value).startswith(message)


def test_reading_cash_flows():
    (flow,) = parse_cash_flows(io.StringIO("date,currency,amount,kind\n2026-10-30,usd,-12.5,Interest\n"))
    assert (flow.value_date, flow.amount, flow.kind) == (date(2026, 10, 30), Money(Decimal("-12.5"), "USD"),
                                                         "interest")
    assert (flow.instrument_id, flow.note, flow.line) == ("", "", 2)


@pytest.mark.parametrize("text, message", [
    (FLOWS + "2026-10-30,GBP,10,gift,,\n", "c.csv:2: unknown kind 'gift'"),
    (FLOWS + "2026-10-30,GBP,10,dividend,,\n", "c.csv:2: a dividend needs an instrument"),
    (FLOWS + "2026-10-30,GBP,-10,dividend,AAA,\n", "c.csv:2: a dividend must be positive (money in)"),
    (FLOWS + "2026-10-30,GBP,10,fee,,custody\n", "c.csv:2: a fee must be negative (money out)"),
    (FLOWS + "2026-10-30,GBP,10,subscription,AAA,\n", "c.csv:2: a subscription is not paid on an instrument"),
    (FLOWS + "2026-10-30,GBP,0,interest,,\n", "c.csv:2: interest amount is zero"),
    (FLOWS + "2026-10-30,GBPX,1,interest,,\n", "c.csv:2: invalid currency code 'GBPX'"),
    (FLOWS + "2026-10-30,GBP,1,interest,,\n2026-10-29,GBP,1,interest,,\n", "c.csv:3: dates must not go backwards"),
])
def test_cash_flow_errors_name_file_and_line(text, message):
    with pytest.raises(DataError) as caught:
        parse_cash_flows(io.StringIO(text), source="c.csv")
    assert str(caught.value).startswith(message)


@pytest.mark.parametrize("trades, flows, message", [
    ("A1,2026-10-30,ZZZ,buy,1,1,0,GBP\n", "", "trades.csv:2: trade A1: ZZZ is not in instruments.csv"),
    ("A1,2026-10-30,BBB,buy,1,1,0,GBP\n", "", "trades.csv:2: trade A1: BBB trades in USD, not GBP"),
    ("A1,2026-10-29,AAA,buy,5,1,0,GBP\nA2,2026-10-30,AAA,sell,8,1,0,GBP\n", "",
     "trades.csv:3: trade A2: the sale of 8 AAA on 2026-10-30 is more than the 5 held"),
    ("", "2026-10-30,GBP,5,coupon,BBB,\n", "cash_flows.csv:2: BBB pays in USD, but this coupon is in GBP"),
    ("", "2026-10-30,GBP,-5,fee,ZZZ,\n", "cash_flows.csv:2: ZZZ is not in instruments.csv"),
])
def test_cross_checks_name_file_and_line(small_book, trades, flows, message):
    ledger = Ledger(small_book[0], parse_trades(io.StringIO(TRADES + trades)),
                    parse_cash_flows(io.StringIO(FLOWS + flows)))
    with pytest.raises(DataError) as caught:
        cross_check(ledger)
    assert str(caught.value).startswith(message)


def test_both_ledger_files_are_needed(tmp_path, universe):
    with pytest.raises(DataError, match="has no trades.csv, cash_flows.csv, which the ledger needs"):
        load_ledger(tmp_path, universe)
    (tmp_path / "trades.csv").write_text(TRADES)
    with pytest.raises(DataError, match="has no cash_flows.csv"):
        load_ledger(tmp_path, universe)
    (tmp_path / "cash_flows.csv").write_text(FLOWS)
    assert load_ledger(tmp_path, universe).last_date() is None
