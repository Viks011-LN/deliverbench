import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

from folio.errors import ConfigError
from folio.scenarios.scenario_file import check_against, find, parse_scenarios, read_scenarios
from folio.scenarios.shocks import HistoricalSpec, PriceShock, YieldShift, signed_percent

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "scenarios.toml"


def parse(text):
    return parse_scenarios(tomllib.loads(text), source="test.toml")


def test_reads_every_shock_type():
    (scenario,) = parse("""
        [scenarios.mixed]
        description = "  Equities down,   dollar down "
        kind = { equity = -20 }
        sector = { Technology = -12.5 }
        instrument = { CCC = 5 }
        fx = { USD = -10 }
        yield_bp = 75
    """)
    assert scenario.name == "mixed"
    assert scenario.description == "Equities down, dollar down"
    assert scenario.prices == (
        PriceShock("kind", "equity", Decimal("-0.2")),
        PriceShock("sector", "Technology", Decimal("-0.125")),
        PriceShock("instrument", "CCC", Decimal("0.05")),
    )
    assert [(shock.currency, shock.change) for shock in scenario.fx] == [("USD", Decimal("-0.1"))]
    assert scenario.yields == (YieldShift(Decimal(75)),)
    assert scenario.historical is None
    assert scenario.shock_summary() == [
        "kind equity -20%", "sector Technology -12.5%", "instrument CCC +5%", "USD -10%", "yields +75bp"]


def test_yield_shift_by_currency_and_historical_defaults():
    replay, curve = parse("""
        [scenarios.uk-curve]
        yield_bp = { USD = -25, GBP = 150 }

        [scenarios.replay]
        historical = { days = 5 }
    """)
    assert curve.yields == (YieldShift(Decimal(150), "GBP"), YieldShift(Decimal(-25), "USD"))
    assert curve.shock_summary() == ["GBP yields +150bp", "USD yields -25bp"]
    assert replay.historical == HistoricalSpec(5, "book")
    assert replay.shock_summary() == ["worst 5-day move of the book"]


def test_scenarios_come_back_in_name_order():
    text = "".join(f"[scenarios.{name}]\nyield_bp = 10\n" for name in ("zeta", "alpha", "mid"))
    assert [scenario.name for scenario in parse(text)] == ["alpha", "mid", "zeta"]


def test_signed_percent_reads_like_the_file():
    assert signed_percent(Decimal("-0.125")) == "-12.5%"
    assert signed_percent(Decimal("0.05")) == "+5%"
    assert signed_percent(Decimal("-0.2")) == "-20%"


@pytest.mark.parametrize("body, message", [
    ("sectr = { Energy = -10 }", "unknown key 'sectr' (did you mean sector?)"),
    ('kind = { equity = "-20" }', "kind.equity must be a percentage, got '-20'"),
    ("kind = { equity = true }", "kind.equity must be a percentage, got True"),
    ("kind = { equities = -20 }", "unknown kind 'equities'; expected one of: equity, bond, fund"),
    ("instrument = { AAA = -120 }", "instrument AAA -120%: nothing can lose more than 100%"),
    ("fx = { usd = 5 }", "invalid currency code 'usd'"),
    ("sector = {}", "sector must be a table of percentages"),
    ("fx = -10", "fx must be a table of percentages"),
    ("yield_bp = 1500", "shifts are limited to 1000 bp"),
    ('yield_bp = "up"', "yield_bp must be a number of basis points"),
    ("yield_bp = {}", "yield_bp is an empty table"),
    ('description = "nothing happens"', "no shocks"),
    ("description = 3\nyield_bp = 10", "description must be a string, got 3"),
    ("historical = { days = 5 }\nyield_bp = 10", "cannot have shocks of its own"),
    ('historical = { days = 5, scope = "sector" }', "historical scope must be one of: book, instrument"),
    ("historical = { days = 0 }", "1 or more, got 0"),
    ("historical = { days = 2.5 }", "whole number of business days"),
    ("historical = { scope = \"book\" }", "historical needs days"),
    ("historical = { days = 5, since = 2026-06-01 }", "unknown key historical.since"),
    ("historical = 5", "historical must be a table"),
])
def test_bad_scenarios_name_file_scenario_and_key(body, message):
    with pytest.raises(ConfigError) as caught:
        parse(f"[scenarios.broken]\n{body}\n")
    assert str(caught.value).startswith("test.toml: scenario broken: ")
    assert message in str(caught.value)


@pytest.mark.parametrize("text, message", [
    ("", "no scenarios; add a [scenarios.<name>] table"),
    ("scenario = 1", "unknown top-level key 'scenario'"),
    ('[scenarios."equity crash"]\nyield_bp = 10', "invalid scenario name 'equity crash'"),
    ("[scenarios]\nbroken = 3", "scenario broken: expected a table of shocks"),
])
def test_bad_file_layout(text, message):
    with pytest.raises(ConfigError, match="^test.toml: ") as caught:
        parse(text)
    assert message in str(caught.value)


def test_read_scenarios_errors_name_the_path(tmp_path):
    with pytest.raises(ConfigError, match="scenario file not found: .*nowhere.toml"):
        read_scenarios(tmp_path / "nowhere.toml")
    broken = tmp_path / "broken.toml"
    broken.write_text("[scenarios.a]\nkind = { equity = }\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"broken.toml: .*line 2"):
        read_scenarios(broken)


def test_check_against_the_instruments(small_book):
    universe = small_book[0]
    fine = parse("""
        [scenarios.ok]
        sector = { Technology = -10 }
        instrument = { CCC = -5 }
        fx = { USD = 3 }
    """)
    check_against(fine, universe, "GBP", source="test.toml")
    with pytest.raises(ConfigError, match=r"scenario typo: sector 'Technlogy' is not in instruments.csv "
                                          r"\(did you mean Technology\?\)"):
        check_against(parse("[scenarios.typo]\nsector = { Technlogy = -10 }"), universe, "GBP")
    with pytest.raises(ConfigError, match="instrument 'ZZZ' is not in instruments.csv"):
        check_against(parse("[scenarios.gone]\ninstrument = { ZZZ = -10 }"), universe, "GBP")
    with pytest.raises(ConfigError, match="fx.GBP: GBP is the base currency"):
        check_against(parse("[scenarios.pound]\nfx = { GBP = -10 }"), universe, "GBP")


def test_find_suggests_the_closest_name():
    scenarios = parse("[scenarios.rates-up]\nyield_bp = 100\n[scenarios.rates-down]\nyield_bp = -100")
    assert find(scenarios, "rates-up").yields == (YieldShift(Decimal(100)),)
    with pytest.raises(ConfigError, match=r"has no scenario 'rates-upp' \(did you mean rates-up\?\)"):
        find(scenarios, "rates-upp")


def test_sample_file_reads_and_matches_the_sample_instruments(universe):
    scenarios = read_scenarios(SAMPLE)
    assert 6 <= len(scenarios) <= 8
    check_against(scenarios, universe, "GBP")
    assert all(scenario.description for scenario in scenarios)
    scopes = {scenario.historical.scope for scenario in scenarios if scenario.historical is not None}
    assert scopes == {"book", "instrument"}
    assert any(scenario.yields for scenario in scenarios)
    assert any(scenario.fx and scenario.prices for scenario in scenarios)
