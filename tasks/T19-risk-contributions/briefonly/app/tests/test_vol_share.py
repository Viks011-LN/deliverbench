"""Shares of volatility: the calculation, report --by risk, the export column and the name_vol_share limit."""

import csv
import dataclasses
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.calc import exposure
from folio.calc.returns import daily_pnl_shares, nav_series
from folio.calc.risk import summarise_risk, vol_groups, vol_shares
from folio.calc.valuation import value_portfolio
from folio.cli import main
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory, PricePoint
from folio.domain.instruments import Equity, Universe
from folio.domain.portfolio import Portfolio
from folio.domain.positions import Lot, Position
from folio.errors import RiskError
from folio.limits.checker import build_rules, needs_vol_shares, run_checks
from folio.limits.rules import NameVolShare
from folio.report import text_report
from folio.report.csv_export import write_csv
from folio.report.json_export import valuation_document

DATA = str(Path(__file__).resolve().parent.parent / "data")
DAYS = [date(2026, 10, day) for day in (26, 27, 28, 29, 30)]


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err, today=date(2026, 11, 19))
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def hedged_book(settings):
    """AAA moves; BBB always moves half as much the other way; plus GBP cash.

    BBB's daily P&L is -0.5 x AAA's, so the book's return is 0.5 x AAA's P&L share and the
    Euler shares are AAA cov(a, a/2) / var(a/2) = 2, BBB -1 and cash 0. On 2026-10-30:
    AAA 1,100, BBB 1,950, cash 1,000; NAV 4,050.
    """
    universe = Universe([Equity("AAA", "Alpha plc", "Technology", "GBP"),
                         Equity("BBB", "Beta plc", "Energy", "GBP")])
    book = Portfolio("HDG", "Hedged book", cash={"GBP": Decimal(1000)})
    book.add_position(Position("AAA", (Lot(date(2026, 1, 5), Decimal(100), Decimal(10)),)))
    book.add_position(Position("BBB", (Lot(date(2026, 1, 5), Decimal(100), Decimal(20)),)))
    prices = PriceHistory({
        "AAA": [PricePoint(day, Decimal(p)) for day, p in zip(DAYS, ("10", "11", "10.5", "12", "11"))],
        "BBB": [PricePoint(day, Decimal(p)) for day, p in zip(DAYS, ("20", "19.5", "19.75", "19", "19.5"))],
    })
    fx = FxRates({("GBP", "USD"): [(day, Decimal("1.25")) for day in DAYS]})
    valuation = value_portfolio(book, universe, prices, fx, DAYS[-1], base_currency="GBP", stale_after_days=3)
    risk = dataclasses.replace(settings.risk, min_observations=2, var_lookback_days=10)
    return valuation, prices, fx, risk


def test_daily_pnl_shares_add_up_to_each_days_return(valuation, prices, fx, settings):
    table = daily_pnl_shares(valuation, prices, fx, settings.risk.var_lookback_days)
    summary = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    assert tuple(row.portfolio_return for row in table) == summary.returns
    for row in table:
        assert sum(row.shares) == pytest.approx(row.portfolio_return, abs=1e-15)


def test_euler_shares_on_a_hedged_book(hedged_book):
    valuation, prices, fx, risk = hedged_book
    shares = vol_shares(valuation, prices, fx, risk)
    assert [float(share) for share in shares.positions] == pytest.approx([2.0, -1.0])
    assert shares.cash == (Decimal(0),)
    assert (shares.start, shares.end, shares.observations) == (DAYS[0], DAYS[-1], 4)


def test_sample_shares_add_up_and_use_the_risk_window(valuation, prices, fx, settings):
    shares = vol_shares(valuation, prices, fx, settings.risk)
    summary = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    assert (shares.start, shares.end, shares.observations) == (summary.start, summary.end, summary.observations)
    assert float(sum(shares.positions) + shares.cash_total) == pytest.approx(1.0)
    sectors = vol_groups(valuation, shares, exposure.SECTOR.key)
    assert sectors[0].key == "Technology"
    assert float(sum(group.vol_share for group in sectors) + shares.cash_total) == pytest.approx(1.0)


def test_shares_need_enough_history(portfolio, universe, prices, fx, settings):
    early = value_portfolio(portfolio, universe, prices, fx, date(2026, 7, 15), base_currency="GBP",
                            stale_after_days=3)
    with pytest.raises(RiskError, match="only 11 daily returns available, risk.min_observations is 20"):
        vol_shares(early, prices, fx, settings.risk)


