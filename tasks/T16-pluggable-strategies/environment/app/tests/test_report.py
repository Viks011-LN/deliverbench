"""The outputs: the JSON report, the equity curve, the trade log and the text summary."""
from bt.config import DEFAULTS
from bt.report import build_report, render_summary, write_equity_curve, write_trade_log
from bt.report.calendar_grid import monthly_grid
from bt.report.equity import equity_line
from bt.report.formatting import money, percent, ratio, row
from bt.report.json_report import final_positions, signal_echo
from bt.report.summary import benchmark_rows, book_line, drawdown_lines, risk_line, strategy_line
from bt.report.trades import trade_line, trades_by_symbol

CURVE = [
    {"date": "2026-01-05", "nav": 1000000.0, "cash": 1000000.0, "gross": 0.0, "net": 0.0, "holdings": 0},
    {"date": "2026-01-06", "nav": 1000100.5, "cash": 500000.0, "gross": 0.5, "net": 0.5, "holdings": 1},
]
TRADE = {"date": "2026-01-05", "symbol": "A", "side": "buy", "units": 1000.0, "price": 500.0, "notional": 500000.0,
         "commission": 250.0, "slippage": 100.0, "reason": "rebalance", "after": 1000.0}
RESULT = {"curve": CURVE, "pnl": {"A": 100.5, "B": 0.0}, "units": {"A": 1000.0, "B": 0.0},
          "last_price": {"A": 500.1005, "B": 20.0}, "trades": [TRADE],
          "stats": {"trades": 1, "forced_exits": 0, "stop_losses": 0, "traded_notional": 500000.0, "commissions": 250.0,
                    "slippage": 100.0, "borrow_fees": 0.0, "interest": 0.0}}
METRICS = {"total_return": 0.0001005, "annual_return": 0.025, "annual_volatility": None, "sharpe": None,
           "sortino": None, "max_drawdown": 0.0, "calmar": None, "hit_rate": 1.0, "best_day": 0.0001005,
           "worst_day": 0.0001005, "average_gross": 0.25, "average_net": 0.25, "average_holdings": 0.5,
           "turnover": 1.0, "trades": 1, "forced_exits": 0, "stop_losses": 0, "commissions": 250.0, "slippage": 100.0,
           "borrow_fees": 0.0, "interest": 0.0}
BENCHMARK = {"symbol": "IDX", "total_return": 0.05, "excess_return": -0.0498995, "beta": 0.8, "correlation": 0.5,
             "tracking_error": 0.1, "information_ratio": -0.3, "up_capture": None, "down_capture": None, "days": 1}


def config_with(**settings):
    config = dict(DEFAULTS)
    config.update(settings)
    return config


def test_report_sections_in_order():
    report = build_report(["2026-01-05", "2026-01-06"], ["A", "B"], config_with(), RESULT, METRICS)
    assert list(report) == ["period", "capital", "strategy", "costs", "metrics", "drawdowns", "positions",
                            "monthly_returns", "yearly_returns", "pnl_by_symbol", "final_positions"]
    assert report["positions"]["opened"] == 1 and report["positions"]["still_open"] == 1
    assert report["period"] == {"start": "2026-01-05", "end": "2026-01-06", "days": 2}
    assert report["capital"] == {"initial": 1000000.0, "final": 1000100.5}


def test_the_benchmark_section_comes_after_the_metrics():
    report = build_report(["2026-01-05", "2026-01-06"], ["A", "B"], config_with(benchmark="IDX"), RESULT, METRICS,
                          BENCHMARK)
    assert list(report)[4:7] == ["metrics", "benchmark", "drawdowns"]
    assert report["benchmark"] is BENCHMARK


def test_strategy_section_in_order():
    report = build_report(["2026-01-05", "2026-01-06"], ["A", "B"], config_with(), RESULT, METRICS)
    assert list(report["strategy"]) == ["signal", "top_n", "allow_short", "max_weight", "min_price", "exclude",
                                        "rebalance", "rebalance_band", "vol_target", "vol_window", "max_leverage",
                                        "drawdown_limit", "drawdown_scale", "stop_loss", "max_turnover",
                                        "min_history", "benchmark"]
    assert list(report["costs"]) == ["commission_bps", "min_commission", "slippage_bps", "borrow_bps", "cash_rate"]


def test_signal_echo_fills_in_the_defaults():
    assert signal_echo({"type": "momentum"}) == {"type": "momentum", "lookback": 60, "skip": 5}


def test_signal_echo_keeps_the_given_parameters():
    echo = signal_echo({"type": "reversion", "entry_z": 0.5, "window": 12})
    assert echo == {"type": "reversion", "window": 12, "entry_z": 0.5}


def test_final_positions_only_holdings():
    positions = final_positions(["A", "B"], RESULT, 1000100.5)
    assert list(positions) == ["A"]
    assert positions["A"]["value"] == 1000.0 * 500.1005
    assert positions["A"]["weight"] == 1000.0 * 500.1005 / 1000100.5


def test_equity_line_writes_numbers_in_full():
    assert equity_line(CURVE[1]) == "2026-01-06,1000100.5,500000.0,0.5,0.5\n"


