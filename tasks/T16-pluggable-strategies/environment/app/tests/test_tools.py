"""The desk's tools: compare, prices_info, sweep and migrate (docs/tools.md)."""
import json
import subprocess
import sys

from conftest import APP, DATA
from bt.tools.compare import differences
from bt.tools.prices_info import describe
from bt.tools.sweep import parse_setting, with_value

import pytest

from bt.errors import BacktestError


def run_tool(name, *args):
    return subprocess.run([sys.executable, "-m", f"bt.tools.{name}", *args], cwd=APP, capture_output=True,
                          text=True)


# compare -----------------------------------------------------------------------------------------------------

def test_the_same_report_has_no_differences():
    report = {"a": 1, "b": {"c": [1.5, None]}}
    assert differences(report, json.loads(json.dumps(report))) == []


def test_a_changed_number_is_one_difference():
    assert differences({"m": {"x": 0.1}}, {"m": {"x": 0.30000000000000004}}) == [
        "m.x: 0.1 != 0.30000000000000004"]


def test_an_integer_and_a_float_differ():
    assert differences({"x": 1}, {"x": 1.0}) == ["x: 1 != 1.0"]


def test_a_tolerance_lets_close_numbers_pass():
    assert differences({"x": 1.0}, {"x": 1.0 + 1e-13}, tolerance=1e-12) == []


def test_key_order_counts():
    assert differences({"a": 1, "b": 2}, {"b": 2, "a": 1}) == ["(top): keys ['a', 'b'] != ['b', 'a']"]


def test_lists_are_compared_item_by_item():
    assert differences({"d": [{"x": 1}]}, {"d": [{"x": 2}]}) == ["d[0].x: 1 != 2"]
    assert differences([1, 2], [1]) == ["(top): 2 items != 1 items"]


def test_compare_exit_status(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text('{"x": 1}', encoding="utf-8")
    b.write_text('{"x": 2}', encoding="utf-8")
    same = run_tool("compare", str(a), str(a))
    assert same.returncode == 0 and same.stdout == "the reports are the same\n"
    differ = run_tool("compare", str(a), str(b))
    assert differ.returncode == 1 and differ.stdout == "x: 1 != 2\n1 difference(s)\n"
    missing = run_tool("compare", str(a), str(tmp_path / "none.json"))
    assert missing.returncode == 2 and missing.stderr.startswith("error: cannot open ")


# prices_info -------------------------------------------------------------------------------------------------

def test_describe_a_series():
    dates = [f"2026-05-{day:02d}" for day in range(4, 12)]
    facts = describe(dates, "AAA", [None, 10.0, 10.5, None, None, None, 11.0, 11.5], 2)
    assert facts["first"] == "2026-05-05" and facts["last"] == "2026-05-11"
    assert facts["prices"] == 4 and facts["missing"] == 3 and facts["longest"] == 3 and facts["beyond"] == 1
    assert facts["last_price"] == 11.5


def test_describe_a_series_with_no_price():
    facts = describe(["2026-05-04", "2026-05-05"], "BBB", [None, None], 5)
    assert facts["prices"] == 0 and facts["vol"] is None


def test_prices_info_on_the_sample():
    proc = run_tool("prices_info", str(DATA / "prices.csv"))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].endswith("9 symbols")
    assert lines[1].split()[:3] == ["symbol", "first", "last"]
    assert len(lines) == 11


# sweep -------------------------------------------------------------------------------------------------------

def test_parse_setting():
    assert parse_setting("signal.lookback=20,40") == (["signal", "lookback"], [20, 40])
    assert parse_setting('rebalance="weekly","daily"') == (["rebalance"], ["weekly", "daily"])


@pytest.mark.parametrize("text", ["top_n", "costs.commission=1", "top_n=", "top_n=fast"])
def test_parse_setting_refuses(text):
    with pytest.raises(BacktestError):
        parse_setting(text)


