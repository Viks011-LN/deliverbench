"""Read benchmark.csv: the index constituents and their weights.

    id,weight,name,kind,sector,country,currency
    ADZM,0.0310,,,,,
    ORVL,0.0300,Orvelle Networks Inc,equity,Technology,US,USD

Required columns: id, weight. Weights are fractions of the index (0.031 is
3.1%) and must add up to 1 within WEIGHT_TOLERANCE; inside the tolerance they
are scaled to add up to exactly 1, so that active weights add up to zero.
Index providers round their published weights, which is why there is a
tolerance at all.

The optional columns (name, kind, sector, country, currency) describe
constituents that instruments.csv does not know, so they can still be grouped
by sector or currency. For ids that instruments.csv does know they are not
needed; instruments.csv stays the reference (see active.describe()).

Blank lines and rows whose id starts with '#' are skipped, columns folio does
not know are ignored, and errors name the file and line, as in instruments.csv.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from folio.domain.instruments import KINDS
from folio.domain.money import check_currency, to_decimal
from folio.errors import DataError

REQUIRED_COLUMNS = ("id", "weight")
LISTING_COLUMNS = ("name", "kind", "sector", "country", "currency")
WEIGHT_TOLERANCE = Decimal("0.001")


@dataclass(frozen=True)
class Listing:
    """What benchmark.csv says about a constituent; blank where the file says nothing.

    Shaped like an Instrument where the exposure dimensions look (id, name,
    kind, sector, country, currency, issuer_key), so a constituent that
    instruments.csv does not know can be grouped the same way.
    """

    id: str
    name: str = ""
    kind: str = ""
    sector: str = ""
    country: str = ""
    currency: str = ""

    @property
    def issuer_key(self) -> str:
        return self.id


@dataclass(frozen=True)
class Constituent:
    """One row of benchmark.csv."""

    listing: Listing
    weight: Decimal  # fraction of the index, after scaling to a total of 1
    line: int        # line in the file, for messages about this row

    @property
    def id(self) -> str:
        return self.listing.id


@dataclass(frozen=True)
class IndexWeights:
    """The constituents of the index, in id order."""

    source: str
    constituents: tuple[Constituent, ...]

    def __len__(self) -> int:
        return len(self.constituents)

    def weight(self, instrument_id: str) -> Decimal:
        """The index weight of ``instrument_id``; zero if it is not a constituent."""
        return next((item.weight for item in self.constituents if item.id == instrument_id), Decimal(0))


def load_weights(path) -> IndexWeights:
    """Read benchmark.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return parse_weights(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"benchmark weights file not found: {path} (use --benchmark)") from None


def parse_weights(lines: Iterable[str], source: str = "<benchmark>") -> IndexWeights:
    """Parse CSV ``lines``; ``source`` is the name used in error messages."""
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        raise DataError("file is empty", source=source)
    header = [name.strip().lower() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise DataError(f"missing column(s): {', '.join(missing)}", source=source, line=1)
    reader.fieldnames = header

    rows: dict[str, tuple[Listing, Decimal, int]] = {}
    for row in reader:
        line = reader.line_num
        if any(cell.strip() for cell in row.get(None) or ()):
            raise DataError(f"row has more cells than the header has columns ({len(header)})",
                            source=source, line=line)
        values = {key: (value or "").strip() for key, value in row.items() if key is not None}
        if not any(values.values()) or values["id"].startswith("#"):
            continue
        try:
            listing, weight = _build(values)
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if listing.id in rows:
            raise DataError(f"{listing.id} is listed twice (first on line {rows[listing.id][2]})",
                            source=source, line=line)
        rows[listing.id] = (listing, weight, line)

    if not rows:
        raise DataError("no constituents in file", source=source)
    total = sum((weight for _, weight, _ in rows.values()), Decimal(0))
    if abs(total - 1) > WEIGHT_TOLERANCE:
        hint = " (they look like percentages; give 0.025 for 2.5%)" if abs(total - 100) <= 100 * WEIGHT_TOLERANCE else ""
        raise DataError(f"weights add up to {total}, not 1 (tolerance {WEIGHT_TOLERANCE}){hint}", source=source)
    constituents = tuple(
        Constituent(listing, weight / total, line)
        for listing, weight, line in (rows[key] for key in sorted(rows))
    )
    return IndexWeights(source, constituents)


def _build(values: dict[str, str]) -> tuple[Listing, Decimal]:
    instrument_id = values["id"]
    if not instrument_id or " " in instrument_id:
        raise ValueError(f"invalid instrument id {instrument_id!r}: it must be non-empty and contain no spaces")
    if not values["weight"]:
        raise ValueError(f"{instrument_id}: weight is empty")
    weight = to_decimal(values["weight"], what=f"weight of {instrument_id}")
    if weight <= 0:
        raise ValueError(f"weight of {instrument_id} must be above 0, got {values['weight']}")

    fields = {column: values.get(column, "") for column in LISTING_COLUMNS}
    fields["kind"] = fields["kind"].lower()
    if fields["kind"] and fields["kind"] not in KINDS:
        raise ValueError(f"{instrument_id}: unknown kind {fields['kind']!r}; expected one of: {', '.join(KINDS)}")
    if fields["currency"]:
        try:
            fields["currency"] = check_currency(fields["currency"].upper())
        except ValueError as exc:
            raise ValueError(f"{instrument_id}: {exc}") from None
    return Listing(instrument_id, **fields), weight
