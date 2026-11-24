import pytest

from alertd import format as fmt
from alertd.timeutil import parse_time


@pytest.mark.parametrize("value, places, text", [
    (2.675, 2, "2.68"),
    (-2.675, 2, "-2.68"),
    (12.25, 1, "12.3"),
    (12.35, 1, "12.4"),
    (0.5, 0, "1"),
    (1212, 0, "1,212"),
    (-1234567.891, 2, "-1,234,567.89"),
    (3.0, 2, "3.00"),
])
def test_number_rounds_half_away_from_zero_with_thousands(value, places, text):
    assert fmt.number(value, places) == text


def test_number_never_writes_minus_zero():
    assert fmt.number(-0.001, 2) == "0.00"
    assert fmt.number(-0.4, 0) == "0"


def test_a_float_difference_is_written_as_its_decimal():
    assert fmt.number(3.4 - 3.1, 2) == "0.30"
    assert fmt.number(0.46 - 0.22, 2) == "0.24"


@pytest.mark.parametrize("value, unit, text", [
    (3.4, "pct", "3.40%"),
    (21.4, "bp", "21bp"),
    (1212, "k", "1,212k"),
    (12.25, "m", "12.3m"),
    (-14.6, "bn", "-14.6bn"),
    (23.4, "min", "23 min"),
])
def test_amount_writes_each_unit(value, unit, text):
    assert fmt.amount(value, unit) == text


def test_signed_shows_the_sign():
    assert fmt.signed(0.24, "pct") == "+0.24%"
    assert fmt.signed(-93, "k") == "-93k"
    assert fmt.signed(-0.001, "pct") == "0.00%"
    assert fmt.signed(1500, "k") == "+1,500k"


def test_change_says_up_or_down():
    assert fmt.change(-3.122, "pct") == "down 3.12%"
    assert fmt.change(21.0, "bp") == "up 21bp"
    assert fmt.change(0.2, "bp") == "unchanged"


def test_share():
    assert fmt.share(2.5, 2.4) == "104.2%"
    assert fmt.share(10.6, 12.0) == "88.3%"


def test_clock():
    assert fmt.clock(parse_time("2026-11-03T09:12:45Z")) == "09:12 UTC"


def test_level_tag():
    assert fmt.level_tag("warning") == "WARNING"
    with pytest.raises(ValueError):
        fmt.level_tag("severe")


def test_shorten():
    assert fmt.shorten("short  headline") == "short headline"
    long = "word " * 30
    cut = fmt.shorten(long, 20)
    assert len(cut) <= 20 and cut.endswith("...")


def test_message_in_the_house_style():
    assert fmt.message("warning", "ORVK", "price down 3.12%", "last 41.27, from 42.60") == \
        "WARNING ORVK: price down 3.12% (last 41.27, from 42.60)"
    assert fmt.message("info", "prices-eu", "back") == "INFO prices-eu: back"
