import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from folio.calc import exposure
from folio.calc.returns import nav_series
from folio.calc.risk import summarise_risk
from folio.calc.valuation import value_portfolio
from folio.report import text_report
from folio.report.tables import (
    Column,
    bucket,
    clip,
    format_money,
    format_pct,
    format_quantity,
    render_table,
)


def test_render_table_aligns_and_strips():
    text = render_table([Column("Name"), Column("Value", "right")], [["a", "1.0"], ["long name", "22.50"]],
                        total=["Total", "23.50"])
    assert text.splitlines() == [
        "Name       Value",
        "---------  -----",
        "a            1.0",
        "long name  22.50",
        "---------  -----",
        "Total      23.50",
    ]


def test_number_formats():
    assert format_money(Decimal("1234567.891")) == "1,234,567.89"
    assert format_money(Decimal("-0.001")) == "0.00"
    assert format_money(Decimal("1234.5"), places=0) == "1,234"
    assert format_pct(Decimal("0.2414")) == "24.1%"
    assert format_pct(0.0125, places=2, signed=True) == "+1.25%"
    assert format_pct(Decimal("-0.0004"), signed=True) == "0.0%"
    assert format_quantity(Decimal("1500")) == "1,500"
    assert format_quantity(Decimal("12.50")) == "12.5"
    assert clip("Harrow Global Equity Index Fund", 20) == "Harrow Global Equ..."


def test_bucket_counts_half_open_bins():
    assert bucket([0.5, 1.5, 7, 1.0, -3], [0, 1, 5]) == [
        ("< 0", 1), ("[0, 1)", 1), ("[1, 5)", 2), (">= 5", 1)]
    assert bucket([], [10], label=lambda edge: f"{edge}d") == [("< 10d", 0), (">= 10d", 0)]
    with pytest.raises(ValueError, match="strictly increasing"):
        bucket([1], [0, 0])


def test_breakdown_report_format(small_valuation, settings):
    text = text_report.render_breakdown(small_valuation, exposure.by_sector(small_valuation), settings.report)
    assert text == (
        "Test book (TEST)\n"
        "Valued 2026-10-30 in GBP\n"
        "\n"
        "Exposure by sector\n"
        "Sector       Positions  Market value  Weight\n"
        "-----------  ---------  ------------  ------\n"
        "Technology           1     12,000.00   48.0%\n"
        "Government           1      8,000.00   32.0%\n"
        "Diversified          1      4,000.00   16.0%\n"
        "Cash                        1,000.00    4.0%\n"
        "-----------  ---------  ------------  ------\n"
        "Total                3     25,000.00  100.0%\n"
    )


def test_breakdown_report_without_cash_row(small_valuation, settings):
    report_settings = dataclasses.replace(settings.report, show_cash=False)
    text = text_report.render_breakdown(small_valuation, exposure.by_kind(small_valuation), report_settings)
    assert "Cash" not in text
    assert text.splitlines()[-1].split() == ["Total", "3", "24,000.00", "96.0%"]


def test_valuation_report(small_book, settings):
    universe, book, prices, fx = small_book
    valuation = value_portfolio(book, universe, prices, fx, date(2026, 11, 5), base_currency="GBP",
                                stale_after_days=3)
    text = text_report.render_valuation(valuation, settings.report)
    row = next(line for line in text.splitlines() if line.startswith("AAA"))
    assert row.split() == ["AAA", "Alpha", "plc", "equity", "GBP", "1,000", "12*", "12,000.00", "48.0%", "+20.0%"]
    assert "Total" in text and "25,000.00" in text
    assert "* price older than 3 business days: AAA (2026-10-30), BBB (2026-10-30), CCC (2026-10-30)" in text
    assert "Fund running costs (est.): GBP 40.00 a year (0.16% of NAV)" in text


def test_risk_report(valuation, prices, fx, settings):
    risk = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    text = text_report.render_risk(valuation, risk, settings, histogram=True)
    assert "VaR 99% 1d" in text and "ES 99% 1d" in text
    assert f"{risk.observations} daily returns" in text
    histogram = text.split("Daily returns (60)\n")[1].splitlines()
    assert histogram[0].startswith("< -") and histogram[-1].startswith(">= ")
    assert sum(int(line.split()[-2] if line.endswith("#") else line.split()[-1]) for line in histogram) == 60
    assert max(histogram, key=len).count("#") == 40  # the fullest bin sets the scale
