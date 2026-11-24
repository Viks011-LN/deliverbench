"""Each guideline on small books with round numbers, then the registry and the checker on the sample."""

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.calc.valuation import value_portfolio
from folio.compliance.checker import run_guidelines
from folio.compliance.composition import GovtMinShare, MaxPositions, MinCashShare
from folio.compliance.concentration import NO_COUNTRY, CountryMaxShare, FundMaxShare, IssuerMaxShare
from folio.compliance.guideline import MAX_SHARE, MIN_SHARE, Reading
from folio.compliance.mandate import parse_mandate
from folio.compliance.registry import GUIDELINES, KINDS, build_guidelines, needs_restricted_list, read_mandate
from folio.compliance.restricted import RestrictedHoldings, restricted_holdings, upcoming_restrictions
from folio.compliance.restricted_list import load_restricted, parse_restricted
from folio.compliance.text import format_violation
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory, PricePoint
from folio.domain.instruments import Bond, Equity, Fund, Universe
from folio.domain.money import Money
from folio.domain.portfolio import Portfolio
from folio.domain.positions import Lot, Position

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 30)
HEADER = "instrument,issuer,reason,from,until\n"


def equity(code, country="GB"):
    return Equity(id=code, name=f"{code} plc", sector="Industrials", currency="GBP", country=country)


def bond(code, issuer, sector="Industrials", country="GB"):
    return Bond(id=code, name=f"{code} 4% 2031", sector=sector, currency="GBP", country=country, issuer=issuer,
                coupon_rate=Decimal("0.04"), maturity=date(2031, 6, 1))


def fund(code, country="IE", sector="Diversified"):
    return Fund(id=code, name=f"{code} Fund", sector=sector, currency="GBP", country=country)


def value_book(*lines, cash=0):
    """Value a GBP book on AS_OF; each line is (instrument, quantity, price), bought at that price."""
    universe = Universe(instrument for instrument, _, _ in lines)
    book = Portfolio("TEST", "Test book", cash={"GBP": Decimal(cash)} if cash else {})
    for instrument, quantity, price in lines:
        book.add_position(Position(instrument.id, (Lot(date(2026, 1, 5), Decimal(quantity), Decimal(price)),)))
    prices = PriceHistory({instrument.id: [PricePoint(AS_OF, Decimal(price))] for instrument, _, price in lines})
    return value_portfolio(book, universe, prices, FxRates({}), AS_OF, base_currency="GBP", stale_after_days=3)


@pytest.fixture
def book():
    """NAV 10,000 GBP: ACME shares 20% and bonds 10%, BOLT (US) 15%, a gilt 25%,
    funds FUNDX 18% and FUNDY 7%, cash 5%."""
    return value_book(
        (equity("ACME"), 100, 20),
        (bond("ACME31", issuer="ACME"), 1000, 100),
        (equity("BOLT", country="US"), 100, 15),
        (bond("GILT31", issuer="UK Treasury", sector="Government"), 2500, 100),
        (fund("FUNDX"), 1000, "1.8"),
        (fund("FUNDY", country="LU"), 100, 7),
        cash=500,
    )


def readings(guideline, valuation):
    return [(reading.subject, reading.actual) for reading in guideline.measure(valuation)]


def test_issuer_adds_shares_and_bonds_but_skips_governments_and_funds(book):
    assert readings(IssuerMaxShare(Decimal("0.3")), book) == [("ACME", Decimal("0.3")), ("BOLT", Decimal("0.15"))]
    assert IssuerMaxShare(Decimal("0.3")).check(book) == []  # equal to the limit is compliant
    [violation] = IssuerMaxShare(Decimal("0.25")).check(book)
    assert format_violation(violation) == "VIOLATION issuer_max_share ACME: 30.0% > 25.0%"
    assert violation.headroom == Decimal("-0.05")