def test_with_value_leaves_the_original_alone():
    raw = {"signal": {"type": "reversion", "window": 10}, "top_n": 2}
    changed = with_value(raw, ["signal", "window"], 15)
    assert changed["signal"] == {"type": "reversion", "window": 15}
    assert raw["signal"]["window"] == 10
    assert with_value(raw, ["top_n"], 4)["top_n"] == 4


def test_sweep_runs_each_value():
    proc = run_tool("sweep", "--prices", str(DATA / "prices.csv"), "--config", str(DATA / "momentum.json"),
                    "--set", "top_n=2,4,0")
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].split() == ["top_n", "return", "vol", "sharpe", "max", "dd", "trades"]
    assert len(lines) == 4
    assert "refused: " in lines[3] and "top_n must be a whole number of at least 1" in lines[3]


# migrate -----------------------------------------------------------------------------------------------------

def test_migrate_prints_todays_layout(tmp_path):
    old = tmp_path / "old.json"
    old.write_text('{"signal": "reversion", "window": 10, "capital": 500000, "frequency": "daily"}',
                   encoding="utf-8")
    proc = run_tool("migrate", str(old))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"signal": {"type": "reversion", "window": 10}, "initial_capital": 500000,
                                       "rebalance": "daily"}


def test_migrate_refuses_a_parameter_of_another_signal(tmp_path):
    old = tmp_path / "old.json"
    old.write_text('{"signal": "momentum", "window": 10}', encoding="utf-8")
    proc = run_tool("migrate", str(old))
    assert proc.returncode == 2
    assert proc.stderr == f"error: {old}: 'window' is a reversion parameter, but the signal is 'momentum'\n"


# settings ----------------------------------------------------------------------------------------------------

def test_every_setting_has_a_description():
    from bt.config.defaults import DEFAULTS
    from bt.config.descriptions import DESCRIPTIONS
    assert list(DESCRIPTIONS) == list(DEFAULTS)


def test_settings_table_and_json():
    proc = run_tool("settings")
    assert proc.returncode == 0
    lines = proc.stdout.splitlines()
    assert lines[0].split() == ["setting", "default", "description"]
    assert lines[1].startswith("initial_capital") and "1000000.0" in lines[1]
    as_json = run_tool("settings", "--json")
    assert json.loads(as_json.stdout)["signal"] == {"type": "momentum"}


# batch -------------------------------------------------------------------------------------------------------

def test_batch_runs_each_config_and_reports_refusals(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"top_n": 0}', encoding="utf-8")
    proc = run_tool("batch", "--prices", str(DATA / "prices.csv"), str(DATA / "momentum.json"),
                    str(DATA / "reversion.json"), str(bad))
    assert proc.returncode == 1
    lines = proc.stdout.splitlines()
    assert lines[1].startswith("momentum.json") and lines[2].startswith("reversion.json")
    assert lines[3] == f"bad.json                    refused: {bad}: top_n must be a whole number of at least 1"


def test_batch_with_every_config_good():
    proc = run_tool("batch", "--prices", str(DATA / "prices.csv"), str(DATA / "momentum.json"))
    assert proc.returncode == 0 and len(proc.stdout.splitlines()) == 2


# walkforward -------------------------------------------------------------------------------------------------

def test_years_of():
    from bt.tools.walkforward import years_of
    assert years_of(["2024-12-30", "2024-12-31", "2025-01-02"]) == [("2024", "2024-12-30", "2024-12-31"),
                                                                     ("2025", "2025-01-02", "2025-01-02")]


def test_walkforward_runs_each_year():
    proc = run_tool("walkforward", "--prices", str(DATA / "prices.csv"), "--config", str(DATA / "reversion.json"))
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert [line[:4] for line in lines[1:]] == ["2024", "2025"]


def test_walkforward_skips_short_years():
    proc = run_tool("walkforward", "--prices", str(DATA / "prices.csv"), "--config", str(DATA / "reversion.json"),
                    "--min-days", "300")
    assert proc.stdout.splitlines()[1] == "2024   261 days: skipped"
