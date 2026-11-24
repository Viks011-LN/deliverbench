"""CS-2291: a trade dated on the valuation date is part of the book on that date.

Prices are closing prices, so a position "as of" a date is the book at that
day's close and includes the trades of that day (docs/ARCHITECTURE.md, Domain
model). The ledger already counted them; the positions did not, so a sale made
on the statement date stayed in the statement's holdings while its proceeds
were already in the cash, and the statement was too high by the value of the
shares sold.
"""

import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from folio.calc.valuation import value_portfolio
from folio.cli import main as folio_main
from folio.domain.instruments import Equity, Universe
from folio.domain.positions import Lot, Position
from folio.ledger.cli import main as ledger_main

ROOT = Path(__file__).resolve().parent.parent
CASE = ROOT / "support" / "CS-2291"
CASE_DATA = CASE / "data"
STATEMENT_DATE = "2026-09-30"


def lot(day, quantity, price):
    return Lot(date.fromisoformat(day), Decimal(quantity), Decimal(price))


def run(main, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err, today=date(2026, 10, 30))
    return code, out.getvalue(), err.getvalue()


def statement_line(text, instrument_id):
    """The cells of one row of `folio value`: columns are two or more spaces apart, names have single spaces."""
    return next(re.split(r"\s{2,}", line.strip()) for line in text.splitlines()
                if line.startswith(instrument_id + " "))


def test_a_sale_counts_on_its_own_trade_date():
    position = Position("X", (lot("2026-01-10", "100", "10"), lot("2026-03-02", "-40", "12")))
    assert position.quantity(date(2026, 3, 1)) == 100
    assert position.quantity(date(2026, 3, 2)) == 60
    assert position.quantity(date(2026, 3, 3)) == 60
    assert [held.quantity for held in position.lots_as_of(date(2026, 3, 2))] == [Decimal(100), Decimal(-40)]
    assert position.average_price(date(2026, 3, 2)) == Decimal(10)


def test_a_buy_counts_on_its_own_trade_date():
    position = Position("X", (lot("2026-01-10", "100", "10"), lot("2026-03-02", "100", "14")))
    assert position.quantity(date(2026, 3, 2)) == 200
    assert position.average_price(date(2026, 3, 2)) == Decimal(12)
    opened = Position("Y", (lot("2026-03-02", "50", "8"),))
    assert not opened.is_open(date(2026, 3, 1))
    assert opened.is_open(date(2026, 3, 2))
    assert opened.quantity(date(2026, 3, 2)) == 50


def test_a_position_closed_on_the_valuation_date_is_not_held(small_book):
    universe, book, prices, fx = small_book
    as_of = date(2026, 10, 30)
    # DDD is bought in January and sold in full on the valuation date; it has no price, and needs none.
    universe.add(Equity("DDD", "Delta plc", "Energy", "GBP"))
    book.add_position(Position("DDD", (lot("2026-01-05", "500", "3"), lot("2026-10-30", "-500", "3"))))
    assert "DDD" not in [holding.instrument.id for holding in book.holdings(universe, as_of)]
    valuation = value_portfolio(book, universe, prices, fx, as_of, base_currency="GBP", stale_after_days=3)
    assert [line.instrument.id for line in valuation.positions] == ["AAA", "BBB", "CCC"]
    assert valuation.nav.amount == Decimal(25000)


def test_cs2291_statement_counts_the_sale_made_on_the_statement_date():
    code, out, err = run(folio_main, "value", "--data-dir", str(CASE_DATA), "--as-of", STATEMENT_DATE)
    assert code == 0, err
    # GRBY: 5,700 + 14,000 bought, 7,500 sold on 30 September (T0068).
    grby = statement_line(out, "GRBY")
    assert grby[4] == "12,200"
    assert grby[6] == "235,826.00"  # 12,200 x 19.33
    # The client's figure: the statement sent was 19,270,675.16, 7,500 x 19.33 = 144,975.00 too high.
    assert statement_line(out, "Total")[1] == "19,125,700.16"


def test_cs2291_holdings_agree_with_the_ledger_on_the_statement_date():
    code, out, err = run(ledger_main, "reconcile", "--data-dir", str(CASE_DATA), "--as-of", STATEMENT_DATE)
    assert (code, out, err) == (
        0, f"OK: 39 instruments and 4 cash balances agree with positions.json on {STATEMENT_DATE}\n", "")


def test_cs2291_only_the_statement_date_changes():
    # The day before the sale the book held all 19,700, and the ledger agrees.
    code, out, _ = run(folio_main, "value", "--data-dir", str(CASE_DATA), "--as-of", "2026-09-29")
    assert code == 0
    assert statement_line(out, "GRBY")[4] == "19,700"
    # ADZM's third lot was bought on 15 September: held on that date, not the day before.
    _, out, _ = run(folio_main, "value", "--data-dir", str(CASE_DATA), "--as-of", "2026-09-15")
    assert statement_line(out, "ADZM")[4] == "6,050"
    _, out, _ = run(folio_main, "value", "--data-dir", str(CASE_DATA), "--as-of", "2026-09-14")
    assert statement_line(out, "ADZM")[4] == "4,540"