def test_country_counts_direct_holdings_including_government_bonds(book):
    assert readings(CountryMaxShare(Decimal("0.5")), book) == [("GB", Decimal("0.55")), ("US", Decimal("0.15"))]
    [violation] = CountryMaxShare(Decimal("0.5")).check(book)
    assert format_violation(violation) == "VIOLATION country_max_share GB: 55.0% > 50.0%"


def test_holdings_without_a_country_count_together():
    valuation = value_book((equity("NOC1", country=""), 10, 30), (equity("NOC2", country=""), 10, 30),
                           (equity("FRA1", country="FR"), 10, 40))
    assert readings(CountryMaxShare(Decimal("0.5")), valuation) == [(NO_COUNTRY, Decimal("0.6")), ("FR", Decimal("0.4"))]


def test_fund_caps_each_fund_on_its_own(book):
    assert readings(FundMaxShare(Decimal("0.1")), book) == [("FUNDX", Decimal("0.18")), ("FUNDY", Decimal("0.07"))]
    assert [reading.subject for reading in FundMaxShare(Decimal("0.1")).check(book)] == ["FUNDX"]


def test_government_floor(book):
    assert GovtMinShare(Decimal("0.25")).check(book) == []  # exactly at the floor
    [violation] = GovtMinShare(Decimal("0.3")).check(book)
    assert format_violation(violation) == "VIOLATION govt_min_share government bonds: 25.0% < 30.0%"
    assert violation.headroom == Decimal("-0.05")


def test_government_bond_funds_do_not_count_toward_the_floor():
    valuation = value_book((fund("GOVF", sector="Government"), 100, 10), cash=1000)
    assert readings(GovtMinShare(Decimal("0.1")), valuation) == [("government bonds", Decimal(0))]


def test_max_positions_and_min_cash(book):
    assert readings(MaxPositions(Decimal(6)), book) == [("positions", Decimal(6))]  # cash is not a position
    [too_many] = MaxPositions(Decimal(5)).check(book)
    assert format_violation(too_many) == "VIOLATION max_positions positions: 6 > 5"
    assert MinCashShare(Decimal("0.05")).check(book) == []
    [short] = MinCashShare(Decimal("0.06")).check(book)
    assert format_violation(short) == "VIOLATION min_cash_share cash: 5.0% < 6.0%"


def test_small_book_from_conftest(small_valuation):
    # AAA 48%, BBB a USD government bond 32%, CCC a fund 16%, cash 4%.
    assert readings(IssuerMaxShare(Decimal("0.5")), small_valuation) == [("AAA", Decimal("0.48"))]
    assert readings(GovtMinShare(Decimal("0.3")), small_valuation) == [("government bonds", Decimal("0.32"))]
    assert readings(FundMaxShare(Decimal("0.2")), small_valuation) == [("CCC", Decimal("0.16"))]
    assert readings(MinCashShare(Decimal("0.05")), small_valuation) == [("cash", Decimal("0.04"))]
    assert readings(MaxPositions(Decimal(3)), small_valuation) == [("positions", Decimal(3))]


def test_restricted_holdings(book):
    restricted = parse_restricted(io.StringIO(
        HEADER + ",ACME,Governance review,2026-10-01,\nFUNDY,,Fee dispute,2026-11-02,\nBOLT,,Old case,2026-01-05,2026-06-30\n"))
    assert [format_violation(reading) for reading in RestrictedHoldings(restricted).check(book)] == [
        "VIOLATION restricted_holdings ACME: 20.0% held, issuer ACME restricted since 2026-10-01 (Governance review)",
        "VIOLATION restricted_holdings ACME31: 10.0% held, issuer ACME restricted since 2026-10-01 (Governance review)",
    ]
    assert [held.position.instrument.id for held in restricted_holdings(book, restricted)] == ["ACME", "ACME31"]
    assert [held.position.instrument.id for held in upcoming_restrictions(book, restricted)] == ["FUNDY"]
    assert RestrictedHoldings(parse_restricted(io.StringIO(HEADER))).measure(book) == []


