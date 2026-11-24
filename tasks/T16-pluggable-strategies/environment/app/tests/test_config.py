"""Loading and validating the config file: defaults, and the message for each kind of problem."""
import json

import pytest

from bt.config import DEFAULTS, load_config
from bt.errors import BacktestError, ConfigError


def test_defaults_are_filled_in(config_file):
    config = load_config(config_file("{}"))
    assert config == DEFAULTS
    assert list(config) == list(DEFAULTS)


def test_the_default_signal_is_momentum(config_file):
    assert load_config(config_file("{}"))["signal"] == {"type": "momentum"}


def test_signal_section_is_kept_as_given(config_file):
    config = load_config(config_file('{"signal": {"type": "reversion", "window": 12}}'))
    assert config["signal"] == {"type": "reversion", "window": 12}


def test_settings_are_laid_over_the_defaults(config_file):
    config = load_config(config_file('{"top_n": 5, "vol_target": 0.1}'))
    assert config["top_n"] == 5
    assert config["vol_target"] == 0.1
    assert config["max_weight"] == DEFAULTS["max_weight"]


def test_the_defaults_are_not_shared_between_loads(config_file):
    first = load_config(config_file("{}"))
    first["signal"]["type"] = "changed"
    first["exclude"].append("IDX")
    second = load_config(config_file("{}"))
    assert second["signal"] == {"type": "momentum"}
    assert second["exclude"] == []


def test_config_errors_are_backtest_errors():
    assert issubclass(ConfigError, BacktestError)


def test_not_json(config_file):
    path = config_file('{"top_n": 3,\n')
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert str(caught.value).startswith(f"{path}: not valid JSON (")
    assert str(caught.value).endswith("line 2)")


@pytest.mark.parametrize("raw,message", [
    ([1, 2, 3], "the config must be a JSON object"),
    ({"lookbak": 30}, "unknown setting 'lookbak'"),
    ({"signal": "momentum"}, "signal must be a JSON object"),
    ({"signal": {"type": "carry"}}, "unknown signal type 'carry'"),
    ({"signal": {"type": "momentum", "window": 20}}, "signal: momentum has no parameter 'window'"),
    ({"signal": {"type": "momentum", "lookback": 60.0}}, "signal.lookback must be a whole number of at least 2"),
    ({"signal": {"type": "momentum", "lookback": 1}}, "signal.lookback must be a whole number of at least 2"),
    ({"signal": {"type": "momentum", "skip": 60}}, "signal.skip must be a whole number from 0 to lookback - 1"),
    ({"signal": {"type": "momentum", "skip": -1}}, "signal.skip must be a whole number from 0 to lookback - 1"),
    ({"signal": {"type": "reversion", "window": 1}}, "signal.window must be a whole number of at least 2"),
    ({"signal": {"type": "reversion", "entry_z": "high"}}, "signal.entry_z must be a number of at least 0"),
    ({"rebalance": "quarterly"}, "rebalance must be one of daily, weekly, monthly"),
    ({"top_n": 0}, "top_n must be a whole number of at least 1"),
    ({"top_n": 2.5}, "top_n must be a whole number of at least 1"),
    ({"vol_window": 1}, "vol_window must be a whole number of at least 2"),
    ({"max_fill_gap": -1}, "max_fill_gap must be a whole number of at least 0"),
    ({"allow_short": "yes"}, "allow_short must be true or false"),
    ({"max_weight": 0}, "max_weight must be a positive number"),
    ({"initial_capital": "a lot"}, "initial_capital must be a positive number"),
    ({"commission_bps": -1}, "commission_bps must be a number of at least 0"),
    ({"min_price": -5}, "min_price must be a number of at least 0"),
    ({"vol_target": 0}, "vol_target must be a positive number or null"),
    ({"drawdown_limit": -0.1}, "drawdown_limit must be a positive number or null"),
    ({"drawdown_scale": 1.5}, "drawdown_scale must be above 0 and at most 1"),
    ({"stop_loss": 1.0}, "stop_loss must be above 0 and below 1, or null"),
    ({"max_turnover": 0}, "max_turnover must be a positive number or null"),
    ({"min_history": -2}, "min_history must be a whole number of at least 0"),
    ({"exclude": "IDX"}, "exclude must be a list of symbols"),
    ({"exclude": ["IDX", 3]}, "exclude must be a list of symbols"),
    ({"benchmark": ["IDX"]}, "benchmark must be a symbol or null"),
    ({"cash_rate": "2%"}, "cash_rate must be a number"),
])
def test_each_problem_has_its_message(config_file, raw, message):
    path = config_file(json.dumps(raw))
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert str(caught.value) == f"{path}: {message}"


def test_an_unknown_setting_is_reported_before_a_bad_signal(config_file):
    path = config_file('{"signal": {"type": "carry"}, "colour": "blue"}')
    with pytest.raises(ConfigError, match="unknown setting 'colour'"):
        load_config(path)


def test_the_first_unknown_setting_in_the_file_is_reported(config_file):
    path = config_file('{"zeta": 1, "alpha": 2}')
    with pytest.raises(ConfigError, match="unknown setting 'zeta'"):
        load_config(path)


def test_a_negative_cash_rate_is_allowed(config_file):
    assert load_config(config_file('{"cash_rate": -0.005}'))["cash_rate"] == -0.005


def test_null_targets_are_allowed(config_file):
    config = load_config(config_file('{"vol_target": null, "drawdown_limit": null}'))
    assert config["vol_target"] is None and config["drawdown_limit"] is None


def test_missing_config_file_is_an_os_error(tmp_path):
    with pytest.raises(OSError):
        load_config(str(tmp_path / "missing.json"))
