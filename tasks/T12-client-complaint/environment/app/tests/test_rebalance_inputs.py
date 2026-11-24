"""The two rebalancing inputs: targets.csv and trading.toml."""

import tomllib
from decimal import Decimal
from pathlib import Path

import pytest

from folio.domain.money import Money
from folio.errors import DataError
from folio.rebalance.dealing import load_rules, parse_rules
from folio.rebalance.targets import load_targets, parse_targets

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = "scope,key,weight,band\n"
# Valid for small_book except for the cash row, which each case adds.
NO_CASH = "instrument,AAA,0.5,0.02\nsector,Government,0.3,0.02\ninstrument,CCC,0.15,0.01\n"


def read_targets(text, universe):
    return parse_targets(text.splitlines(), universe, source="targets.csv")


def read_rules(text, universe):
    return parse_rules(tomllib.loads(text), universe, "GBP", source="trading.toml")


def test_sample_targets(universe):
    model = load_targets(DATA_DIR / "targets.csv", universe)
    assert len(model) == 10
    assert sum(target.weight for target in model) == 1
    assert model.cash.weight == Decimal("0.04")
    assert model.for_instrument(universe["GEIF"]).describe() == "instrument GEIF"
    assert model.for_instrument(universe["KIWQ"]).describe() == "sector Technology"
    assert model.for_instrument(universe["FRXL"]).describe() == "sector Industrials"  # covered, though not held


def test_comments_blank_lines_and_extra_columns(small_book):
    universe = small_book[0]
    model = read_targets("# model of 1 November\n"
                         "\n"
                         "Scope,Key,Weight,Band,Note\n"
                         "instrument,AAA,0.5,0.02,core holding\n"
                         "# the bond\n"
                         "sector,Government,0.3,0.02,\n"
                         "instrument,CCC,0.15,0.01\n"
                         "CASH,,0.05,0.01\n", universe)
    assert [target.describe() for target in model] == ["instrument AAA", "sector Government", "instrument CCC", "cash"]
    assert [target.line for target in model] == [4, 6, 7, 8]
    assert [target.label for target in model] == ["AAA", "Government", "CCC", "Cash"]
    assert model.for_instrument(universe["BBB"]).key == "Government"


@pytest.mark.parametrize("text, message", [
    ("", "targets.csv: file is empty"),
    ("# nothing yet\n" + HEADER, "targets.csv: no targets in file"),
    ("scope,key,weight\n", "targets.csv:1: missing column(s): band"),
    (HEADER + "region,Europe,0.95,0.01\ncash,,0.05,0.01\n", "targets.csv:2: unknown scope 'region'"),
    (HEADER + "instrument,ZZZ,0.95,0.01\ncash,,0.05,0.01\n",
     "targets.csv:2: unknown instrument 'ZZZ': it is not in instruments.csv"),
    (HEADER + "sector,Energy,0.95,0.01\ncash,,0.05,0.01\n",
     "targets.csv:2: unknown sector 'Energy'; instruments.csv has Diversified, Government, Technology"),
    (HEADER + NO_CASH + "cash,EUR,0.05,0.01\n", "targets.csv:5: the cash target takes no key, got 'EUR'"),
    (HEADER + NO_CASH + "cash,,0.05,\n", "targets.csv:5: band is required"),
    (HEADER + NO_CASH + "cash,,-0.05,0.01\n", "targets.csv:5: weight -0.05 must be a fraction of NAV"),
    (HEADER + NO_CASH + "instrument,AAA,0.05,0.01\n",
     "targets.csv:5: second target for instrument AAA (the first is on line 2)"),
    (HEADER + NO_CASH, "targets.csv: no cash target"),
    (HEADER + NO_CASH + "cash,,0.04,0.01\n", "targets.csv: weights add up to 0.99, not 1 (the cash target counts too)"),
    (HEADER + "sector,Technology,0.5,0.02\ninstrument,AAA,0.5,0.02\ncash,,0,0\n",
     "targets.csv:3: instrument AAA is in sector Technology, which has its own target on line 2"),
])
def test_target_errors_name_file_and_line(small_book, text, message):
    with pytest.raises(DataError) as caught:
        read_targets(text, small_book[0])
    assert str(caught.value).startswith(message)


