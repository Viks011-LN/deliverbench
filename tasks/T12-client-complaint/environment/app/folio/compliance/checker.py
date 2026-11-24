"""Run the mandate's guidelines against a valuation and work out the headroom on each.

The check is all-or-nothing per run: every guideline in force is measured on
the same valuation, and the result keeps both the violations, for the exit
status and the VIOLATION lines, and the tightest reading of every guideline,
for ``check --explain``. The tightest reading is the one with the least
headroom, which for a guideline in violation is its worst violation.

Headroom on a share is also given in the base currency, as headroom x NAV:
that is how much can be bought (or, for a minimum, sold) for cash before the
guideline is violated, since a trade for cash leaves NAV where it was. For a
violation it is the amount to sell, or to buy, to come back inside.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from folio.calc.valuation import Valuation
from folio.compliance.guideline import MAX_COUNT, Guideline, Reading
from folio.domain.money import Money


@dataclass(frozen=True)
class Headroom:
    """How close one guideline is to its limit: its tightest reading, if it measured anything."""

    guideline: str
    kind: str
    limit: Decimal
    tightest: Reading | None
    amount: Money | None = None  # headroom in the base currency; None for counts and when nothing was read
    remark: str = ""             # said instead of figures when there was nothing to measure


@dataclass(frozen=True)
class ComplianceResult:
    """What run_guidelines() found; ``ok`` is True when no guideline is violated."""

    violations: tuple[Reading, ...]  # in guideline order, then each guideline's own order
    checked: tuple[str, ...]         # keys of the guidelines that ran
    headroom: tuple[Headroom, ...]   # one per guideline that ran, same order
    nav: Money                       # of the valuation checked

    @property
    def ok(self) -> bool:
        return not self.violations

    def violated(self) -> tuple[str, ...]:
        """Keys of the guidelines with at least one violation, in guideline order."""
        return tuple(key for key in self.checked if any(reading.guideline == key for reading in self.violations))


def tightest(readings: Iterable[Reading]) -> Reading | None:
    """The reading with the least headroom; ties go to the first subject in name order."""
    return min(readings, key=lambda reading: (reading.headroom, reading.subject), default=None)


def headroom_of(guideline: Guideline, readings: list[Reading], nav: Money) -> Headroom:
    """The Headroom entry for one guideline's readings on a book worth ``nav``."""
    closest = tightest(readings)
    if closest is None:
        return Headroom(guideline.key, guideline.kind, guideline.limit, None, remark=guideline.nothing_to_measure)
    amount = None if guideline.kind == MAX_COUNT else nav * closest.headroom
    return Headroom(guideline.key, guideline.kind, guideline.limit, closest, amount)


def run_guidelines(valuation: Valuation, guidelines: Iterable[Guideline]) -> ComplianceResult:
    """Measure every guideline once; violations keep the guideline order."""
    violations: list[Reading] = []
    checked: list[str] = []
    headroom: list[Headroom] = []
    for guideline in guidelines:
        readings = guideline.measure(valuation)
        violations.extend(reading for reading in readings if reading.is_violation)
        checked.append(guideline.key)
        headroom.append(headroom_of(guideline, readings, valuation.nav))
    return ComplianceResult(tuple(violations), tuple(checked), tuple(headroom), valuation.nav)
