"""The command line, end to end, against the golden files in tests/golden.

The golden files are the program's own output on the sample (tests/data), kept byte for byte: any change to
what the program prints shows up here first.
"""
import json

from conftest import DATA, GOLDEN, run_cli

PRICES = str(DATA / "prices.csv")


def golden(name):
    return (GOLDEN / name).read_text(encoding="utf-8")


def test_momentum_report_matches_golden(tmp_path):
    equity = tmp_path / "equity.csv"
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"), "--equity", str(equity))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == golden("momentum_report.json")
    assert equity.read_text(encoding="utf-8") == golden("momentum_equity.csv")


def test_momentum_trade_log_matches_golden(tmp_path):
    trades = tmp_path / "trades.csv"
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"), "--trades", str(trades))
    assert proc.returncode == 0, proc.stderr
    assert trades.read_text(encoding="utf-8") == golden("momentum_trades.csv")


def test_reversion_report_matches_golden(tmp_path):
    equity = tmp_path / "equity.csv"
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "reversion.json"), "--equity", str(equity))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == golden("reversion_report.json")
    assert equity.read_text(encoding="utf-8") == golden("reversion_equity.csv")


def test_momentum_summary_matches_golden():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"), "--format", "text")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == golden("momentum_summary.txt")


def test_reversion_summary_matches_golden():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "reversion.json"), "--format", "text")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == golden("reversion_summary.txt")


def test_gap_warnings_go_to_stderr():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"))
    assert proc.returncode == 0
    assert proc.stderr == golden("sample_warnings.txt")


def test_window_options_set_the_period():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"),
                   "--start", "2024-03-01", "--end", "2024-12-31")
    assert proc.returncode == 0, proc.stderr
    period = json.loads(proc.stdout)["period"]
    assert period["start"] == "2024-03-01"
    assert period["end"] == "2024-12-31"


def test_window_too_short_is_an_error():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"),
                   "--start", "2024-03-02", "--end", "2024-03-04")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr == "error: fewer than two days between 2024-03-02 and 2024-03-04\n"


def test_bad_config_is_reported():
    proc = run_cli("--prices", PRICES, "--config", "tests/data/bad_config.json")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr == "error: tests/data/bad_config.json: unknown setting 'lookback'\n"


def test_missing_price_file_is_reported():
    proc = run_cli("--prices", "tests/data/no_such_file.csv", "--config", str(DATA / "momentum.json"))
    assert proc.returncode == 2
    assert proc.stderr == "error: cannot open tests/data/no_such_file.csv: No such file or directory\n"


def test_no_equity_file_after_an_error(tmp_path):
    equity = tmp_path / "equity.csv"
    proc = run_cli("--prices", PRICES, "--config", "tests/data/bad_config.json", "--equity", str(equity))
    assert proc.returncode == 2
    assert not equity.exists()


def test_report_is_json_with_a_fixed_key_order():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"))
    report = json.loads(proc.stdout)
    assert list(report) == ["period", "capital", "strategy", "costs", "metrics", "benchmark", "drawdowns",
                            "positions", "monthly_returns", "yearly_returns", "pnl_by_symbol", "final_positions"]
    assert report["benchmark"]["symbol"] == "IDX"
    assert "IDX" not in report["pnl_by_symbol"]


def test_a_benchmark_that_is_not_a_column_is_an_error(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"benchmark": "SPX"}', encoding="utf-8")
    proc = run_cli("--prices", "tests/data/prices.csv", "--config", str(config))
    assert proc.returncode == 2
    assert proc.stderr == "error: benchmark 'SPX' is not a column of tests/data/prices.csv\n"


def test_help_names_every_option():
    proc = run_cli("--help")
    assert proc.returncode == 0
    for option in ("--prices", "--config", "--equity", "--start", "--end", "--format"):
        assert option in proc.stdout


def test_unknown_format_is_refused():
    proc = run_cli("--prices", PRICES, "--config", str(DATA / "momentum.json"), "--format", "xml")
    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr
