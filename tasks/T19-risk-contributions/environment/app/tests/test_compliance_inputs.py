"""The two compliance input files: the mandate (guidelines.toml) and the restricted list."""

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.compliance.mandate import parse_mandate
from folio.compliance.registry import KINDS, read_mandate
from folio.compliance.restricted_list import load_restricted, parse_restricted
from folio.domain.instruments import Bond, Equity
from folio.errors import ConfigError, DataError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = "instrument,issuer,reason,from,until\n"

ALPHA = Equity(id="ALPHA", name="Alpha plc", sector="Energy", currency="GBP")
BETA = Equity(id="BETA", name="Beta plc", sector="Industrials", currency="GBP")
BETA_BOND = Bond(id="BETA30", name="Beta 5% 2030", sector="Industrials", currency="GBP", issuer="BETA",
                 coupon_rate=Decimal("0.05"), maturity=date(2030, 1, 1))


def mandate_doc(**guidelines):
    """A parsed mandate for portfolio TEST; each keyword is one [guidelines.<key>] table."""
    return {"mandate": {"portfolio": "TEST"}, "guidelines": guidelines or {"max_positions": {"value": 30}}}


def test_sample_mandate():
    mandate = read_mandate(DATA_DIR / "guidelines.toml")
    assert (mandate.portfolio, mandate.client, mandate.source) == (
        "GBL-BAL", "Ellesmere Staff Pension Scheme", "guidelines.toml")
    issuer = mandate.term("issuer_max_share")
    assert issuer.value == Decimal("0.07") and isinstance(issuer.value, Decimal)
    assert issuer.note.startswith("Schedule 2")
    assert mandate.term("max_positions").value == Decimal(40)
    assert mandate.term("restricted_holdings").value is None
    assert all(term.enabled for term in mandate.terms)


def test_terms_come_in_registry_order_not_file_order():
    mandate = parse_mandate(mandate_doc(min_cash_share={"value": 0.02}, issuer_max_share={"value": 0.05}), KINDS)
    assert [term.key for term in mandate.terms] == ["issuer_max_share", "min_cash_share"]
    assert mandate.term("min_cash_share").value == Decimal("0.02")  # via repr: exactly 0.02, not a binary float


def test_switched_off_and_absent_guidelines():
    mandate = parse_mandate(mandate_doc(fund_max_share={"value": 0.1, "enabled": False, "note": "Waived to March"}),
                            KINDS)
    term = mandate.term("fund_max_share")
    assert (term.value, term.enabled, term.note) == (Decimal("0.1"), False, "Waived to March")
    assert not mandate.in_force("fund_max_share") and mandate.enabled_terms == ()
    assert mandate.term("issuer_max_share") is None and not mandate.in_force("issuer_max_share")
    assert parse_mandate(mandate_doc(), KINDS).client == "TEST"  # the client defaults to the portfolio


@pytest.mark.parametrize("key, table, message", [
    ("issuer_max_shar", {"value": 0.05},
     r"unknown guideline guidelines\.issuer_max_shar \(did you mean guidelines\.issuer_max_share\?\)"),
    ("issuer_max_share", {"valeu": 0.05},
     r"unknown key guidelines\.issuer_max_share\.valeu \(did you mean guidelines\.issuer_max_share\.value\?\)"),
    ("issuer_max_share", {"note": "Schedule 2"}, r"guidelines\.issuer_max_share has no value"),
    ("issuer_max_share", {"value": "5%"},
     r"guidelines\.issuer_max_share\.value must be a fraction, not a percentage: write 0\.05 for 5%"),
    ("issuer_max_share", {"value": "0.05"}, r"guidelines\.issuer_max_share\.value must be a number such as 0\.05"),
    ("issuer_max_share", {"value": True}, r"guidelines\.issuer_max_share\.value must be a number"),
    ("issuer_max_share", {"value": float("inf")}, r"guidelines\.issuer_max_share\.value must be a finite number"),
    ("issuer_max_share", {"value": 1.5},
     r"guidelines\.issuer_max_share\.value must be a fraction of NAV above 0 and at most 1, got 1\.5"),
    ("country_max_share", {"value": 0}, r"guidelines\.country_max_share\.value must be a fraction of NAV above 0"),
    ("govt_min_share", {"value": 1}, r"guidelines\.govt_min_share\.value must be a fraction of NAV above 0 and below 1"),
    ("max_positions", {"value": 40.5}, r"guidelines\.max_positions\.value must be a whole number, got 40\.5"),
    ("max_positions", {"value": 0}, r"guidelines\.max_positions\.value must be 1 or more, got 0"),
    ("restricted_holdings", {"value": 0}, r"guidelines\.restricted_holdings takes no value"),
    ("fund_max_share", {"value": 0.1, "enabled": "no"}, r"guidelines\.fund_max_share\.enabled must be true or false"),
    ("fund_max_share", {"value": 0.1, "note": " "}, r"guidelines\.fund_max_share\.note must be a non-empty string"),
    ("fund_max_share", 0.1, r"guidelines\.fund_max_share must be a table"),
])
def test_bad_guidelines_name_the_file_and_the_key(key, table, message):
    with pytest.raises(ConfigError, match=r"^gl\.toml: " + message):
        parse_mandate(mandate_doc(**{key: table}), KINDS, source="gl.toml")


