import dataclasses
from decimal import Decimal

import pytest

from folio.calc.returns import nav_series
from folio.calc.risk import summarise_risk
from folio.errors import ConfigError
from folio.limits.checker import RULES, build_rules, needs_risk, run_checks
from folio.limits.rules import Breach, CurrencyShare, NameShare, SectorShare, VarShare


def limits_with(settings, **changes):
    return dataclasses.replace(settings.limits, **changes)


def test_breach_format():
    breach = Breach("sector_share", "Technology", Decimal("0.3124"), Decimal("0.25"))
    assert breach.format() == "BREACH sector_share Technology: 31.2% > 25.0%"
    assert breach.format(places=2) == "BREACH sector_share Technology: 31.24% > 25.00%"


def test_sector_rule_on_small_book(small_valuation):
    breaches = SectorShare(Decimal("0.25")).check(small_valuation)
    assert [b.format() for b in breaches] == [
        "BREACH sector_share Technology: 48.0% > 25.0%",
        "BREACH sector_share Government: 32.0% > 25.0%",
    ]
    assert SectorShare(Decimal("0.48")).check(small_valuation) == []  # equal to the limit is not a breach


def test_name_rule_groups_by_issuer(valuation):
    # Maxtead Bank shares (3.2%) and bonds (2.4%) count together.
    subjects = [b.subject for b in NameShare(Decimal("0.05")).check(valuation)]
    assert "MXTB" in subjects and "ADZM" in subjects
    assert "MXTB29" not in subjects


def test_currency_rule_skips_the_base_currency(valuation):
    breaches = CurrencyShare(Decimal("0.15")).check(valuation)
    assert [b.subject for b in breaches] == ["USD", "EUR"]


def test_var_rule(valuation, prices, fx, settings):
    risk = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    assert VarShare(Decimal("0.03")).check(valuation, risk) == []
    breach = VarShare(Decimal("0.005")).check(valuation, risk)[0]
    assert breach.subject == "99% 1d"
    assert breach.format().startswith("BREACH var_share 99% 1d: ")
    with pytest.raises(ValueError, match="needs a risk summary"):
        VarShare(Decimal("0.03")).check(valuation)


def test_sample_portfolio_is_within_default_limits(valuation, prices, fx, settings):
    rules = build_rules(settings.limits)
    risk = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    result = run_checks(valuation, rules, risk)
    assert result.ok
    assert result.rules == tuple(rule.name for rule in rules)


def test_nearest_measurements_for_rules_without_breaches(small_valuation, settings):
    limits = limits_with(settings, disabled=("var_share",), name_max_share=Decimal("0.5"))
    lines = [b.format() for b in run_checks(small_valuation, build_rules(limits)).nearest]
    assert "ok name_share AAA: 48.0% <= 50.0%" in lines
    assert "ok currency_share USD: 32.0% <= 35.0%" in lines
    assert not any(line.startswith("ok sector_share") for line in lines)  # it breached instead


def test_build_rules_reads_thresholds_from_settings(settings):
    rules = build_rules(limits_with(settings, sector_max_share=Decimal("0.3")))
    assert len(rules) == len(RULES)
    sector = next(rule for rule in rules if rule.name == "sector_share")
    assert sector.threshold == Decimal("0.3")
    assert needs_risk(rules)


def test_disabled_rules(settings):
    rules = build_rules(limits_with(settings, disabled=("var_share",)))
    assert "var_share" not in [rule.name for rule in rules]
    assert len(rules) == len(RULES) - 1
    assert not needs_risk(rules)
    with pytest.raises(ConfigError, match="unknown rule"):
        build_rules(limits_with(settings, disabled=("sector_shares",)))


def test_breaches_come_in_rule_order(small_valuation, settings):
    limits = limits_with(settings, disabled=("var_share",))
    result = run_checks(small_valuation, build_rules(limits))
    assert not result.ok
    rules_seen = [b.rule for b in result.breaches]
    assert rules_seen == sorted(rules_seen, key=[cls.name for cls in RULES].index)
    assert "currency_share" not in rules_seen  # USD is 32% of the book, under the 35% default
