"""Read instruments.csv into a Universe.

Required columns: id, name, kind, sector, currency.
Optional columns: country, issuer; coupon_rate and maturity for bonds;
expense_ratio for funds.

Any other column is ignored, so the file can carry fields that folio does
not use (yet). Blank lines and rows whose id starts with '#' are skipped.
Errors name the file and line.
"""

import csv
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, Optional

from folio.data.business_days import parse_date
from folio.domain.instruments import KINDS, Instrument, Universe, make_instrument
from folio.domain.money import to_decimal
from folio.errors import DataError

REQUIRED_COLUMNS = ("id", "name", "kind", "sector", "currency")

# Columns that only make sense for one kind. A value in one of these on a row
# of another kind is an error, because it usually means a shifted row.
KIND_ONLY_COLUMNS = {
    "coupon_rate": "bond",
    "maturity": "bond",
    "expense_ratio": "fund",
}


def load_instruments(path) -> Universe:
    """Read instruments.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:  # utf-8-sig: Excel adds a BOM
            return parse_instruments(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"instrument file not found: {path}") from None


def parse_instruments(lines: Iterable[str], source: str = "<instruments>") -> Universe:
    """Parse CSV ``lines``; ``source`` is the name used in error messages."""
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        raise DataError("file is empty", source=source)
    header = [name.strip() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise DataError(f"missing column(s): {', '.join(missing)}", source=source, line=1)
    reader.fieldnames = header

    universe = Universe()
    for row in reader:
        line = reader.line_num
        # Trailing empty cells (a habit of spreadsheet exports) are fine.
        if any(cell.strip() for cell in row.get(None) or ()):
            raise DataError(f"row has more cells than the header has columns ({len(header)})",
                            source=source, line=line)
        values = {key: (value or "").strip() for key, value in row.items() if key is not None}
        if not any(values.values()) or values["id"].startswith("#"):
            continue
        try:
            instrument = _build(values)
        except (ValueError, TypeError) as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if instrument.id in universe:
            raise DataError(f"duplicate instrument id {instrument.id}", source=source, line=line)
        universe.add(instrument)

    if not len(universe):
        raise DataError("no instruments in file", source=source)
    return universe


def _build(values: Dict[str, str]) -> Instrument:
    kind = values["kind"].lower()
    if kind not in KINDS:
        raise ValueError(f"unknown kind {values['kind']!r}; expected one of: {', '.join(KINDS)}")
    for column, only_for in sorted(KIND_ONLY_COLUMNS.items()):
        if values.get(column) and kind != only_for:
            raise ValueError(f"{values['id']}: {column} is only valid for kind {only_for}, not {kind}")

    fields = {
        "id": values["id"],
        "name": values["name"],
        "sector": values["sector"],
        "currency": values["currency"].upper(),
        "country": values.get("country", ""),
        "issuer": values.get("issuer", ""),
    }
    if kind == "bond":
        fields["coupon_rate"] = _decimal(values, "coupon_rate", default=Decimal(0))
        maturity = values.get("maturity", "")
        if not maturity:
            raise ValueError(f"{values['id']}: a bond needs a maturity")
        fields["maturity"] = parse_date(maturity, what="maturity")
    elif kind == "fund":
        fields["expense_ratio"] = _decimal(values, "expense_ratio", default=Decimal(0))
    return make_instrument(kind, **fields)


def _decimal(values: Dict[str, str], column: str, default: Optional[Decimal] = None) -> Decimal:
    text = values.get(column, "")
    if not text:
        if default is None:
            raise ValueError(f"{values['id']}: {column} is required")
        return default
    return to_decimal(text, what=column)
