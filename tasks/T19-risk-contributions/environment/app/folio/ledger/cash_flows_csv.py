"""Read cash_flows.csv: cash that comes in or goes out without a trade.

    date,currency,amount,kind,instrument,note
    2026-06-12,USD,2360.80,dividend,ADZM,quarterly dividend 0.52

Amounts are signed from the portfolio's side: money in is positive, money
out negative. ``kind`` says what the money was for, and KINDS gives each
kind the sign it must have and whether it belongs to an instrument: a
dividend is paid on a share, a custody fee is not paid on anything.

A currency conversion is two ``fx`` rows on the same day, one in each
currency. The ledger does not tie them together; the rate is whatever the
two amounts say, and the note is the place to write it down.

The CSV rules are those of trades.csv, and as there dates must not go
backwards. The instrument and note columns may be left out or blank.
Whether an instrument exists and pays in the currency given is checked in
ledger/book.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from folio.data.business_days import parse_date
from folio.domain.money import Money, to_decimal
from folio.errors import DataError
from folio.ledger.trades_csv import csv_rows

REQUIRED_COLUMNS = ("date", "currency", "amount", "kind")


@dataclass(frozen=True)
class KindRule:
    sign: int        # +1 money in only, -1 money out only, 0 either way
    instrument: str  # "required", "optional" or "never"


KINDS = {
    "subscription": KindRule(+1, "never"),
    "redemption": KindRule(-1, "never"),
    "dividend": KindRule(+1, "required"),
    "coupon": KindRule(+1, "required"),
    "interest": KindRule(0, "never"),  # negative when the bank charges for holding cash
    "fee": KindRule(-1, "optional"),
    "fx": KindRule(0, "never"),
}

# Paid by an instrument to whoever holds it; pnl reports these per instrument.
INCOME_KINDS = ("dividend", "coupon")


@dataclass(frozen=True)
class CashFlow:
    """One movement of cash that is not a trade."""

    value_date: date
    amount: Money  # signed: positive in, negative out
    kind: str
    instrument_id: str = ""
    note: str = ""
    line: int | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        try:
            rule = KINDS[self.kind]
        except KeyError:
            raise ValueError(f"unknown kind {self.kind!r}; expected one of: {', '.join(sorted(KINDS))}") from None
        if self.amount.is_zero():
            raise ValueError(f"{self.kind} amount is zero")
        if rule.sign * self.amount.amount < 0:
            direction = "positive (money in)" if rule.sign > 0 else "negative (money out)"
            raise ValueError(f"a {self.kind} must be {direction}, got {self.amount.amount}")
        if rule.instrument == "required" and not self.instrument_id:
            raise ValueError(f"a {self.kind} needs an instrument")
        if rule.instrument == "never" and self.instrument_id:
            raise ValueError(f"a {self.kind} is not paid on an instrument, but {self.instrument_id} is given")

    @property
    def currency(self) -> str:
        return self.amount.currency


def load_cash_flows(path) -> tuple[CashFlow, ...]:
    """Read cash_flows.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return parse_cash_flows(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"cash flow file not found: {path}") from None


def parse_cash_flows(lines: Iterable[str], source: str = "<cash flows>") -> tuple[CashFlow, ...]:
    """Parse CSV ``lines`` into cash flows in file order."""
    flows: list[CashFlow] = []
    for line, values in csv_rows(lines, source, REQUIRED_COLUMNS):
        try:
            flow = CashFlow(
                value_date=parse_date(values["date"]),
                amount=Money(to_decimal(values["amount"]), values["currency"].upper()),
                kind=values["kind"].lower(),
                instrument_id=values.get("instrument", ""),
                note=values.get("note", ""),
                line=line,
            )
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if flows and flow.value_date < flows[-1].value_date:
            raise DataError(f"dates must not go backwards: {flow.value_date} comes after {flows[-1].value_date}",
                            source=source, line=line)
        flows.append(flow)
    return tuple(flows)
