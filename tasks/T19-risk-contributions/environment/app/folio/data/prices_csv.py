"""Daily closing prices: one row per date, one column per instrument id.

    date,ADZM,BXBK,...
    2026-06-01,212.40,18.05,...

An empty cell means there was no price that day (a market holiday, a
suspension, or a fund that only prices weekly or monthly). Lookups return the
latest price on or before the date asked for, together with that price's own
date, so callers can decide whether it is too old to use.
"""

from __future__ import annotations

import bisect
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from folio.data.business_days import is_business_day, parse_date
from folio.domain.money import to_decimal
from folio.errors import DataError, MissingPriceError


@dataclass(frozen=True)
class PricePoint:
    day: date
    price: Decimal


class PriceHistory:
    """Price series per instrument, each sorted by date."""

    def __init__(self, series: dict[str, list[PricePoint]]):
        self._days: dict[str, list[date]] = {}
        self._prices: dict[str, list[Decimal]] = {}
        for instrument_id in sorted(series):
            points = sorted(series[instrument_id], key=lambda point: point.day)
            if not points:
                continue
            for earlier, later in zip(points, points[1:]):
                if earlier.day == later.day:
                    raise ValueError(f"two prices for {instrument_id} on {later.day}")
            self._days[instrument_id] = [point.day for point in points]
            self._prices[instrument_id] = [point.price for point in points]

    def instruments(self) -> list[str]:
        """Ids with at least one price, sorted."""
        return list(self._days)

    def __contains__(self, instrument_id: object) -> bool:
        return instrument_id in self._days

    def dates(self) -> list[date]:
        """Every date on which at least one instrument has a price, sorted."""
        return sorted({day for days in self._days.values() for day in days})

    def first_date(self) -> date | None:
        return min((days[0] for days in self._days.values()), default=None)

    def last_date(self) -> date | None:
        return max((days[-1] for days in self._days.values()), default=None)

    def first_price_date(self, instrument_id: str) -> date:
        days = self._days.get(instrument_id)
        if not days:
            raise MissingPriceError(f"no prices at all for {instrument_id}")
        return days[0]

    def latest(self, instrument_id: str, on: date) -> PricePoint:
        """The last price on or before ``on``."""
        days = self._days.get(instrument_id)
        if not days:
            raise MissingPriceError(f"no prices at all for {instrument_id}")
        index = bisect.bisect_right(days, on) - 1
        if index < 0:
            raise MissingPriceError(f"no price for {instrument_id} on or before {on} (its first price is {days[0]})")
        return PricePoint(days[index], self._prices[instrument_id][index])

    def history(self, instrument_id: str, start: date, end: date) -> list[PricePoint]:
        """Prices with start <= day <= end, oldest first (only days that have a price)."""
        days = self._days.get(instrument_id, [])
        low = bisect.bisect_left(days, start)
        high = bisect.bisect_right(days, end)
        prices = self._prices.get(instrument_id, [])
        return [PricePoint(days[i], prices[i]) for i in range(low, high)]

    def jumps(self, threshold: Decimal) -> list[tuple[str, date, Decimal]]:
        """Moves from one price to the next larger than ``threshold`` either way.

        Returns (instrument id, day of the later price, move) in id then date
        order; a move is a fraction, so -0.5 means the price halved.
        """
        found = []
        for instrument_id, prices in self._prices.items():
            days = self._days[instrument_id]
            for index in range(1, len(prices)):
                move = prices[index] / prices[index - 1] - 1
                if abs(move) > threshold:
                    found.append((instrument_id, days[index], move))
        return found


def load_prices(path) -> PriceHistory:
    """Read prices.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return parse_prices(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"price file not found: {path}") from None


def parse_prices(lines: Iterable[str], source: str = "<prices>") -> PriceHistory:
    """Parse CSV ``lines``; dates must be business days in increasing order, prices positive."""
    reader = csv.reader(lines)
    header = next(reader, None)
    if not header:
        raise DataError("file is empty", source=source)
    header = [cell.strip() for cell in header]
    if header[0].lower() != "date":
        raise DataError(f"the first column must be 'date', not {header[0]!r}", source=source, line=1)
    ids = header[1:]
    if not ids:
        raise DataError("no instrument columns", source=source, line=1)
    seen: set[str] = set()
    for instrument_id in ids:
        if not instrument_id:
            raise DataError("blank instrument column name", source=source, line=1)
        if instrument_id in seen:
            raise DataError(f"instrument {instrument_id} has two columns", source=source, line=1)
        seen.add(instrument_id)

    series: dict[str, list[PricePoint]] = {instrument_id: [] for instrument_id in ids}
    previous: date | None = None
    for row in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if len(row) > len(header):
            raise DataError(f"{len(row)} cells but the header has {len(header)} columns", source=source, line=line)
        try:
            day = parse_date(row[0])
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        if not is_business_day(day):
            raise DataError(f"{day} is a {day.strftime('%A')}; prices are for business days only",
                            source=source, line=line)
        if previous is not None and day <= previous:
            raise DataError(f"dates must increase: {day} comes after {previous}", source=source, line=line)
        previous = day
        for instrument_id, cell in zip(ids, row[1:]):
            if not cell.strip():
                continue
            try:
                price = to_decimal(cell, what=f"price of {instrument_id}")
            except ValueError as exc:
                raise DataError(str(exc), source=source, line=line) from None
            if price <= 0:
                raise DataError(f"price of {instrument_id} must be positive, got {cell.strip()}",
                                source=source, line=line)
            series[instrument_id].append(PricePoint(day, price))
    return PriceHistory(series)
