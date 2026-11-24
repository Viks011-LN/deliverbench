"""Limit rules.

A rule measures one kind of concentration on a valuation (and, for VaR, on a
risk summary; for shares of volatility, on calc.risk.vol_shares()) and
compares each measurement with its threshold. Every rule has

* ``name``: what appears in the output and what ``limits.disabled`` lists;
* ``setting``: the field of LimitSettings that holds its threshold.

A rule only has to implement measure(); check() and closest() are shared.
All thresholds are fractions of NAV and a breach is strictly above the
threshold, compared on exact values (the printed percentages are rounded).
One line per breach, always in the same format:

    BREACH sector_share Technology: 31.2% > 25.0%
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from folio.aggregate.rollup import rollup, share
from folio.calc import exposure
from folio.calc.risk import RiskSummary, VolShares, confidence_label
from folio.calc.valuation import Valuation
from folio.config.settings import LimitSettings
from folio.domain.money import to_decimal
from folio.report.tables import format_pct

Measurement = tuple[str, Decimal]  # (subject, fraction of NAV)


@dataclass(frozen=True)
class Breach:
    """One measurement against its limit; a breach when ``actual`` is above ``limit``."""

    rule: str
    subject: str      # what is over the limit: a sector, an issuer, a currency...
    actual: Decimal   # fraction of NAV
    limit: Decimal    # fraction of NAV

    @property
    def is_breach(self) -> bool:
        return self.actual > self.limit

    def format(self, places: int = 1) -> str:
        actual, limit = format_pct(self.actual, places), format_pct(self.limit, places)
        if self.is_breach:
            return f"BREACH {self.rule} {self.subject}: {actual} > {limit}"
        return f"ok {self.rule} {self.subject}: {actual} <= {limit}"


class Rule(abc.ABC):
    """Base class: subclasses set ``name`` and ``setting`` and implement measure()."""

    name: ClassVar[str]
    setting: ClassVar[str]
    needs_risk: ClassVar[bool] = False
    needs_vol_shares: ClassVar[bool] = False

    def __init__(self, threshold: Decimal):
        self.threshold = threshold

    @classmethod
    def from_settings(cls, limits: LimitSettings) -> "Rule":
        return cls(getattr(limits, cls.setting))

    @abc.abstractmethod
    def measure(self, valuation: Valuation, risk: RiskSummary | None = None,
                shares: VolShares | None = None) -> list[Measurement]:
        """Everything this rule limits, largest first (ties by subject)."""

    def check(self, valuation: Valuation, risk: RiskSummary | None = None,
              shares: VolShares | None = None) -> list[Breach]:
        """The measurements above the threshold, largest first."""
        return [
            Breach(self.name, subject, actual, self.threshold)
            for subject, actual in self.measure(valuation, risk, shares)
            if actual > self.threshold
        ]

    def closest(self, valuation: Valuation, risk: RiskSummary | None = None,
                shares: VolShares | None = None) -> Breach | None:
        """The largest measurement, breach or not, for ``check-limits --verbose``."""
        measured = self.measure(valuation, risk, shares)
        if not measured:
            return None
        subject, actual = measured[0]
        return Breach(self.name, subject, actual, self.threshold)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.setting}={self.threshold})"


class SectorShare(Rule):
    """No sector may be more than ``limits.sector_max_share`` of NAV."""

    name = "sector_share"
    setting = "sector_max_share"

    def measure(self, valuation, risk=None, shares=None):
        return [(row.key, row.share) for row in exposure.by_sector(valuation).rows]


class NameShare(Rule):
    """No single issuer may be more than ``limits.name_max_share`` of NAV.

    Instruments of the same issuer (a company's shares and its bonds) count
    together; see Instrument.issuer_key.
    """

    name = "name_share"
    setting = "name_max_share"

    def measure(self, valuation, risk=None, shares=None):
        groups = rollup(valuation.positions, key=lambda line: line.instrument.issuer_key,
                        value=lambda line: line.base_value.amount)
        return [(group.key, share(group.total, valuation.nav.amount)) for group in groups]


class CurrencyShare(Rule):
    """No currency other than the base may be more than ``limits.currency_max_share`` of NAV.

    Cash counts: a USD balance is USD exposure just like a USD bond.
    """

    name = "currency_share"
    setting = "currency_max_share"

    def measure(self, valuation, risk=None, shares=None):
        rows = exposure.by_currency(valuation).rows
        return [(row.key, row.share) for row in rows if row.key != valuation.base_currency]


class VarShare(Rule):
    """Historical VaR may not be more than ``limits.var_max_share`` of NAV."""

    name = "var_share"
    setting = "var_max_share"
    needs_risk = True

    def measure(self, valuation, risk=None, shares=None):
        if risk is None:
            raise ValueError(f"rule {self.name} needs a risk summary")
        subject = f"{confidence_label(risk.confidence)} {risk.horizon_days}d"
        return [(subject, to_decimal(risk.var))]


class NameVolShare(Rule):
    """No single issuer may carry more than ``limits.name_vol_max_share`` of the portfolio's volatility.

    Shares of volatility come from calc.risk.vol_shares() (docs/risk-notes.md),
    summed by issuer as in NameShare; cash is not a name, and a negative share
    never breaches. They need the price history, which a valuation does not
    carry, so the caller passes them in; without them the rule measures nothing.
    """

    name = "name_vol_share"
    setting = "name_vol_max_share"
    needs_vol_shares = True

    def measure(self, valuation, risk=None, shares=None):
        if shares is None:
            return []
        return [(group.key, group.total)
                for group in shares.by_group(valuation, lambda line: line.instrument.issuer_key)]