def test_report_by_risk(hedged_book, settings):
    valuation, prices, fx, risk = hedged_book
    lines = text_report.render_vol_shares(valuation, vol_shares(valuation, prices, fx, risk),
                                          settings.report).splitlines()
    assert lines[3] == "Share of volatility by holding, 2026-10-26 to 2026-10-30, 4 daily returns"
    assert lines[6].split() == ["AAA", "Alpha", "plc", "Technology", "27.2%", "200.0%"]
    assert lines[7].split() == ["BBB", "Beta", "plc", "Energy", "48.1%", "-100.0%"]
    assert lines[8].split() == ["CASH", "Cash", "GBP", "Cash", "24.7%", "0.0%"]
    assert lines[10].split() == ["Total", "100.0%", "100.0%"]
    assert lines[12] == "Share of volatility by sector"
    assert [line.split()[0] for line in lines[15:18]] == ["Technology", "Energy", "Cash"]
    assert lines[-1].split() == ["Total", "2", "100.0%", "100.0%"]


def test_export_vol_share_sits_before_weight(hedged_book):
    valuation, prices, fx, risk = hedged_book
    shares = vol_shares(valuation, prices, fx, risk)
    buffer = io.StringIO()
    write_csv(valuation, buffer, vol_shares=shares)
    rows = list(csv.DictReader(io.StringIO(buffer.getvalue())))
    assert list(rows[0])[-2:] == ["vol_share", "weight"]
    assert [row["vol_share"] for row in rows] == ["2.000000", "-1.000000"]
    doc = valuation_document(valuation, vol_shares=shares)
    assert list(doc["positions"][0])[-2:] == ["vol_share", "weight"]
    assert [entry["vol_share"] for entry in doc["positions"]] == [2.0, -1.0]
    assert all("vol_share" not in cash for cash in doc["cash"])


def test_export_without_shares_leaves_the_column_blank(small_valuation):
    buffer = io.StringIO()
    write_csv(small_valuation, buffer)
    assert {row["vol_share"] for row in csv.DictReader(io.StringIO(buffer.getvalue()))} == {""}
    assert valuation_document(small_valuation)["positions"][0]["vol_share"] is None


def test_name_vol_share_rule(valuation, prices, fx, settings):
    assert settings.limits.name_vol_max_share == Decimal("0.20")
    rules = build_rules(settings.limits)
    assert needs_vol_shares(rules)
    shares = vol_shares(valuation, prices, fx, settings.risk)
    risk = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    assert run_checks(valuation, rules, risk, shares).ok
    measured = dict(NameVolShare(Decimal("0.2")).measure(valuation, None, shares))
    # Maxtead Bank's shares and bond count together; cash is not a name.
    by_line = {line.instrument.id: share for line, share in zip(valuation.positions, shares.positions)}
    assert measured["MXTB"] == by_line["MXTB"] + by_line["MXTB29"]
    assert "MXTB29" not in measured and "Cash" not in measured
    breaches = NameVolShare(Decimal("0.06")).check(valuation, None, shares)
    assert [b.subject for b in breaches] == ["ADZM", "GEIF", "QNTL"]
    with pytest.raises(ValueError, match="shares of volatility"):
        NameVolShare(Decimal("0.2")).check(valuation)


def test_cli_report_export_and_limits():
    code, out, _ = run("report", "--by", "risk", "--data-dir", DATA, "--as-of", "2026-10-30")
    assert code == 0
    assert out.splitlines()[3] == "Share of volatility by holding, 2026-08-07 to 2026-10-30, 60 daily returns"
    assert out.splitlines()[6].startswith("ADZM ")
    _, out, _ = run("export", "--data-dir", DATA)
    assert out.splitlines()[0].endswith(",base_value,vol_share,weight")
    code, out, _ = run("check-limits", "--data-dir", DATA, "--set", "limits.name_vol_max_share=0.08")
    assert (code, out) == (1, "BREACH name_vol_share ADZM: 8.7% > 8.0%\n")
    with pytest.raises(SystemExit) as caught:
        main(["report", "--by", "risk", "--since", "2026-09-01", "--data-dir", DATA],
             out=io.StringIO(), err=io.StringIO())
    assert caught.value.code == 2