def test_readings_compare_exact_values():
    at_limit = Reading("issuer_max_share", "ZED", Decimal("0.07"), Decimal("0.07"), MAX_SHARE)
    assert at_limit.headroom == 0 and not at_limit.is_violation
    just_over = Reading("issuer_max_share", "ZED", Decimal("0.07001"), Decimal("0.07"), MAX_SHARE)
    assert format_violation(just_over) == "VIOLATION issuer_max_share ZED: 7.0% > 7.0%"
    under = Reading("min_cash_share", "cash", Decimal("0.0199"), Decimal("0.02"), MIN_SHARE)
    assert under.is_violation and under.headroom == Decimal("-0.0001")
    with pytest.raises(ValueError, match="unknown kind"):
        Reading("issuer_max_share", "ZED", Decimal(0), Decimal(0), "at_most")


def test_headroom_in_base_currency(book):
    result = run_guidelines(book, [IssuerMaxShare(Decimal("0.35")), MaxPositions(Decimal(8)),
                                   FundMaxShare(Decimal("0.1"))])
    issuer, positions, funds = result.headroom
    assert issuer.tightest.subject == "ACME" and issuer.amount == Money(Decimal(500), "GBP")
    assert positions.tightest.headroom == 2 and positions.amount is None
    assert funds.amount == Money(Decimal(-800), "GBP")  # sell 800 of FUNDX to come back to 10%
    assert not result.ok and result.violated() == ("fund_max_share",)


def test_nothing_to_measure_is_not_a_violation():
    result = run_guidelines(value_book((equity("ONLY"), 10, 10)), [FundMaxShare(Decimal("0.1"))])
    [entry] = result.headroom
    assert result.ok and result.checked == ("fund_max_share",)
    assert (entry.tightest, entry.amount, entry.remark) == (None, None, "no funds held")


def test_registry_builds_what_the_mandate_has_in_force():
    assert list(KINDS) == [cls.key for cls in GUIDELINES]
    mandate = parse_mandate({"mandate": {"portfolio": "TEST"}, "guidelines": {
        "max_positions": {"value": 30}, "fund_max_share": {"value": 0.1, "enabled": False},
        "issuer_max_share": {"value": 0.05}}}, KINDS)
    guidelines = build_guidelines(mandate)
    assert [guideline.key for guideline in guidelines] == ["issuer_max_share", "max_positions"]
    assert [guideline.limit for guideline in guidelines] == [Decimal("0.05"), Decimal(30)]
    assert not needs_restricted_list(mandate)


def test_restricted_guideline_needs_the_list():
    mandate = parse_mandate({"mandate": {"portfolio": "TEST"}, "guidelines": {"restricted_holdings": {}}}, KINDS)
    assert needs_restricted_list(mandate)
    with pytest.raises(ValueError, match="no restricted list"):
        build_guidelines(mandate)
    [guideline] = build_guidelines(mandate, parse_restricted(io.StringIO(HEADER)))
    assert isinstance(guideline, RestrictedHoldings) and guideline.limit == 0


def test_sample_book_breaks_only_the_restricted_list(valuation):
    mandate = read_mandate(DATA_DIR / "guidelines.toml")
    result = run_guidelines(valuation, build_guidelines(mandate, load_restricted(DATA_DIR / "restricted.csv")))
    assert result.checked == tuple(term.key for term in mandate.terms)
    assert result.violated() == ("restricted_holdings",)
    assert [format_violation(reading) for reading in result.violations] == [
        "VIOLATION restricted_holdings TNSL: 0.9% held, restricted since 2026-10-01 (Thermal coal over 10% of revenue)"]
    tightest = {entry.guideline: entry.tightest.subject for entry in result.headroom}
    assert (tightest["issuer_max_share"], tightest["country_max_share"], tightest["fund_max_share"]) == (
        "ADZM", "US", "GEIF")
    adzm = valuation.position("ADZM").weight + valuation.position("ADZM32").weight  # shares and bonds together
    assert abs(result.headroom[0].tightest.actual - adzm) < Decimal("1e-20")
