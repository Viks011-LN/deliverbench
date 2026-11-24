"""FX fixings: one row per date, one column per currency pair.

    date,EURUSD,GBPUSD,USDJPY
    2026-06-01,1.0842,1.2716,155.32

Column XXXYYY is the price of one XXX in YYY (market convention), so EURUSD
at 1.0842 means 1 EUR = 1.0842 USD. A cross that is not in the file goes
through the pivot currency: GBPEUR = GBPUSD / EURUSD when the pivot is USD.

A fixing older than ``max_age_days`` calendar days is refused rather than
used, unlike prices: a stale rate moves every line in that currency at once.
"""

from __future__ import annotations

import bisect
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from folio.data.business_days import parse_date
from folio.domain.money import Money, check_currency, to_decimal
from folio.errors import DataError, MissingPriceError

Pair = tuple[str, str]


def split_pair(text: str) -> Pair:
    """``"EURUSD"`` -> ``("EUR", "USD")``."""
    text = text.strip().upper().replace("/", "")
    if len(text) != 6:
        raise ValueError(f"currency pair {text!r} should be six letters such as EURUSD")
    base, quote = check_currency(text[:3]), check_currency(text[3:])
    if base == quote:
        raise ValueError(f"currency pair {text} has the same currency twice")
    return base, quote


class FxRates:
    """Fixings per currency pair, with lookups that invert and cross through a pivot.

    ``max_age_days`` (None = no limit) is fx.max_rate_age_days; see _fixing().
    """

    def __init__(self, fixings: dict[Pair, list[tuple[date, Decimal]]], *, pivot: str = "USD",
                 max_age_days: int | None = None):
        self.pivot = check_currency(pivot)
        self.max_age_days = max_age_days
        self._days: dict[Pair, list[date]] = {}
        self._rates: dict[Pair, list[Decimal]] = {}
        for pair in sorted(fixings):
            points = sorted(fixings[pair])
            if points:
                self._days[pair] = [day for day, _ in points]
                self._rates[pair] = [rate for _, rate in points]

    def currencies(self) -> list[str]:
        found = {self.pivot}
        for base, quote in self._days:
            found.update((base, quote))
        return sorted(found)

    def rate(self, base: str, quote: str, on: date) -> Decimal:
        """How many ``quote`` one unit of ``base`` buys on ``on``."""
        if base == quote:
            return Decimal(1)
        direct = self._direct(base, quote, on)
        if direct is not None:
            return direct
        if self.pivot in (base, quote):
            raise MissingPriceError(f"no FX rate for {base}{quote} and none for {quote}{base}")
        first = self._direct(base, self.pivot, on)
        second = self._direct(self.pivot, quote, on)
        if first is None or second is None:
            missing = f"{base}{self.pivot}" if first is None else f"{self.pivot}{quote}"
            raise MissingPriceError(f"no FX rate for {base}{quote}: cannot cross through {self.pivot} "
                                    f"without {missing} (or its inverse)")
        return first * second

    def convert(self, amount: Money, currency: str, on: date) -> Money:
        """``amount`` in ``currency`` at the rate for ``on``."""
        return Money(amount.amount * self.rate(amount.currency, currency, on), currency)

    def _direct(self, base: str, quote: str, on: date) -> Decimal | None:
        if (base, quote) in self._days:
            return self._fixing((base, quote), on)
        if (quote, base) in self._days:
            return Decimal(1) / self._fixing((quote, base), on)
        return None

    def _fixing(self, pair: Pair, on: date) -> Decimal:
        days = self._days[pair]
        index = bisect.bisect_right(days, on) - 1
        name = "".join(pair)
        if index < 0:
            raise MissingPriceError(f"no {name} fixing on or before {on} (the first is {days[0]})")
        # TODO: count business days, as prices do; calendar days make a Friday
        # fixing look three days old on Monday, so the limit has to be loose.
        age = (on - days[index]).days
        if self.max_age_days is not None and age > self.max_age_days:
            raise MissingPriceError(f"latest {name} fixing before {on} is from {days[index]}, {age} days old; "
                                    f"fx.max_rate_age_days is {self.max_age_days}")
        return self._rates[pair][index]


def load_fx(path, *, pivot: str = "USD", max_age_days: int | None = None) -> FxRates:
    """Read fx.csv at ``path``; ``pivot`` and ``max_age_days`` come from the [fx] settings."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return parse_fx(handle, source=path.name, pivot=pivot, max_age_days=max_age_days)
    except FileNotFoundError:
        raise DataError(f"FX file not found: {path}") from None


def parse_fx(lines: Iterable[str], source: str = "<fx>", *, pivot: str = "USD",
             max_age_days: int | None = None) -> FxRates:
    reader = csv.reader(lines)
    header = [cell.strip() for cell in next(reader, [])]
    if not header or header[0].lower() != "date":
        raise DataError("the first column must be 'date'", source=source, line=1)
    pairs: list[Pair] = []
    for cell in header[1:]:
        try:
            pair = split_pair(cell)
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=1) from None
        if pair in pairs or pair[::-1] in pairs:
            raise DataError(f"pair {cell} appears twice (directly or inverted)", source=source, line=1)
        pairs.append(pair)

    fixings: dict[Pair, list[tuple[date, Decimal]]] = {pair: [] for pair in pairs}
    previous = None
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        line = reader.line_num
        try:
            day = parse_date(row[0])
            if previous is not None and day <= previous:
                raise ValueError(f"dates must increase: {day} comes after {previous}")
            previous = day
            for pair, cell in zip(pairs, row[1:]):
                if cell.strip():
                    rate = to_decimal(cell, what=f"{''.join(pair)} rate")
                    if rate <= 0:
                        raise ValueError(f"{''.join(pair)} rate must be positive, got {cell.strip()}")
                    fixings[pair].append((day, rate))
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
    return FxRates(fixings, pivot=pivot, max_age_days=max_age_days)
