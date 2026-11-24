"""Regression test for CS-2291: a trade counts in the figures of its own day.

The client's statement for 30 September valued the book as it stood before that day's sale, so it did not agree
with the trade ledger they are sent, and `folio.ledger reconcile` reported a difference that was not there.
A position as of a date includes that day's trades (docs/ARCHITECTURE.md, Domain model); Position.lots_as_of()
kept only the lots dated before the date.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from folio.cli import main as folio_main
from folio.domain.positions import Lot, Position
from folio.ledger.cli import main as ledger_main

CLIENT_DATA = Path(__file__).resolve().parent.parent / "support" / "CS-2291" / "data"


def run(main, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    status = main(["--data-dir", str(CLIENT_DATA), *argv], out=out, err=io.StringIO())
    return status, out.getvalue()


def test_a_position_counts_the_trades_of_its_own_day():
    day = date(2026, 9, 30)
    position = Position("AAA", (Lot(date(2026, 9, 1), Decimal(1000), Decimal(10)),
                                Lot(day, Decimal(500), Decimal(13)),
                                Lot(date(2026, 10, 1), Decimal(-300), Decimal(12))))
    assert position.quantity(date(2026, 9, 29)) == 1000
    assert position.quantity(day) == 1500
    assert position.average_price(day) == Decimal(11)
    assert position.quantity(date(2026, 10, 1)) == 1200
    closed = Position("BBB", (Lot(date(2026, 9, 1), Decimal(10), Decimal(1)), Lot(day, Decimal(-10), Decimal(1))))
    assert closed.is_open(date(2026, 9, 29))
    assert not closed.is_open(day)


def test_the_statement_counts_the_sale_made_on_its_date():
    status, out = run(folio_main, "export", "--format", "csv", "--as-of", "2026-09-30")
    assert status == 0
    rows = {row["instrument"]: row for row in csv.DictReader(io.StringIO(out))}
    assert rows["GRBY"]["quantity"] == "12200"


def test_the_ledger_and_the_positions_agree_on_the_statement_date():
    status, out = run(ledger_main, "reconcile", "--as-of", "2026-09-30")
    assert status == 0, out
    assert out.startswith("OK: ")
