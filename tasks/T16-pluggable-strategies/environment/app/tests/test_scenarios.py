"""End-to-end scenarios through the command line, on small hand-made price files.

Each scenario checks what the desk would check by eye: the right names held, the right trades on the right days,
the costs and fees where they belong. The golden files (tests/test_cli.py) check the digits.
"""
import csv
import io
import json
from datetime import date

import pytest

from conftest import run_cli, trending, weekdays, write_prices, zigzag

DAYS = weekdays(date(2025, 3, 3), 120)


@pytest.fixture
def market(tmp_path):
    """Six names: three steady risers of different speeds, a faller, a swinger and one listed late."""
    columns = {
        "FAST": trending(30.0, 0.006, 120),
        "MIDL": trending(60.0, 0.003, 120),
        "SLOW": trending(90.0, 0.001, 120),
        "FALL": trending(70.0, -0.004, 120),
        "SWAY": zigzag(50.0, 0.03, 120),
        "LATE": [None] * 50 + trending(25.0, 0.008, 70),
    }
    return write_prices(tmp_path / "market.csv", DAYS, columns)


def run(tmp_path, prices, config, *options):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    proc = run_cli("--prices", str(prices), "--config", str(path), *options)
    assert proc.returncode == 0, proc.stderr
    return proc


def report(tmp_path, prices, config, *options):
    return json.loads(run(tmp_path, prices, config, *options).stdout)


def trade_log(tmp_path, prices, config, *options):
    path = tmp_path / "trades.csv"
    run(tmp_path, prices, config, "--trades", str(path), *options)
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def test_momentum_holds_the_fastest_risers(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20, "skip": 2}, "top_n": 2})
    assert set(result["final_positions"]) == {"FAST", "LATE"}


def test_shorts_go_to_the_faller(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20, "skip": 2}, "top_n": 1,
                                       "allow_short": True})
    weights = {s: p["weight"] for s, p in result["final_positions"].items()}
    assert weights["FALL"] < 0.0
    assert result["metrics"]["borrow_fees"] > 0.0


def test_the_first_trades_come_on_the_end_of_the_warm_up(tmp_path, market):
    trades = trade_log(tmp_path, market, {"signal": {"type": "momentum", "lookback": 30, "skip": 2}})
    assert {t["date"] for t in trades[:3]} == {DAYS[30]}
    assert all(t["reason"] == "rebalance" for t in trades)


def test_a_longer_vol_window_delays_the_first_trades(tmp_path, market):
    trades = trade_log(tmp_path, market, {"signal": {"type": "momentum", "lookback": 10}, "vol_window": 40})
    assert trades[0]["date"] == DAYS[40]


def test_the_late_listing_is_not_traded_before_it_has_a_score(tmp_path, market):
    trades = trade_log(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20, "skip": 2},
                                          "rebalance": "daily"})
    first_late = min(t["date"] for t in trades if t["symbol"] == "LATE")
    assert first_late >= DAYS[70]


def test_reversion_trades_the_swinger(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "reversion", "window": 6, "entry_z": 0.5},
                                       "rebalance": "daily", "allow_short": True})
    assert result["pnl_by_symbol"]["SWAY"] != 0.0
    assert result["metrics"]["trades"] > 50


def test_steady_trends_give_reversion_little_to_do(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "reversion", "window": 10, "entry_z": 3.0}})
    assert result["metrics"]["trades"] <= 10


def test_a_minimum_commission_raises_the_costs(tmp_path, market):
    config = {"signal": {"type": "momentum", "lookback": 20}, "rebalance": "weekly"}
    plain = report(tmp_path, market, config)["metrics"]
    floored = report(tmp_path, market, dict(config, min_commission=500.0))["metrics"]
    assert floored["commissions"] > plain["commissions"]
    assert floored["commissions"] >= 500.0 * floored["trades"]


def test_the_band_cuts_small_trades(tmp_path, market):
    config = {"signal": {"type": "momentum", "lookback": 20}, "rebalance": "daily"}
    every = report(tmp_path, market, config)["metrics"]["trades"]
    banded = report(tmp_path, market, dict(config, rebalance_band=0.02))["metrics"]["trades"]
    assert banded < every


