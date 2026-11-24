"""Revalue the book under a scenario.

Every scenario, whether its shocks come from the scenario file or from the
price history, comes down to Moves: a price change per instrument and a
change per currency. Stresser.run() turns those into a stressed value for
every position and every cash balance:

    stressed = base value x (1 + price change) x (1 + FX change)

The FX change is that of the line's own currency against the base currency,
so a position in the base currency, and base-currency cash, only move with
their price. Cash has no price; it moves with FX alone.

A bond yield shift becomes a price change through the bond's modified
duration (calc/bonds.py), a first-order estimate:

    price change = -modified duration x shift

It leaves out convexity, so it overstates the loss when yields rise and
understates the gain when they fall. For a seven-year bond the gap is about
a quarter of a percent of its price for a 100 bp shift, and four times that
for 200 bp. Funds are not bonds here: a yield shift does not move a bond
fund, so shock it by instrument if it should move.

Nothing is rounded here; the outputs round at the edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from folio.calc.bonds import bond_risks
from folio.calc.valuation import CashValue, PositionValue, Valuation
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory
from folio.domain.money import Money, sum_money, to_decimal
from folio.errors import ValuationError
from folio.scenarios.history import replay
from folio.scenarios.shocks import Moves, Scenario, Window, revalue


@dataclass(frozen=True)
class StressedPosition:
    """One position before and after a scenario, in the base currency."""

    line: PositionValue
    price_change: Decimal      # every price shock and yield shift together, as a fraction
    fx_change: Decimal         # of the instrument's currency against the base currency
    stressed_value: Money
    window: Window | None = None  # where a historical move was measured

    @property
    def pnl(self) -> Money:
        return self.stressed_value - self.line.base_value


@dataclass(frozen=True)
class StressedCash:
    """One cash balance before and after a scenario, in the base currency."""

    cash: CashValue
    fx_change: Decimal
    stressed_value: Money

    @property
    def currency(self) -> str:
        return self.cash.local_value.currency

    @property
    def pnl(self) -> Money:
        return self.stressed_value - self.cash.base_value


@dataclass(frozen=True)
class ScenarioResult:
    """A scenario run on one valuation: every line stressed, and the totals."""

    scenario: Scenario
    valuation: Valuation
    positions: tuple[StressedPosition, ...]  # in valuation (instrument id) order
    cash: tuple[StressedCash, ...]           # in currency order
    window: Window | None = None             # the replayed window of a whole-book historical scenario

    @property
    def pnl(self) -> Money:
        lines = [line.pnl for line in self.positions] + [cash.pnl for cash in self.cash]
        return sum_money(lines, self.valuation.base_currency)

    @property
    def pnl_share(self) -> Decimal:
        """P&L as a fraction of NAV before the scenario."""
        return self.pnl.amount / self.valuation.nav.amount

    @property
    def stressed_nav(self) -> Money:
        return self.valuation.nav + self.pnl

    def worst_position(self) -> StressedPosition | None:
        """The position that loses most, ties by instrument id; None when nothing loses."""
        losers = [line for line in self.positions if line.pnl.amount < 0]
        return min(losers, key=lambda line: (line.pnl.amount, line.line.instrument.id), default=None)


class Stresser:
    """Runs scenarios on one valuation.

    Bond durations are worked out the first time a scenario shifts yields
    and reused for the rest, so ``compare`` finds each bond's yield once.
    """

    def __init__(self, valuation: Valuation, prices: PriceHistory, fx: FxRates):
        self.valuation = valuation
        self.prices = prices
        self.fx = fx
        self._durations: dict[str, Decimal] | None = None

    def durations(self) -> dict[str, Decimal]:
        """Modified duration of each bond held, keyed by instrument id."""
        if self._durations is None:
            try:
                risks = bond_risks(self.valuation)
            except ValueError as exc:
                raise ValuationError(f"cannot shift yields: {exc}") from None
            self._durations = {risk.line.instrument.id: to_decimal(risk.modified_duration) for risk in risks}
        return self._durations

    def moves(self, scenario: Scenario) -> Moves:
        """What ``scenario`` does to each held instrument and each currency."""
        if scenario.historical is not None:
            return replay(scenario.historical, self.valuation, self.prices, self.fx)
        durations = self.durations() if scenario.yields else {}
        changes: dict[str, Decimal] = {}
        for line in self.valuation.positions:
            instrument = line.instrument
            factor = Decimal(1)
            for shock in scenario.prices:
                if shock.applies_to(instrument):
                    factor *= 1 + shock.change
            for shift in scenario.yields:
                if shift.applies_to(instrument):
                    factor *= 1 + shift.price_change(durations[instrument.id])
            changes[instrument.id] = factor - 1
        return Moves(changes, {shock.currency: shock.change for shock in scenario.fx})

    def run(self, scenario: Scenario) -> ScenarioResult:
        moves = self.moves(scenario)
        base = self.valuation.base_currency
        positions = []
        for line in self.valuation.positions:
            instrument = line.instrument
            price, fx = moves.price_change(instrument.id), moves.fx_change(instrument.currency)
            stressed = Money(revalue(line.base_value.amount, price, fx), base)
            positions.append(StressedPosition(line, price, fx, stressed, moves.windows.get(instrument.id)))
        cash = []
        for balance in self.valuation.cash:
            fx = moves.fx_change(balance.local_value.currency)
            cash.append(StressedCash(balance, fx, Money(revalue(balance.base_value.amount, Decimal(0), fx), base)))
        return ScenarioResult(scenario, self.valuation, tuple(positions), tuple(cash), moves.window)

    def run_all(self, scenarios: Iterable[Scenario]) -> list[ScenarioResult]:
        """Every scenario, in the order given."""
        return [self.run(scenario) for scenario in scenarios]
