from datetime import date
from decimal import Decimal

import pytest

from folio.calc import bonds
from folio.domain.instruments import Bond

AS_OF = date(2026, 10, 30)


def gilt(coupon="0.04", maturity=date(2031, 10, 30)):
    return Bond("G", "Gilt", "Government", "GBP", coupon_rate=Decimal(coupon), maturity=maturity)


def test_schedule_rolls_back_from_maturity():
    assert bonds.add_months(date(2026, 8, 31), -6) == date(2026, 2, 28)  # clamped to month end
    assert bonds.coupon_dates(date(2028, 3, 7), AS_OF, 2) == [
        date(2027, 3, 7), date(2027, 9, 7), date(2028, 3, 7)]
    bund = Bond("B", "Bund", "Government", "EUR", coupon_rate=Decimal("0.02"), maturity=date(2028, 8, 15))
    flows = bonds.cash_flows(bund, AS_OF)
    assert [amount for _, amount in flows] == [2.0, 102.0]  # annual coupons for EUR


def test_par_bond_yields_its_coupon():
    flows = bonds.cash_flows(gilt(), AS_OF)
    assert bonds.yield_to_maturity(flows, 100.0, 2) == pytest.approx(0.04, abs=1e-4)
    assert bonds.yield_to_maturity(flows, 95.0, 2) > 0.04
    with pytest.raises(ValueError, match="outside"):
        bonds.yield_to_maturity(flows, 500.0, 2)


def test_duration_is_below_maturity_and_grows_with_it():
    short = bonds.modified_duration(bonds.cash_flows(gilt(maturity=date(2028, 10, 30)), AS_OF), 0.04, 2)
    long = bonds.modified_duration(bonds.cash_flows(gilt(), AS_OF), 0.04, 2)
    assert 1.5 < short < 2.0 < long < 5.0


def test_duration_summary(valuation, small_valuation):
    on_bonds, on_nav, share = bonds.duration_summary(valuation)
    assert len(bonds.bond_risks(valuation)) == 8
    assert on_nav == pytest.approx(on_bonds * share)
    assert 3 < on_bonds < 8
    assert bonds.duration_summary(small_valuation)[2] == pytest.approx(0.32)
