"""Read targets.csv: the model weights the book is brought back to.

    scope,key,weight,band
    sector,Technology,0.15,0.010
    instrument,GEIF,0.05,0.005
    cash,,0.04,0.010

Each row is one target. ``scope`` says what it covers: one instrument (by
id), every holding in one sector, or the cash balances. ``weight`` and
``band`` are fractions of NAV; a target is outside its band when its current
weight is further than ``band`` from ``weight``, either way.

The rows must describe one consistent model, so the reader refuses:

* weights that, cash target included, do not add up to 1;
* an instrument or a sector that instruments.csv does not know;
* an instrument with a target of its own in a sector that also has one,
  because the two would pull the same holding towards different weights;
* a second target for the same thing, and a file without a cash target.

Blank lines and lines starting with '#' are skipped, so the file can say
where the weights came from. Columns other than the four above are ignored.
Errors name the file and line.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator

from folio.domain.instruments import Instrument, Universe
from folio.domain.money import to_decimal
from folio.errors import DataError

COLUMNS = ("scope", "key", "weight", "band")
INSTRUMENT, SECTOR, CASH = "instrument", "sector", "cash"
SCOPES = (INSTRUMENT, SECTOR, CASH)

# Weights are typed by hand; allow for a third written as 0.333333.
SUM_TOLERANCE = Decimal("0.000001")


@dataclass(frozen=True)
class Target:
    """One model weight and its tolerance band, both fractions of NAV."""

    scope: str               # one of SCOPES
    key: str                 # instrument id or sector name; empty for cash
    weight: Decimal
    band: Decimal
    line: int | None = None  # line in the targets file, for messages

    @property
    def is_cash(self) -> bool:
        return self.scope == CASH

    @property
    def label(self) -> str:
        return "Cash" if self.is_cash else self.key

    def describe(self) -> str:
        """``sector Technology``, ``instrument GEIF`` or ``cash``, for messages."""
        return CASH if self.is_cash else f"{self.scope} {self.key}"


@dataclass(frozen=True)
class TargetSet:
    """Every target read from one file, in file order."""

    source: str  # file name, for messages about the targets
    targets: tuple[Target, ...]

    def __iter__(self) -> Iterator[Target]:
        return iter(self.targets)

    def __len__(self) -> int:
        return len(self.targets)

    @property
    def cash(self) -> Target:
        return next(target for target in self.targets if target.is_cash)

    def for_instrument(self, instrument: Instrument) -> Target | None:
        """The target covering ``instrument``: its own if it has one, else its sector's."""
        by_sector = None
        for target in self.targets:
            if target.scope == INSTRUMENT and target.key == instrument.id:
                return target
            if target.scope == SECTOR and target.key == instrument.sector:
                by_sector = target
        return by_sector


def load_targets(path, universe: Universe) -> TargetSet:
    """Read targets.csv at ``path``, checking it against ``universe``."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")  # utf-8-sig: Excel adds a BOM
    except FileNotFoundError:
        raise DataError(f"targets file not found: {path} (use --targets)") from None
    return parse_targets(text.splitlines(), universe, source=path.name)


def parse_targets(lines: Iterable[str], universe: Universe, source: str = "<targets>") -> TargetSet:
    """Parse CSV ``lines``; ``source`` is the name used in error messages."""
    header: list[str] | None = None
    targets: list[Target] = []
    first_seen: dict[tuple[str, str], int] = {}
    for number, text in enumerate(lines, start=1):
        if not text.strip() or text.lstrip().startswith("#"):
            continue
        cells = [cell.strip() for cell in next(csv.reader([text]))]
        if header is None:
            header = [cell.lower() for cell in cells]
            missing = [column for column in COLUMNS if column not in header]
            if missing:
                raise DataError(f"missing column(s): {', '.join(missing)}", source=source, line=number)
            continue
        if any(cells[len(header):]):
            raise DataError(f"row has more cells than the header has columns ({len(header)})",
                            source=source, line=number)
        values = dict(zip(header, cells + [""] * (len(header) - len(cells))))
        try:
            target = _build(values, universe, number)
        except ValueError as exc:
            raise DataError(str(exc), source=source, line=number) from None
        identity = (target.scope, target.key)
        if identity in first_seen:
            raise DataError(f"second target for {target.describe()} (the first is on line {first_seen[identity]})",
                            source=source, line=number)
        first_seen[identity] = number
        targets.append(target)

    if header is None:
        raise DataError("file is empty", source=source)
    if not targets:
        raise DataError("no targets in file", source=source)
    if (CASH, "") not in first_seen:
        raise DataError("no cash target; add a row such as 'cash,,0.02,0.01' (a weight of 0 is fine)",
                        source=source)
    _check_overlaps(targets, universe, source)
    _check_total(targets, source)
    return TargetSet(source, tuple(targets))


def _build(values: dict[str, str], universe: Universe, line: int) -> Target:
    scope, key = values["scope"].lower(), values["key"]
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {values['scope']!r}; expected one of: {', '.join(SCOPES)}")
    if scope == CASH and key:
        raise ValueError(f"the cash target takes no key, got {key!r}")
    if scope != CASH and not key:
        raise ValueError(f"a {scope} target needs a key")
    if scope == INSTRUMENT and key not in universe:
        raise ValueError(f"unknown instrument {key!r}: it is not in instruments.csv")
    if scope == SECTOR and key not in universe.sectors():
        raise ValueError(f"unknown sector {key!r}; instruments.csv has {', '.join(universe.sectors())}")
    return Target(scope, key, _fraction(values["weight"], "weight"), _fraction(values["band"], "band"), line)


def _fraction(text: str, what: str) -> Decimal:
    if not text:
        raise ValueError(f"{what} is required")
    value = to_decimal(text, what=what)
    if not Decimal(0) <= value <= Decimal(1):
        raise ValueError(f"{what} {text} must be a fraction of NAV between 0 and 1, such as 0.05")
    return value


def _check_overlaps(targets: list[Target], universe: Universe, source: str) -> None:
    sectors = {target.key: target for target in targets if target.scope == SECTOR}
    for target in targets:
        if target.scope != INSTRUMENT:
            continue
        sector = universe[target.key].sector
        if sector in sectors:
            raise DataError(f"instrument {target.key} is in sector {sector}, which has its own target on line "
                            f"{sectors[sector].line}; give the instrument or the sector a target, not both",
                            source=source, line=target.line)


def _check_total(targets: list[Target], source: str) -> None:
    total = sum((target.weight for target in targets), Decimal(0))
    if abs(total - 1) > SUM_TOLERANCE:
        raise DataError(f"weights add up to {total}, not 1 (the cash target counts too)", source=source)
