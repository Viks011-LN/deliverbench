from decimal import Decimal

import pytest

from folio.domain.money import CurrencyMismatch, Money, check_currency, sum_money, to_decimal


def test_arithmetic_in_one_currency():
    assert Money("10.50", "GBP") + Money("0.25", "GBP") == Money("10.75", "GBP")
    assert sum([Money("1.10", "EUR"), Money("2.20", "EUR")]) == Money("3.30", "EUR")
    assert sum_money([], "JPY") == Money.zero("JPY")
    assert 3 * Money("2", "USD") == Money("6", "USD")
    assert Money("3", "USD") / Money("4", "USD") == Decimal("0.75")
    assert Money("3", "USD") / 2 == Money("1.5", "USD")


def test_mixing_currencies_raises():
    with pytest.raises(CurrencyMismatch, match="cannot add GBP and USD"):
        Money("1", "GBP") + Money("1", "USD")
    with pytest.raises(CurrencyMismatch):
        Money("1", "GBP") < Money("2", "EUR")
    with pytest.raises(ZeroDivisionError):
        Money("3", "USD") / Money("0", "USD")


def test_rounding_is_half_even_and_uses_minor_units():
    assert Money("2.345", "GBP").rounded() == Money("2.34", "GBP")
    assert Money("2.355", "GBP").rounded() == Money("2.36", "GBP")
    assert Money("1234.5", "JPY").rounded() == Money("1234", "JPY")
    assert str(Money("1234.5", "GBP")) == "GBP 1,234.50"
    assert str(Money("98765.5", "JPY")) == "JPY 98,766"


def test_to_decimal():
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(" 12.5 ") == Decimal("12.5")
    with pytest.raises(TypeError):
        to_decimal(True)
    with pytest.raises(ValueError, match="not a number"):
        to_decimal("12,5")
    with pytest.raises(ValueError, match="finite"):
        to_decimal("NaN")


@pytest.mark.parametrize("code", ["gbp", "GB", "G1P", 840])
def test_invalid_currency_codes(code):
    with pytest.raises(ValueError, match="invalid currency code"):
        check_currency(code)
