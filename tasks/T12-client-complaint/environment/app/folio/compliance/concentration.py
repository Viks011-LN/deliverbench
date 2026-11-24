"""Concentration guidelines: how much of NAV may sit with one issuer, one country or one fund.

All three look at positions only; cash has no issuer and no country. Each
measures every subject it covers, largest first with ties by name, so the
first reading is the tightest and violations print biggest first.

* ``issuer_max_share`` adds a company's shares and bonds together through
  Instrument.issuer_key, as folio's own name limit does. Government bonds are
  left out: the mandate caps sovereign debt by country, not by issuer. Funds
  are left out too, because fund_max_share covers them.
* ``country_max_share`` uses each instrument's country. Funds are left out:
  a fund's country is where it is domiciled, which says nothing about where
  its money is invested. Holdings without a country count together under
  NO_COUNTRY, so a gap in instruments.csv cannot hide a concentration.
* ``fund_max_share`` caps each fund on its own.
"""

from __future__ import annotations

from typing import Callable, Iterable

from folio.aggregate.rollup import rollup, share
from folio.calc.valuation import PositionValue, Valuation
from folio.compliance.guideline import MAX_SHARE, Guideline, Reading, is_fund, is_government_bond

NO_COUNTRY = "(no country)"


def _shares(guideline: Guideline, valuation: Valuation, lines: Iterable[PositionValue],
            key: Callable[[PositionValue], str]) -> list[Reading]:
    """Group ``lines`` by ``key`` and read each group as a share of NAV, largest first."""
    groups = rollup(lines, key=key, value=lambda line: line.base_value.amount)
    return [guideline.reading(group.key, share(group.total, valuation.nav.amount)) for group in groups]


def _direct(valuation: Valuation) -> list[PositionValue]:
    """Positions held directly, that is everything but funds."""
    return [line for line in valuation.positions if not is_fund(line.instrument)]


class IssuerMaxShare(Guideline):
    """No issuer other than a government may be more than the limit of NAV."""

    key = "issuer_max_share"
    kind = MAX_SHARE
    title = "each issuer but governments and funds"
    nothing_to_measure = "no corporate holdings"

    def measure(self, valuation):
        lines = [line for line in _direct(valuation) if not is_government_bond(line.instrument)]
        return _shares(self, valuation, lines, key=lambda line: line.instrument.issuer_key)


class CountryMaxShare(Guideline):
    """No country may be more than the limit of NAV, counting direct holdings."""

    key = "country_max_share"
    kind = MAX_SHARE
    title = "each country, direct holdings"
    nothing_to_measure = "no direct holdings"

    def measure(self, valuation):
        return _shares(self, valuation, _direct(valuation),
                       key=lambda line: line.instrument.country or NO_COUNTRY)


class FundMaxShare(Guideline):
    """No single fund may be more than the limit of NAV."""

    key = "fund_max_share"
    kind = MAX_SHARE
    title = "each fund"
    nothing_to_measure = "no funds held"

    def measure(self, valuation):
        funds = [line for line in valuation.positions if is_fund(line.instrument)]
        return _shares(self, valuation, funds, key=lambda line: line.instrument.id)
