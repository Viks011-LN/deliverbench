"""Read trades.csv: one row per trade, in the order the trades were done.

    trade_id,date,instrument,side,quantity,price,fees,currency
    T0002,2024-11-12,CNZA,buy,6120,38.19,116.86,EUR

Quantities are always positive and ``side`` (buy or sell) gives the
direction, so a dropped minus sign cannot turn a sale into a purchase.
Prices are quoted like the instrument, per 100 nominal for bonds, exactly as
in positions.json. Fees are in the trade currency; a blank cell means none.

The file order is the trade order. FIFO matches each sale against the buys
above it, so dates must not go backwards; trades on the same day keep their
file order. Dates must be business days. Columns the ledger does not know
are ignored, blank lines are skipped and errors name the file and line.

Whether the instrument exists and trades in the currency given is checked
in ledger/book.py, which has instruments.csv to hand.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from folio.data.business_days import is_business_day, parse_date
from folio.domain.money import check_currency, to_decimal
from folio.errors import DataError

REQUIRED_COLUMNS = ("trade_id", "date", "instrument", "side", "quantity", "price", "currency")
SIDES = ("buy", "sell")


@dataclass(frozen=True)
class Trade:
    """One trade. ``quantity`` is always positive; ``side`` says which way it went."""

    trade_id: str
    trade_date: date
    instrument_id: str
    side: str
    quantity: Decimal
    price: Decimal              # quoted like the instrument (per 100 nominal for bonds)
    currency: str
    fees: Decimal = Decimal(0)  # in ``currency``
    line: int | None = field(default=None, compare=False)  # where it was read, for error messages

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError(f"trade {self.trade_id}: side must be buy or sell, not {self.side!r}")
        if self.quantity <= 0:
            raise ValueError(f"trade {self.trade_id}: quantity must be positive, got {self.quantity}")
        # Zero is allowed, as for a lot in positions.json: shares received for nothing.
        if self.price < 0:
            raise ValueError(f"trade {self.trade_id}: price {self.price} is negative")
        if self.fees < 0:
            raise ValueError(f"trade {self.trade_id}: fees {self.fees} are negative")
        check_currency(self.currency)

    @property
    def is_buy(self) -> bool:
        return self.side == "buy"

    @property
    def signed_quantity(self) -> Decimal:
        """Positive for a buy and negative for a sale, like a lot in positions.json."""
        return self.quantity if self.is_buy else -self.quantity


def load_trades(path) -> tuple[Trade, ...]:
    """Read trades.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return parse_trades(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"trade file not found: {path}") from None


def csv_rows(lines: Iterable[str], source: str, required: Sequence[str]) -> Iterator[tuple[int, dict[str, str]]]:
    """(line number, cells by lower-case column name) for each non-blank row of a CSV file.

    Shared with cash_flows_csv.py. Refuses a header without the ``required``
    columns and a row with more cells than the header; cells are stripped and
    missing trailing cells read as blank.
    """
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        raise DataError("file is empty", source=source)
    header = [name.strip().lower() for name in reader.fieldnames]
    missing = [column for column in required if column not in header]
    if missing:
        raise DataError(f"missing column(s): {', '.join(missing)}", source=source, line=1)
    reader.fieldnames = header
    for row in reader:
        if any(cell.strip() for cell in row.get(None) or ()):
            raise DataError(f"row has more cells than the header has columns ({len(header)})",
                            source=source, line=reader.line_num)
        values = {key: (value or "").strip() for key, value in row.items() if key is not None}
        if any(values.values()):
            yield reader.line_num, values


def parse_trades(lines: Iterable[str], source: str = "<trades>") -> tuple[Trade, ...]:
    """Parse CSV ``lines`` into trades in file order; ``source`` names the file in errors."""
    trades: list[Trade] = []
    first_line: dict[str, int] = {}
    for line, values in csv_rows(lines, source, REQUIRED_COLUMNS):
        try:
            trade = _build(values, line)
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if trade.trade_id in first_line:
            raise DataError(f"trade id {trade.trade_id} is already used on line {first_line[trade.trade_id]}",
                            source=source, line=line)
        if trades and trade.trade_date < trades[-1].trade_date:
            raise DataError(f"dates must not go backwards: {trade.trade_date} comes after {trades[-1].trade_date}",
                            source=source, line=line)
        first_line[trade.trade_id] = line
        trades.append(trade)
    return tuple(trades)


def _build(values: dict[str, str], line: int) -> Trade:
    trade_id = values["trade_id"]
    if not trade_id:
        raise ValueError("trade_id is empty")
    day = parse_date(values["date"])
    if not is_business_day(day):
        raise ValueError(f"trade {trade_id}: {day} is a {day.strftime('%A')}; trades are done on business days")
    if not values["instrument"]:
        raise ValueError(f"trade {trade_id}: instrument is empty")
    fees = values.get("fees", "")
    return Trade(
        trade_id=trade_id,
        trade_date=day,
        instrument_id=values["instrument"],
        side=values["side"].lower(),
        quantity=to_decimal(values["quantity"], what=f"trade {trade_id}: quantity"),
        price=to_decimal(values["price"], what=f"trade {trade_id}: price"),
        currency=values["currency"].upper(),
        fees=to_decimal(fees, what=f"trade {trade_id}: fees") if fees else Decimal(0),
        line=line,
    )
