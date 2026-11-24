"""Build the configured rules and run them against a valuation."""

from __future__ import annotations

from dataclasses import dataclass

from folio.calc.risk import RiskSummary, VolShares
from folio.calc.valuation import Valuation
from folio.config.settings import LimitSettings
from folio.errors import ConfigError
from folio.limits.rules import Breach, CurrencyShare, NameShare, NameVolShare, Rule, SectorShare, VarShare

# Every rule folio knows, in the order their breaches are printed.
RULES: tuple[type[Rule], ...] = (SectorShare, NameShare, CurrencyShare, VarShare, NameVolShare)


@dataclass(frozen=True)
class CheckResult:
    """What run_checks() found; ``ok`` is True when nothing is over its limit."""

    breaches: tuple[Breach, ...]
    rules: tuple[str, ...]  # names of the rules that ran
    nearest: tuple[Breach, ...] = ()  # largest measurement of each rule that did not breach

    @property
    def ok(self) -> bool:
        return not self.breaches


def build_rules(limits: LimitSettings) -> list[Rule]:
    """One rule per entry in RULES, minus those named in ``limits.disabled``."""
    known = {cls.name for cls in RULES}
    unknown = sorted(set(limits.disabled) - known)
    if unknown:
        raise ConfigError(f"limits.disabled names unknown rule(s) {', '.join(unknown)}; "
                          f"known rules: {', '.join(sorted(known))}")
    return [cls.from_settings(limits) for cls in RULES if cls.name not in limits.disabled]


def needs_risk(rules: list[Rule]) -> bool:
    """Whether any rule needs a risk summary, which means building a NAV history first."""
    return any(rule.needs_risk for rule in rules)


def needs_vol_shares(rules: list[Rule]) -> bool:
    """Whether any rule needs the positions' shares of volatility (calc.risk.vol_shares)."""
    return any(rule.needs_vol_shares for rule in rules)


def run_checks(valuation: Valuation, rules: list[Rule], risk: RiskSummary | None = None,
               vol_shares: VolShares | None = None) -> CheckResult:
    """Run ``rules`` in order. Breaches keep the rule order, then each rule's own order.

    Shares of volatility need the price history, which a caller holding only a
    valuation does not have: without ``vol_shares`` the rules that need them
    measure nothing. ``folio check-limits`` always passes them when such a rule
    is enabled.
    """
    breaches: list[Breach] = []
    nearest: list[Breach] = []
    for rule in rules:
        if rule.needs_vol_shares and vol_shares is None:
            continue
        found = rule.check(valuation, risk, vol_shares)
        breaches.extend(found)
        if not found:
            closest = rule.closest(valuation, risk, vol_shares)
            if closest is not None:
                nearest.append(closest)
    return CheckResult(tuple(breaches), tuple(rule.name for rule in rules), tuple(nearest))