def test_a_third_written_out_is_close_enough(small_book):
    model = read_targets(HEADER + "instrument,AAA,0.333333,0.02\nsector,Government,0.333333,0.02\n"
                         "instrument,CCC,0.333334,0.01\ncash,,0,0\n", small_book[0])
    assert len(model) == 4


def test_missing_targets_file(universe, tmp_path):
    with pytest.raises(DataError, match=r"targets file not found: .*nowhere\.csv \(use --targets\)"):
        load_targets(tmp_path / "nowhere.csv", universe)


def test_sample_rules(universe):
    rules = load_rules(DATA_DIR / "trading.toml", universe, "GBP")
    assert rules.min_ticket == Money(25000, "GBP")
    assert rules.cash_buffer == Decimal("0.01")
    assert rules.bonds_in_nominal_multiples
    lots = {instrument_id: rules.lot_for(universe[instrument_id])
            for instrument_id in ("ADZM", "KIWQ", "UKT34", "JGB30", "GEIF")}
    assert lots == {"ADZM": 1, "KIWQ": 100, "UKT34": 1000, "JGB30": 1000000, "GEIF": 1}


def test_every_rule_is_optional(small_book):
    universe = small_book[0]
    rules = read_rules("", universe)
    assert rules.min_ticket == Money(0, "GBP")
    assert rules.cash_buffer == 0
    assert [rules.lot_for(universe[key]) for key in ("AAA", "BBB", "CCC")] == [1, 1, 1]


def test_bonds_outside_nominal_multiples_deal_in_any_whole_nominal(small_book):
    universe = small_book[0]
    rules = read_rules("bonds_in_nominal_multiples = false\n[lots]\nbond = 1000\nequity = 10\n", universe)
    assert rules.lot_for(universe["BBB"]) == 1
    assert rules.lot_for(universe["AAA"]) == 10
    nominal = read_rules("[lots]\nbond = 1000\n[instrument_lots]\nBBB = 5000\n", universe)
    assert nominal.lot_for(universe["BBB"]) == 5000


@pytest.mark.parametrize("text, message", [
    ("min_tickets = 100", "trading.toml: unknown key min_tickets (did you mean min_ticket?)"),
    ("[lots]\nequities = 10", "trading.toml: unknown key lots.equities (did you mean lots.equity?)"),
    ("[lots]\nequity = 0", "trading.toml: lots.equity must be above 0, got 0"),
    ("cash_buffer = 1", "trading.toml: cash_buffer must be a share of NAV from 0 up to 1"),
    ("min_ticket = -5", "trading.toml: min_ticket must be 0 or more, got -5"),
    ("bonds_in_nominal_multiples = 1", "trading.toml: bonds_in_nominal_multiples must be true or false, got 1"),
    ("[instrument_lots]\nZZZ = 100", "trading.toml: instrument_lots lists ZZZ, which is not in instruments.csv"),
    ("bonds_in_nominal_multiples = false\n[instrument_lots]\nBBB = 1000",
     "trading.toml: instrument_lots.BBB has no effect"),
])
def test_rule_errors_name_the_file(small_book, text, message):
    with pytest.raises(DataError) as caught:
        read_rules(text, small_book[0])
    assert str(caught.value).startswith(message)


def test_rules_file_missing_or_not_toml(universe, tmp_path):
    with pytest.raises(DataError, match=r"dealing rules file not found: .*\(use --rules\)"):
        load_rules(tmp_path / "trading.toml", universe, "GBP")
    broken = tmp_path / "trading.toml"
    broken.write_text("min_ticket = = 5\n", encoding="utf-8")
    with pytest.raises(DataError, match=r"^trading\.toml: not valid TOML"):
        load_rules(broken, universe, "GBP")
