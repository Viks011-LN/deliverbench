"""Restricted holdings: positions in names the client's restricted list rules out.

The list itself is read by restricted_list.py. This module matches it against
a valuation, for two users: the ``restricted_holdings`` guideline, which
makes every match a violation, and the ``restricted`` command, which also
shows the holdings an upcoming entry will catch, so that the desk can sell
before the restriction starts rather than after.

A holding is matched on the valuation date only. Something bought and sold
while it was restricted leaves no trace here; that is a question for the
trade log, not for a check of the book as it stands.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from folio.calc.valuation import PositionValue, Valuation
from folio.compliance.guideline import NONE_HELD, Guideline
from folio.compliance.restricted_list import RestrictedList, Restriction


@dataclass(frozen=True)
class RestrictedHolding:
    """A position and the restricted-list entry that catches it."""

    position: PositionValue
    restriction: Restriction

    def detail(self) -> str:
        """``restricted since 2026-10-01 (reason)``, naming the issuer when the entry does."""
        who = f"issuer {self.restriction.issuer} " if self.restriction.by_issuer else ""
        return f"{who}restricted since {self.restriction.start} ({self.restriction.reason})"


def _largest_first(found: list[RestrictedHolding]) -> list[RestrictedHolding]:
    return sorted(found, key=lambda holding: (-holding.position.weight, holding.position.instrument.id))


def restricted_holdings(valuation: Valuation, restricted: RestrictedList) -> list[RestrictedHolding]:
    """Positions covered by an entry in force on the valuation date, largest first, ties by id."""
    found = []
    for line in valuation.positions:
        entry = restricted.restriction_for(line.instrument, valuation.as_of)
        if entry is not None:
            found.append(RestrictedHolding(line, entry))
    return _largest_first(found)


def upcoming_restrictions(valuation: Valuation, restricted: RestrictedList) -> list[RestrictedHolding]:
    """Positions not restricted yet that an entry starting later will catch, largest first."""
    found = []
    for line in valuation.positions:
        if restricted.restriction_for(line.instrument, valuation.as_of) is not None:
            continue
        entry = restricted.next_restriction(line.instrument, valuation.as_of)
        if entry is not None:
            found.append(RestrictedHolding(line, entry))
    return _largest_first(found)


class RestrictedHoldings(Guideline):
    """Nothing on the restricted list may be held: every match is a violation, whatever its size."""

    key = "restricted_holdings"
    kind = NONE_HELD
    title = "names on restricted.csv"
    nothing_to_measure = "no restricted holdings"

    def __init__(self, restricted: RestrictedList, note: str = ""):
        super().__init__(Decimal(0), note)
        self.restricted = restricted

    @classmethod
    def from_term(cls, term, restricted=None):
        if restricted is None:
            raise ValueError(f"{cls.key} needs the restricted list")
        return cls(restricted, term.note)

    def measure(self, valuation):
        return [
            self.reading(holding.position.instrument.id, holding.position.weight, holding.detail())
            for holding in restricted_holdings(valuation, self.restricted)
        ]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self.restricted)} entries)"
