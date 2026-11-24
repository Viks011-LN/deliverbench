"""Read positions.json: one portfolio with its positions (as lots) and cash.

    {
      "portfolio": "GBL-BAL",
      "name": "Global Balanced",
      "cash": {"GBP": "182500.00", "USD": "64000.00"},
      "positions": [
        {"instrument": "ADZM",
         "lots": [{"date": "2025-11-04", "quantity": "1200", "price": "212.40"}]}
      ]
    }

Numbers may be JSON numbers or strings; strings are preferred because they
keep every digit. Keys starting with "_" are comments and are ignored; any
other unknown key is an error. Errors give the JSON path of the bad value,
for example ``positions[3].lots[0].quantity``.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from folio.data.business_days import parse_date
from folio.domain.money import check_currency, to_decimal
from folio.domain.portfolio import Portfolio
from folio.domain.positions import Lot, Position
from folio.errors import DataError

TOP_LEVEL_KEYS = {"portfolio", "name", "cash", "positions"}
POSITION_KEYS = {"instrument", "lots"}
LOT_KEYS = {"date", "quantity", "price"}


def load_portfolio(path) -> Portfolio:
    """Read positions.json at ``path``. Raises DataError with the JSON path of any bad value."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise DataError(f"positions file not found: {path}") from None
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(f"not valid JSON: {exc.msg}", source=path.name, line=exc.lineno) from None
    return parse_portfolio(document, source=path.name)


def parse_portfolio(document: Any, source: str = "<positions>") -> Portfolio:
    """Build a Portfolio from an already parsed JSON ``document``."""
    reader = _Reader(source)
    top = reader.mapping(document, "top level", TOP_LEVEL_KEYS, required={"portfolio", "positions"})
    code = reader.text(top["portfolio"], "portfolio")
    name = reader.text(top.get("name", code), "name")

    cash: dict[str, Decimal] = {}
    for currency, amount in sorted(reader.mapping(top.get("cash", {}), "cash").items()):
        where = f"cash.{currency}"
        try:
            check_currency(currency)
        except ValueError as exc:
            reader.fail(where, str(exc))
        cash[currency] = reader.number(amount, where)

    try:
        portfolio = Portfolio(code=code, name=name, cash=cash)
    except ValueError as exc:
        reader.fail("portfolio", str(exc))

    for index, entry in enumerate(reader.array(top["positions"], "positions")):
        where = f"positions[{index}]"
        position = reader.mapping(entry, where, POSITION_KEYS, required=POSITION_KEYS)
        instrument_id = reader.text(position["instrument"], f"{where}.instrument")
        lots = [
            _lot(reader, raw, f"{where}.lots[{lot_index}]")
            for lot_index, raw in enumerate(reader.array(position["lots"], f"{where}.lots"))
        ]
        try:
            portfolio.add_position(Position(instrument_id, tuple(lots)))
        except ValueError as exc:
            reader.fail(where, str(exc))
    return portfolio


def _lot(reader: "_Reader", raw: Any, where: str) -> Lot:
    lot = reader.mapping(raw, where, LOT_KEYS, required=LOT_KEYS)
    trade_date = reader.day(lot["date"], f"{where}.date")
    quantity = reader.number(lot["quantity"], f"{where}.quantity")
    price = reader.number(lot["price"], f"{where}.price")
    try:
        return Lot(trade_date, quantity, price)
    except ValueError as exc:
        reader.fail(where, str(exc))


class _Reader:
    """Typed access to parsed JSON that reports the path of anything wrong."""

    def __init__(self, source: str):
        self.source = source

    def fail(self, where: str, message: str) -> NoReturn:
        raise DataError(f"{where}: {message}", source=self.source)

    def mapping(self, value: Any, where: str, allowed: set[str] | None = None,
                required: set[str] = frozenset()) -> dict[str, Any]:
        if not isinstance(value, dict):
            self.fail(where, f"expected an object, got {type(value).__name__}")
        if allowed is not None:
            unknown = sorted(key for key in value if key not in allowed and not key.startswith("_"))
            if unknown:
                self.fail(where, f"unknown key {unknown[0]!r}; expected {', '.join(sorted(allowed))}")
        absent = sorted(required - set(value))
        if absent:
            self.fail(where, f"missing key {absent[0]!r}")
        return value

    def array(self, value: Any, where: str) -> list[Any]:
        if not isinstance(value, list):
            self.fail(where, f"expected a list, got {type(value).__name__}")
        if not value:
            self.fail(where, "is empty")
        return value

    def text(self, value: Any, where: str) -> str:
        if not isinstance(value, str) or not value.strip():
            self.fail(where, f"expected a non-empty string, got {value!r}")
        return value.strip()

    def number(self, value: Any, where: str) -> Decimal:
        try:
            return to_decimal(value, what="value")
        except (TypeError, ValueError) as exc:
            self.fail(where, str(exc))

    def day(self, value: Any, where: str) -> date:
        if not isinstance(value, str):
            self.fail(where, f"expected a date string, got {value!r}")
        try:
            return parse_date(value)
        except ValueError as exc:
            self.fail(where, str(exc))
