"""Read restricted.csv: the instruments and issuers the client does not allow the portfolio to hold.

    instrument,issuer,reason,from,until
    TNSL,,Thermal coal mining over 10% of revenue,2026-10-01,
    ,MXTB,Trustee review of lending practices,2026-06-15,2026-07-31

Each row names either one instrument, by its id in instruments.csv, or an
issuer as Instrument.issuer_key gives it, never both. An issuer row covers
everything that issuer has issued: ``MXTB`` above catches Maxtead Bank's
shares and its bond. A restriction is in force from ``from`` to ``until``,
both days included; a blank ``until`` means until further notice.

Rows for names the portfolio has never held are normal, since the client's
list is wider than the book, so ids and issuers are not checked against
instruments.csv. Everything else is: unknown columns, a row naming both or
neither, a missing reason, an ``until`` before its ``from`` and the same name
listed twice from the same day are errors naming the file and line. Blank
lines and rows whose first cell starts with '#' are skipped.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from folio.data.business_days import parse_date
from folio.domain.instruments import Instrument
from folio.errors import DataError

REQUIRED_COLUMNS = ("instrument", "issuer", "reason", "from")
COLUMNS = REQUIRED_COLUMNS + ("until",)


@dataclass(frozen=True)
class Restriction:
    """One row of the restricted list."""

    instrument: str     # an instrument id, or "" when the row names an issuer
    issuer: str         # an issuer key, or "" when the row names an instrument
    reason: str
    start: date         # the ``from`` column
    end: date | None    # the ``until`` column, last day included; None = no end
    line: int = 0       # where it is in the file, for messages

    def __post_init__(self) -> None:
        if bool(self.instrument) == bool(self.issuer):
            raise ValueError("a restriction names an instrument or an issuer, not both and not neither")
        if not self.reason.strip():
            raise ValueError(f"{self.target}: reason is empty")
        if self.end is not None and self.end < self.start:
            raise ValueError(f"{self.target}: until {self.end} is before from {self.start}")

    @property
    def target(self) -> str:
        return self.instrument or self.issuer

    @property
    def by_issuer(self) -> bool:
        return bool(self.issuer)

    def describe(self) -> str:
        """``TNSL`` for an instrument row, ``issuer MXTB`` for an issuer row."""
        return f"issuer {self.issuer}" if self.by_issuer else self.instrument

    def in_force(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day <= self.end)

    def covers(self, instrument: Instrument) -> bool:
        if self.by_issuer:
            return instrument.issuer_key == self.issuer
        return instrument.id == self.instrument


@dataclass(frozen=True)
class RestrictedList:
    """Every row of restricted.csv, in file order."""

    entries: tuple[Restriction, ...]
    source: str = "<restricted>"

    def __len__(self) -> int:
        return len(self.entries)

    def in_force(self, day: date) -> list[Restriction]:
        return [entry for entry in self.entries if entry.in_force(day)]

    def lifted(self, day: date) -> list[Restriction]:
        """Entries whose ``until`` has passed by ``day``."""
        return [entry for entry in self.entries if entry.end is not None and entry.end < day]

    def not_yet(self, day: date) -> list[Restriction]:
        """Entries that start after ``day``."""
        return [entry for entry in self.entries if entry.start > day]

    def restriction_for(self, instrument: Instrument, day: date) -> Restriction | None:
        """The restriction on ``instrument`` in force on ``day``, the longest-standing if several are."""
        found = [entry for entry in self.in_force(day) if entry.covers(instrument)]
        return min(found, key=lambda entry: (entry.start, entry.line), default=None)

    def next_restriction(self, instrument: Instrument, day: date) -> Restriction | None:
        """The first restriction on ``instrument`` that starts after ``day``."""
        found = [entry for entry in self.not_yet(day) if entry.covers(instrument)]
        return min(found, key=lambda entry: (entry.start, entry.line), default=None)


def load_restricted(path) -> RestrictedList:
    """Read restricted.csv at ``path``. Raises DataError naming the file and line."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:  # utf-8-sig: Excel adds a BOM
            return parse_restricted(handle, source=path.name)
    except FileNotFoundError:
        raise DataError(f"restricted list not found: {path}") from None


def parse_restricted(lines: Iterable[str], source: str = "<restricted>") -> RestrictedList:
    """Parse CSV ``lines``; ``source`` is the name used in error messages."""
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        raise DataError("file is empty", source=source)
    header = [name.strip().lower() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise DataError(f"missing column(s): {', '.join(missing)}", source=source, line=1)
    unknown = [column for column in header if column and column not in COLUMNS]
    if unknown:
        raise DataError(f"unknown column {unknown[0]!r}; expected {', '.join(COLUMNS)}", source=source, line=1)
    reader.fieldnames = header

    entries: list[Restriction] = []
    first_seen: dict[tuple[str, str, date], int] = {}
    for row in reader:
        line = reader.line_num
        values = {key: (value or "").strip() for key, value in row.items() if key}
        first = next(iter(values.values()), "")
        extra = [cell for cell in row.get(None) or () if cell.strip()]
        if first.startswith("#") or not (any(values.values()) or extra):
            continue
        if extra:
            raise DataError(f"row has more cells than the header has columns ({len(header)})",
                            source=source, line=line)
        try:
            entry = _build(values, line)
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=line) from None
        seen = (entry.instrument, entry.issuer, entry.start)
        if seen in first_seen:
            raise DataError(f"{entry.describe()} is already listed from {entry.start} (line {first_seen[seen]})",
                            source=source, line=line)
        first_seen[seen] = line
        entries.append(entry)
    return RestrictedList(tuple(entries), source)


def _build(values: dict[str, str], line: int) -> Restriction:
    instrument, issuer = values["instrument"], values["issuer"]
    if instrument and issuer:
        raise ValueError(f"give an instrument or an issuer, not both ({instrument}, {issuer})")
    if not instrument and not issuer:
        raise ValueError("no instrument or issuer")
    if " " in instrument:
        raise ValueError(f"instrument id {instrument!r} contains a space")
    if not values["from"]:
        raise ValueError(f"{instrument or issuer}: from is required")
    start = parse_date(values["from"], what="from")
    until = values.get("until", "")
    end = parse_date(until, what="until") if until else None
    return Restriction(instrument, issuer, values["reason"], start, end, line)
