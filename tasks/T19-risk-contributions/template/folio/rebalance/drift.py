"""Drift: how far each target's current weight is from its model weight.

A target's current weight is the sum of the weights of the holdings it
covers: one instrument for an instrument target, every holding in the sector
for a sector target, all cash balances for the cash target. Drift is current
minus model, so a positive drift is overweight. A target is outside its band
when the drift, either way, is strictly larger than the band; a drift that
sits exactly on the edge of the band does not trade.

measure_drift() takes (instrument, weight) pairs rather than a Valuation, so
the same code measures the book before a proposal and after it. Every
holding must be covered by a target: one that no target mentions would be
left to chance by the proposal, so it is an error that names the holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from folio.calc.valuation import Valuation
from folio.domain.instruments import Instrument
from folio.errors import DataError
from folio.rebalance.targets import Target, TargetSet

Holding = tuple[Instrument, Decimal]  # an instrument and its weight in NAV


@dataclass(frozen=True)
class Drift:
    """One target against the book: its current weight and the holdings that make it up."""

    target: Target
    current: Decimal             # fraction of NAV
    members: tuple[str, ...]     # ids of the holdings it covers, in id order; () for cash

    @property
    def drift(self) -> Decimal:
        return self.current - self.target.weight

    @property
    def outside(self) -> bool:
        return abs(self.drift) > self.target.band


def holdings_of(valuation: Valuation) -> list[Holding]:
    """Each open position of ``valuation`` with its weight, in instrument id order."""
    return [(line.instrument, line.weight) for line in valuation.positions]


def cash_weight_of(valuation: Valuation) -> Decimal:
    return valuation.cash_total.amount / valuation.nav.amount


def measure_drift(targets: TargetSet, holdings: Iterable[Holding], cash_weight: Decimal) -> tuple[Drift, ...]:
    """Every target in ``targets`` against ``holdings``, ordered by order_by_drift().

    Raises DataError, naming the targets file, when a holding has no target.
    """
    weights: dict[tuple[str, str], list[Holding]] = {(target.scope, target.key): [] for target in targets}
    uncovered = []
    for instrument, weight in sorted(holdings, key=lambda holding: holding[0].id):
        target = targets.for_instrument(instrument)
        if target is None:
            uncovered.append(f"{instrument.id} ({instrument.sector})")
            continue
        weights[(target.scope, target.key)].append((instrument, weight))
    if uncovered:
        raise DataError(f"held but covered by no target: {', '.join(uncovered)}; give each one, or its sector, "
                        f"a target (a weight of 0 sells it)", source=targets.source)

    drifts = []
    for target in targets:
        if target.is_cash:
            drifts.append(Drift(target, cash_weight, ()))
            continue
        covered = weights[(target.scope, target.key)]
        drifts.append(Drift(target, sum((weight for _, weight in covered), Decimal(0)),
                            tuple(instrument.id for instrument, _ in covered)))
    return order_by_drift(drifts)


def order_by_drift(drifts: Iterable[Drift]) -> tuple[Drift, ...]:
    """Largest drift either way first, ties by label; the cash target always last."""
    return tuple(sorted(drifts, key=lambda drift: (drift.target.is_cash, -abs(drift.drift), drift.target.label)))


def outside_band(drifts: Iterable[Drift]) -> list[Drift]:
    """The drifts whose target is outside its band, in the order given."""
    return [drift for drift in drifts if drift.outside]
