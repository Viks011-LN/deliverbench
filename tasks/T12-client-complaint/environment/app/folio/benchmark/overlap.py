"""Active share and the largest bets against the index.

Active share is half the sum of the absolute active weights,

    active_share = sum(|book weight - index weight|) / 2

over every instrument held or listed and every cash balance. Both sides add up
to 1, so it runs from 0 (the book is the index) to 1 (nothing in common), and
1 - active_share is the weight the two have in common: the sum, holding by
holding, of the smaller of the two weights.

Cash counts as a holding the index does not have. Leaving it out would make a
book that is the index plus a tenth in cash look perfectly passive.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from folio.benchmark.active import ActiveLine, Comparison


@dataclass(frozen=True)
class Overlap:
    """Everything ``overlap`` prints."""

    active_share: Decimal
    in_common: Decimal                    # sum of min(book, index) weights
    held: int                             # instruments the book holds
    listed: int                           # index constituents
    common: int                           # instruments in both
    overweights: tuple[ActiveLine, ...]   # largest first
    underweights: tuple[ActiveLine, ...]  # most underweight first


def active_share(lines: Iterable[ActiveLine]) -> Decimal:
    return sum((abs(line.active) for line in lines), Decimal(0)) / 2


def overlap(comparison: Comparison, top: int = 5) -> Overlap:
    """Active share of ``comparison`` and its ``top`` largest over- and underweights.

    The lists hold instruments only; cash shows up in active share and in the
    ``active`` command. Ties go to the lower id.
    """
    if top < 1:
        raise ValueError(f"top must be 1 or more, got {top}")
    lines = comparison.lines
    over = sorted((line for line in lines if line.active > 0), key=lambda line: (-line.active, line.id))
    under = sorted((line for line in lines if line.active < 0), key=lambda line: (line.active, line.id))
    return Overlap(
        active_share=active_share(comparison.every_line),
        in_common=sum((min(line.book, line.index) for line in comparison.every_line), Decimal(0)),
        held=sum(1 for line in lines if line.held),
        listed=sum(1 for line in lines if line.listed),
        common=sum(1 for line in lines if line.held and line.listed),
        overweights=tuple(over[:top]),
        underweights=tuple(under[:top]),
    )