def test_write_equity_curve(tmp_path):
    path = tmp_path / "equity.csv"
    write_equity_curve(str(path), CURVE)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "date,nav,cash,gross,net"
    assert len(lines) == 3


def test_trade_line():
    assert trade_line(TRADE) == "2026-01-05,A,buy,1000.0,500.0,500000.0,250.0,100.0,rebalance\n"


def test_write_trade_log(tmp_path):
    path = tmp_path / "trades.csv"
    write_trade_log(str(path), [TRADE, dict(TRADE, side="sell", units=-1000.0, reason="forced exit")])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "date,symbol,side,units,price,notional,commission,slippage,reason"
    assert lines[2].endswith(",forced exit") and ",sell,-1000.0," in lines[2]


def test_trades_by_symbol():
    assert trades_by_symbol([TRADE, dict(TRADE, symbol="B"), TRADE]) == {"A": 2, "B": 1}


def test_formatting():
    assert percent(0.12345) == "12.35%"
    assert percent(None) == "n/a"
    assert ratio(1.234) == "1.23"
    assert ratio(None) == "n/a"
    assert money(1234567.891) == "1,234,567.89"
    assert row("Sharpe", "1.00") == "Sharpe" + " " * 14 + " " * 14 + "1.00"


def test_strategy_line_names_the_strategy_and_its_parameters():
    assert strategy_line({"type": "momentum"}) == "Strategy: momentum (lookback 60, skip 5)"
    assert strategy_line({"type": "reversion", "window": 15, "entry_z": 1.5}) == \
        "Strategy: reversion (window 15, entry_z 1.5)"


def test_book_line():
    assert book_line(config_with()) == "Book: top 3, long only, rebalanced monthly, max weight 40.00%"
    assert book_line(config_with(allow_short=True, rebalance_band=0.02, min_price=5.0, exclude=["X", "Y"])) == \
        "Book: top 3, long-short, rebalanced monthly, max weight 40.00%, band 2.00%, min price 5.00, excluding X Y"


def test_risk_line():
    assert risk_line(config_with()) == "Risk: volatility target none; drawdown control none"
    assert risk_line(config_with(vol_target=0.1, drawdown_limit=0.2)) == (
        "Risk: volatility target 10.00% over 20 days, leverage at most 1.50; drawdown control x0.50 beyond 20.00%")
    assert risk_line(config_with(stop_loss=0.15, max_turnover=0.5)) == (
        "Risk: volatility target none; drawdown control none; stop loss 15.00%; turnover at most 50.00%")


def test_benchmark_rows():
    assert benchmark_rows(None) == []
    rows = benchmark_rows(BENCHMARK)
    assert rows[0] == row("Benchmark IDX", "5.00%")
    assert rows[2] == row("Beta", "0.80")


def test_drawdown_lines():
    curve = [{"date": "2026-01-05", "nav": 100.0}, {"date": "2026-01-06", "nav": 90.0},
             {"date": "2026-01-07", "nav": 101.0}, {"date": "2026-01-08", "nav": 100.0}]
    assert drawdown_lines(curve) == ["Worst drawdowns",
                                     "   -10.00%  2026-01-05 to 2026-01-06, recovered 2026-01-07 (2 days)",
                                     "    -0.99%  2026-01-07 to 2026-01-08, not recovered (1 days)"]
    assert drawdown_lines(curve[:1]) == ["Worst drawdowns", "  none"]


def test_monthly_grid():
    lines = monthly_grid({"2025-12": 0.02, "2026-01": -0.015}, {"2025": 0.02, "2026": -0.015})
    assert lines[0].startswith("Year    Jan    Feb")
    assert lines[1] == "2025" + " " * 7 * 11 + "   2.0%" + "     2.0%"
    assert lines[2] == "2026" + "  -1.5%" + " " * 7 * 11 + "    -1.5%"


def test_summary_layout():
    config = config_with(signal={"type": "momentum"})
    text = render_summary(["2026-01-05", "2026-01-06"], config, RESULT, METRICS)
    lines = text.splitlines()
    assert text.endswith("\n")
    assert lines[0] == "Backtest 2026-01-05 to 2026-01-06 (2 days)"
    assert lines[1] == "Strategy: momentum (lookback 60, skip 5)"
    assert lines[4] == ""
    assert lines[13] == row("Trades", "1 (0f 0s)")
    assert lines[14] == row("Positions", "1 (n/a days)")
    assert lines[17] == row("Final NAV", "1,000,100.50")
    assert lines[19:21] == ["Worst drawdowns", "  none"]
    assert lines[22] == "Monthly returns"


def test_summary_with_a_benchmark_has_five_more_rows():
    config = config_with(signal={"type": "momentum"}, benchmark="IDX")
    plain = render_summary(["2026-01-05", "2026-01-06"], config, RESULT, METRICS).splitlines()
    with_benchmark = render_summary(["2026-01-05", "2026-01-06"], config, RESULT, METRICS, BENCHMARK).splitlines()
    assert len(with_benchmark) == len(plain) + 5
    assert with_benchmark[13] == row("Benchmark IDX", "5.00%")