@pytest.mark.parametrize("document, message", [
    ({"mandate": {"portfolio": "TEST"}, "guideline": {}},
     r"unknown section \[guideline\] \(did you mean \[guidelines\]\?\)"),
    ({"guidelines": {"max_positions": {"value": 30}}}, r"\[mandate\] is missing"),
    ({"mandate": {"client": "Someone"}, "guidelines": {}}, r"mandate\.portfolio must be a non-empty string, got None"),
    ({"mandate": {"portfolio": "TEST", "owner": "Ops"}, "guidelines": {}},
     r"unknown key mandate\.owner; expected one of: client, portfolio"),
    ({"mandate": {"portfolio": "TEST"}, "guidelines": {}}, "no guidelines"),
])
def test_bad_mandate_sections(document, message):
    with pytest.raises(ConfigError, match=message):
        parse_mandate(document, KINDS)


def test_mandate_file_errors_and_portfolio_check(tmp_path):
    with pytest.raises(ConfigError, match="mandate file not found"):
        read_mandate(tmp_path / "missing.toml")
    broken = tmp_path / "broken.toml"
    broken.write_text("[mandate]\nportfolio = GBL-BAL\n")
    with pytest.raises(ConfigError, match=r"^broken\.toml: "):
        read_mandate(broken)
    mandate = parse_mandate(mandate_doc(), KINDS, source="gl.toml")
    mandate.require_portfolio("TEST")
    with pytest.raises(ConfigError, match="gl.toml is the mandate for portfolio TEST, but the data folder holds GBL-BAL"):
        mandate.require_portfolio("GBL-BAL")


def test_sample_restricted_list():
    restricted = load_restricted(DATA_DIR / "restricted.csv")
    day = date(2026, 10, 30)
    assert (len(restricted), restricted.source) == (5, "restricted.csv")
    assert [entry.target for entry in restricted.in_force(day)] == ["FRXL", "NYQV", "TNSL"]
    assert [entry.describe() for entry in restricted.lifted(day)] == ["issuer MXTB"]
    assert [entry.describe() for entry in restricted.not_yet(day)] == ["issuer Brixham Shipping"]


def test_dates_are_inclusive_and_an_issuer_covers_all_it_issued():
    restricted = parse_restricted(io.StringIO(HEADER + ",BETA,Review,2026-03-02,2026-03-31\nALPHA,,Coal,2026-03-16,\n"))
    beta = restricted.entries[0]
    assert not beta.in_force(date(2026, 3, 1))
    assert beta.in_force(date(2026, 3, 2)) and beta.in_force(date(2026, 3, 31))
    assert not beta.in_force(date(2026, 4, 1))
    assert beta.covers(BETA) and beta.covers(BETA_BOND) and not beta.covers(ALPHA)
    assert restricted.restriction_for(BETA_BOND, date(2026, 3, 10)) is beta
    assert restricted.restriction_for(ALPHA, date(2026, 3, 10)) is None
    assert restricted.next_restriction(ALPHA, date(2026, 3, 10)).reason == "Coal"
    assert restricted.restriction_for(ALPHA, date(2027, 1, 4)).end is None  # no until: in force for good


def test_the_longest_standing_restriction_is_the_one_reported():
    restricted = parse_restricted(io.StringIO(HEADER + "BETA,,Later,2026-05-01,\n,BETA,Earlier,2026-02-02,\n"))
    assert restricted.restriction_for(BETA, date(2026, 6, 1)).reason == "Earlier"
    assert restricted.restriction_for(BETA_BOND, date(2026, 6, 1)).reason == "Earlier"


def test_comments_blank_rows_column_order_and_an_empty_list():
    restricted = parse_restricted(io.StringIO(
        "reason,from,issuer,instrument\n# trustees' list, as received\n,,,\nCoal,2026-01-05,,ALPHA\n"))
    assert [(entry.instrument, entry.reason, entry.end) for entry in restricted.entries] == [("ALPHA", "Coal", None)]
    assert len(parse_restricted(io.StringIO(HEADER))) == 0


@pytest.mark.parametrize("text, message", [
    ("", "list.csv: file is empty"),
    ("instrument,reason,from\n", "list.csv:1: missing column(s): issuer"),
    (HEADER.strip() + ",owner\n", "list.csv:1: unknown column 'owner'"),
    (HEADER + "ALPHA,Alpha,Coal,2026-01-05,\n", "list.csv:2: give an instrument or an issuer, not both"),
    (HEADER + ",,Coal,2026-01-05,\n", "list.csv:2: no instrument or issuer"),
    (HEADER + "ALPHA,,,2026-01-05,\n", "list.csv:2: ALPHA: reason is empty"),
    (HEADER + "ALPHA,,Coal,,\n", "list.csv:2: ALPHA: from is required"),
    (HEADER + "ALPHA,,Coal,05/01/2026,\n", "list.csv:2: from '05/01/2026' is not a date"),
    (HEADER + "ALPHA,,Coal,2026-02-01,2026-01-31\n", "list.csv:2: ALPHA: until 2026-01-31 is before from 2026-02-01"),
    (HEADER + "ALPHA,,Coal,2026-01-05,,surprise\n", "list.csv:2: row has more cells"),
    (HEADER + "ALPHA,,Coal,2026-01-05,\nALPHA,,Again,2026-01-05,\n",
     "list.csv:3: ALPHA is already listed from 2026-01-05 (line 2)"),
])
def test_restricted_list_errors_name_file_and_line(text, message):
    with pytest.raises(DataError) as caught:
        parse_restricted(io.StringIO(text), source="list.csv")
    assert str(caught.value).startswith(message)


def test_missing_restricted_list(tmp_path):
    with pytest.raises(DataError, match="restricted list not found"):
        load_restricted(tmp_path / "restricted.csv")
