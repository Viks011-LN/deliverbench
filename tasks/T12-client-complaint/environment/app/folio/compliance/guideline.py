"""Guidelines: the base class every clause of the mandate builds on, and what it reads.

A guideline measures the valuation and returns Readings, one per subject (an
issuer, a country, the cash line...), each carrying the limit it is held to.
What "inside the limit" means depends on the guideline's kind:

* ``max_share`` and ``max_count``: the reading may not be above the limit;
* ``min_share``: the reading may not be below it;
* ``none_held``: the subject may not be held at all (the restricted list).

Equal is compliant, and the comparison uses exact values, so a holding printed
as 7.0% against a 7.0% limit is never a violation by rounding. Headroom is how
far a reading can move before it violates; negative headroom is the size of
the violation. Shares are fractions of NAV and counts are whole numbers, both
held as Decimal so that every reading compares and sorts the same way.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from folio.calc.valuation import Valuation
from folio.domain.instruments import Bond, Fund, Instrument

if TYPE_CHECKING:
    from folio.compliance.mandate import Term
    from folio.compliance.restricted_list import RestrictedList

MAX_SHARE = "max_share"
MIN_SHARE = "min_share"
MAX_COUNT = "max_count"
NONE_HELD = "none_held"
KINDS = (MAX_SHARE, MIN_SHARE, MAX_COUNT, NONE_HELD)

# Bonds in this sector are government debt. The issuer guideline leaves them
# out (sovereigns are capped by country) and govt_min_share counts only them.
GOVERNMENT_SECTOR = "Government"


def is_government_bond(instrument: Instrument) -> bool:
    return isinstance(instrument, Bond) and instrument.sector == GOVERNMENT_SECTOR


def is_fund(instrument: Instrument) -> bool:
    return isinstance(instrument, Fund)


@dataclass(frozen=True)
class Reading:
    """One measured subject of one guideline, with the limit it is held to."""

    guideline: str
    subject: str
    actual: Decimal   # fraction of NAV, or a count for max_count
    limit: Decimal    # zero for none_held
    kind: str
    detail: str = ""  # said after the figures, e.g. why a name is restricted

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"reading {self.guideline} {self.subject}: unknown kind {self.kind!r}")

    @property
    def headroom(self) -> Decimal:
        """How far ``actual`` may move before it violates; negative when it already does."""
        if self.kind == MIN_SHARE:
            return self.actual - self.limit
        return self.limit - self.actual

    @property
    def is_violation(self) -> bool:
        return self.headroom < 0


class Guideline(abc.ABC):
    """Base class: subclasses set ``key``, ``kind`` and ``title`` and implement measure()."""

    key: ClassVar[str]    # the table name in guidelines.toml, and what the output calls it
    kind: ClassVar[str]   # one of KINDS: how the mandate states the limit and how it compares
    title: ClassVar[str]  # what the guideline covers, in a few words
    nothing_to_measure: ClassVar[str] = "nothing to measure"

    def __init__(self, limit: Decimal, note: str = ""):
        if not isinstance(limit, Decimal):
            raise TypeError(f"{self.key}: limit must be a Decimal, got {limit!r}")
        self.limit = limit
        self.note = note

    @classmethod
    def from_term(cls, term: Term, restricted: RestrictedList | None = None) -> Guideline:
        """Build the guideline a mandate term describes; only the restricted list needs ``restricted``."""
        if term.value is None:
            raise ValueError(f"{cls.key}: the mandate gives no value")
        return cls(term.value, term.note)

    @abc.abstractmethod
    def measure(self, valuation: Valuation) -> list[Reading]:
        """Everything this guideline covers, in the order its violations are printed."""

    def reading(self, subject: str, actual: Decimal, detail: str = "") -> Reading:
        return Reading(self.key, subject, actual, self.limit, self.kind, detail)

    def check(self, valuation: Valuation) -> list[Reading]:
        """The readings that violate the guideline, in measure() order."""
        return [reading for reading in self.measure(valuation) if reading.is_violation]

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.key}={self.limit})"
