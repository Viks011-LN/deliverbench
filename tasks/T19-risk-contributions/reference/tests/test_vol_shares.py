"""Shares of volatility: the daily P&L table, the Euler split, the report, the exports and the name_vol_share limit."""

import csv
import dataclasses
import io
import json
import math
import statistics
from decimal import Decimal
from pathlib import Path

import pytest

from folio.calc import exposure
from folio.calc.returns import daily_pnl_shares, nav_series, simple_returns
from folio.calc.risk import summarise_risk, vol_shares
from folio.cli import main
from folio.config.loader import load_settings
from folio.errors import ConfigError, RiskError
from folio.limits.checker import build_rules, needs_risk, needs_vol_shares, run_checks
from folio.limits.rules import NameVolShare
from folio.report.csv_export import write_csv
from folio.report.json_export import valuation_document

DATA = str(Path(__file__).resolve().parent.parent / "data")


def run(*argv, as_of="2026-10-30"):
    out, err = io.StringIO(), io.StringIO()
    code = main([*argv, "--data-dir", DATA, "--as-of", as_of], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_daily_shares_add_up_to_the_same_days_return(valuation, prices, fx, settings):
    table = daily_pnl_shares(valuation, prices, fx, settings.risk.var_lookback_days)
    returns = simple_returns(nav_series(valuation, prices, fx))[-settings.risk.var_lookback_days:]
    assert [row.day for row in table] == [day for day, _ in returns]
    for row, (_, value) in zip(table, returns):
        assert math.fsum(row.shares) == pytest.approx(value, abs=1e-12)
        assert row.portfolio_return == pytest.approx(value, abs=1e-15)
    assert len(table[0].shares) == len(valuation.positions) + len(valuation.cash)


def test_short_history_starts_at_the_first_return(valuation, prices, fx):
    table = daily_pnl_shares(valuation, prices, fx, 500)
    returns = simple_returns(nav_series(valuation, prices, fx))
    assert len(table) == len(returns) and table[0].day == returns[0][0]
    assert math.fsum(table[0].shares) == pytest.approx(returns[0][1], abs=1e-12)


def test_shares_add_up_to_one_on_the_risk_window(valuation, prices, fx, settings):
    shares = vol_shares(valuation, prices, fx, settings.risk)
    risk = summarise_risk(nav_series(valuation, prices, fx), valuation.nav, settings.risk)
    assert math.fsum(shares.positions) + shares.cash_total == pytest.approx(1.0, abs=1e-12)
    assert (shares.end, shares.observations) == (risk.end, risk.observations)
    assert shares.start > risk.start  # risk.start is the NAV before the first return
    gbp = next(i for i, cash in enumerate(valuation.cash) if cash.local_value.currency == "GBP")
    assert shares.cash[gbp] == 0.0  # a balance in the base currency never moves
    by_sector = shares.by_group(valuation, exposure.SECTOR.key)
    assert by_sector[0].key == "Technology"
    assert math.fsum(float(group.total) for group in by_sector) == pytest.approx(math.fsum(shares.positions))


def test_euler_split_matches_a_direct_calculation(valuation, prices, fx, settings):
    table = daily_pnl_shares(valuation, prices, fx, settings.risk.var_lookback_days)
    returns = [math.fsum(row.shares) for row in table]
    first = [row.shares[0] for row in table]
    expected = statistics.covariance(first, returns) / statistics.variance(returns)
    assert vol_shares(valuation, prices, fx, settings.risk).positions[0] == pytest.approx(expected, rel=1e-9)


def test_too_little_history_is_refused(valuation, prices, fx, settings):
    strict = dataclasses.replace(settings.risk, min_observations=60, var_lookback_days=500)
    shares = vol_shares(valuation, prices, fx, strict)
    assert shares.observations > 60
    with pytest.raises(RiskError, match="risk.min_observations is 100"):
        vol_shares(valuation, prices, fx, dataclasses.replace(strict, min_observations=100))


def test_name_vol_share_groups_by_issuer(valuation, prices, fx, settings):
    shares = vol_shares(valuation, prices, fx, settings.risk)
    measured = dict(NameVolShare(Decimal("0.2")).measure(valuation, shares=shares))
    index = {line.instrument.id: i for i, line in enumerate(valuation.positions)}
    assert float(measured["ADZM"]) == pytest.approx(shares.positions[index["ADZM"]] + shares.positions[index["ADZM32"]])
    assert "ADZM32" not in measured and "Cash" not in measured
    breaches = NameVolShare(Decimal("0.06")).check(valuation, shares=shares)
    assert [b.format() for b in breaches] == ["BREACH name_vol_share ADZM: 8.7% > 6.0%",
                                              "BREACH name_vol_share GEIF: 7.7% > 6.0%",
                                              "BREACH name_vol_share QNTL: 6.8% > 6.0%"]
    assert NameVolShare(Decimal("0.2")).check(valuation) == []  # no shares, nothing measured


def test_setting_default_override_and_disable(tmp_path, settings):
    assert load_settings(cwd=tmp_path).limits.name_vol_max_share == Decimal("0.20")
    assert load_settings(overrides=["limits.name_vol_max_share=0.1"], cwd=tmp_path).limits.name_vol_max_share \
        == Decimal("0.1")
    with pytest.raises(ConfigError, match="limits.name_vol_max_share must be a fraction"):
        load_settings(overrides=["limits.name_vol_max_share=0"], cwd=tmp_path)
    rules = build_rules(dataclasses.replace(settings.limits, disabled=("var_share",)))
    assert needs_vol_shares(rules) and not needs_risk(rules)
    rules = build_rules(dataclasses.replace(settings.limits, disabled=("name_vol_share",)))
    assert not needs_vol_shares(rules)


def test_check_limits_with_the_new_rule():
    code, out, _ = run("check-limits", "-v")
    assert code == 0
    assert "ok name_vol_share ADZM: 8.7% <= 20.0%" in out.splitlines()
    assert out.endswith("OK: 5 rules checked, no breaches\n")
    code, out, _ = run("check-limits", "--set", "limits.name_vol_max_share=0.08")
    assert code == 1 and out == "BREACH name_vol_share ADZM: 8.7% > 8.0%\n"


def test_report_by_risk_lists_every_holding_and_sector(valuation):
    code, out, _ = run("report", "--by", "risk")
    assert code == 0
    lines = out.splitlines()
    assert lines[3].startswith("Share of volatility by holding (60 daily returns")
    assert {line.split()[0] for line in lines if line.strip()} >= {line.instrument.id for line in valuation.positions}
    assert "Share of volatility by sector" in lines
    assert lines[-1].split() == ["Total", "38", "100.0%", "100.0%"]


def test_exports_put_vol_share_before_weight(small_valuation):
    _, out, _ = run("export", "--format", "csv")
    rows = list(csv.DictReader(io.StringIO(out)))
    header = list(rows[0])
    assert header[-2:] == ["vol_share", "weight"]
    assert math.fsum(float(row["vol_share"]) for row in rows) == pytest.approx(1.0, abs=0.01)
    _, out, _ = run("export", "--format", "json")
    positions = json.loads(out)["positions"]
    assert list(positions[0])[-2:] == ["vol_share", "weight"]
    assert {p["instrument"]: p["vol_share"] for p in positions}["ADZM"] == 0.082434
    buffer = io.StringIO()
    write_csv(small_valuation, buffer)  # without shares the column stays, blank
    assert {row["vol_share"] for row in csv.DictReader(io.StringIO(buffer.getvalue()))} == {""}
    assert valuation_document(small_valuation)["positions"][0]["vol_share"] is None


def test_export_without_enough_history_leaves_the_shares_blank():
    code, out, err = run("export", "--set", "risk.min_observations=60", as_of="2026-08-31")
    assert code == 0
    assert all(row["vol_share"] == "" for row in csv.DictReader(io.StringIO(out)))
    assert "folio: note: vol_share left blank: only " in err
