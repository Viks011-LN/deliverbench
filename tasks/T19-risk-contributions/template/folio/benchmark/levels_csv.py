"""Read benchmark_levels.csv: the index's closing level, one row per date.

    date,HGB6040
    2026-06-01,2150.00

The second column is named after the index, and the reports use that name.
Levels are in the base currency, on business days in increasing order; the
same dates as prices.csv is the normal case. A blank cell means no level that
day, and lookups then use the latest earlier level, the way price gaps are
filled for the book's own NAV series.
"""

from __future__ import annotations

import bisect
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from folio.data.business_days import is_business_day, parse_date
from folio.data.prices_csv import PricePoint
from folio.domain.money import to_decimal
from folio.errors import DataError, MissingPriceError


class IndexLevels:
    """The index's level history, sorted by date."""

    def __init__(self, code: str, points: Iterable[PricePoint]):
        ordered = sorted(points, key=lambda point: point.day)
        if not ordered:
            raise ValueError(f"no levels for {code}")
        for earlier, later in zip(ordered, ordered[1:]):
            if earlier.day == later.day:
                raise ValueError(f"two levels for {code} on {later.day}")
        self.code = code
        self._days = [point.day for point in ordered]
        self._levels = [point.price for point in ordered]

    def __len__(self) -> int:
        return len(self._days)

    def first_date(self) -> date:
        return self._days[0]

    def last_date(self) -> date:
        return self._days[-1]

    def latest(self, on: date) -> PricePoint:
        """The last level on or before ``on``."""
        index = bisect.bisect_right(self._days, on) - 1
        if index < 0:
            raise MissingPriceError(f"no level for {self.code} on or before {on} (the first is {self._days[0]})")
        return PricePoint(self._days[index], self._levels[index])

    def period_return(self, start: date, end: date) -> Decimal:
        """Index return from ``start`` to ``end``, e.g. Decimal('0.021') for +2.1%."""
        return self.latest(end).price / self.latest(start).price - 1


def load_levels(path) -> IndexLevels:
    """Read benchmark_levels.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return parse_levels(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"benchmark levels file not found: {path} (use --levels)") from None


def parse_levels(lines: Iterable[str], source: str = "<levels>") -> IndexLevels:
    """Parse CSV ``lines``: a date column, then one column of levels named after the index."""
    reader = csv.reader(lines)
    header = [cell.strip() for cell in next(reader, [])]
    if not header:
        raise DataError("file is empty", source=source)
    if header[0].lower() != "date":
        raise DataError(f"the first column must be 'date', not {header[0]!r}", source=source, line=1)
    if len(header) != 2 or not header[1]:
        raise DataError(f"expected a date column and one level column named after the index, "
                        f"found {len(header)} column(s)", source=source, line=1)
    code = header[1]

    points = []
    previous: date | None = None
    for row in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) > 2 and any(cell.strip() for cell in row[2:]):
            raise DataError(f"{len(row)} cells but the header has 2 columns", source=source, line=line)
        try:
            day = parse_date(row[0])
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if not is_business_day(day):
            raise DataError(f"{day} is a {day.strftime('%A')}; levels are for business days only",
                            source=source, line=line)
        if previous is not None and day <= previous:
            raise DataError(f"dates must increase: {day} comes after {previous}", source=source, line=line)
        previous = day
        cell = row[1].strip() if len(row) > 1 else ""
        if not cell:
            continue
        try:
            level = to_decimal(cell, what=f"level of {code}")
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if level <= 0:
            raise DataError(f"level of {code} must be positive, got {cell}", source=source, line=line)
        points.append(PricePoint(day, level))
    if not points:
        raise DataError(f"no levels for {code}", source=source)
    return IndexLevels(code, points)