def test_a_gap_forces_an_exit(tmp_path):
    columns = {"HELD": trending(40.0, 0.006, 120), "OTHR": trending(40.0, 0.001, 120)}
    columns["HELD"][80:90] = [None] * 10
    prices = write_prices(tmp_path / "gap.csv", DAYS, columns)
    config = {"signal": {"type": "momentum", "lookback": 20}, "top_n": 1}
    trades = trade_log(tmp_path, prices, config)
    forced = [t for t in trades if t["reason"] == "forced exit"]
    assert [(t["symbol"], t["date"], t["side"]) for t in forced] == [("HELD", DAYS[85], "sell")]
    proc = run(tmp_path, prices, config)
    assert proc.stderr == f"warning: HELD has no price from {DAYS[80]} to {DAYS[89]} (10 days, more than " \
                          "max_fill_gap)\n"


def test_a_longer_fill_gap_avoids_the_forced_exit(tmp_path):
    columns = {"HELD": trending(40.0, 0.006, 120), "OTHR": trending(40.0, 0.001, 120)}
    columns["HELD"][80:84] = [None] * 4
    prices = write_prices(tmp_path / "gap.csv", DAYS, columns)
    config = {"signal": {"type": "momentum", "lookback": 20}, "top_n": 1}
    assert report(tmp_path, prices, config)["metrics"]["forced_exits"] == 0
    assert report(tmp_path, prices, dict(config, max_fill_gap=2))["metrics"]["forced_exits"] == 1


def test_the_benchmark_is_never_traded(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20}, "benchmark": "SLOW"})
    assert "SLOW" not in result["pnl_by_symbol"]
    assert result["benchmark"]["symbol"] == "SLOW"
    assert result["benchmark"]["total_return"] == pytest.approx(1.001 ** 119 - 1.0, rel=1e-3)


def test_excluded_names_still_count_for_the_benchmark_but_are_not_held(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20}, "exclude": ["FAST"]})
    assert "FAST" not in result["final_positions"]
    assert result["pnl_by_symbol"]["FAST"] == 0.0


def test_interest_on_an_idle_book(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "momentum", "lookback": 500, "skip": 5},
                                       "cash_rate": 0.05})
    assert result["metrics"]["trades"] == 0
    assert result["capital"]["final"] == pytest.approx(1000000.0 * (1 + 0.05 / 252) ** 119)
    assert result["metrics"]["interest"] == pytest.approx(result["capital"]["final"] - 1000000.0)


def test_the_window_options_cut_the_report(tmp_path, market):
    result = report(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20}},
                    "--start", DAYS[10], "--end", DAYS[99])
    assert result["period"] == {"start": DAYS[10], "end": DAYS[99], "days": 90}


def test_the_equity_curve_has_a_row_per_day(tmp_path, market):
    equity = tmp_path / "equity.csv"
    run(tmp_path, market, {"signal": {"type": "momentum", "lookback": 20}}, "--equity", str(equity))
    rows = list(csv.DictReader(io.StringIO(equity.read_text(encoding="utf-8"))))
    assert [row["date"] for row in rows] == DAYS
    assert float(rows[0]["nav"]) == 1000000.0


def test_the_text_summary_matches_the_report(tmp_path, market):
    config = {"signal": {"type": "momentum", "lookback": 20}}
    full = report(tmp_path, market, config)
    text = run(tmp_path, market, config, "--format", "text").stdout
    assert f"{full['metrics']['total_return'] * 100:.2f}%" in text
    assert f"{full['capital']['final']:,.2f}" in text


def test_the_html_page_matches_the_report(tmp_path, market):
    config = {"signal": {"type": "momentum", "lookback": 20}}
    full = report(tmp_path, market, config)
    page = run(tmp_path, market, config, "--format", "html").stdout
    assert f"<td>{full['capital']['final']:,.2f}</td>" in page


def test_trades_add_up_to_the_statistics(tmp_path, market):
    config = {"signal": {"type": "reversion", "window": 8}, "rebalance": "weekly", "allow_short": True}
    full = report(tmp_path, market, config)
    trades = trade_log(tmp_path, market, config)
    assert len(trades) == full["metrics"]["trades"]
    assert sum(float(t["commission"]) for t in trades) == pytest.approx(full["metrics"]["commissions"])
