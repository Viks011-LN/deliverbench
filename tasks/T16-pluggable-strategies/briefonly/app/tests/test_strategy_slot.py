"""The strategy slot (docs/design/strategy-slot.md): finding a strategy by its type, its parameters, its warm-up,
its scores and its echo, and a strategy plugged in from outside the package (the example in examples/)."""
import json
import shutil
import sys

import pytest

import bt.strategies
from conftest import APP
from bt.cli import main
from bt.config import load_config
from bt.engine import first_trading_day
from bt.errors import BacktestError, ConfigError
from bt.report.json_report import signal_echo
from bt.report.summary import strategy_line
from bt.signals import compute_scores
from bt.signals.slot import find_strategy, get_strategy, parameters, strategy_scores
from bt.strategies import momentum, reversion

EXAMPLES = APP / "examples"


@pytest.fixture
def plug_in(tmp_path, monkeypatch):
    """Make strategy files from a folder of their own findable as bt/strategies/<name>.py, for this test only."""
    folder = tmp_path / "strategies"
    folder.mkdir()
    monkeypatch.setattr(bt.strategies, "__path__", list(bt.strategies.__path__) + [str(folder)])
    added = []

    def plug(name, source):
        if isinstance(source, str):
            (folder / f"{name}.py").write_text(source, encoding="utf-8")
        else:
            shutil.copyfile(source, folder / f"{name}.py")
        added.append(name)
    yield plug
    for name in added:
        sys.modules.pop(f"bt.strategies.{name}", None)
        if hasattr(bt.strategies, name):
            delattr(bt.strategies, name)


def test_the_type_is_the_module_name():
    assert find_strategy("momentum") is momentum
    assert find_strategy("reversion") is reversion


@pytest.mark.parametrize("kind", ["carry", "Momentum", "MOMENTUM", "momentum ", "momentum.py", "", "__init__",
                                  "os", "../momentum", None, 5, 1.5, True, ["momentum"], {}])
def test_anything_else_names_no_strategy(kind):
    assert find_strategy(kind) is None


def test_the_built_ins_define_the_three_names():
    for strategy in (momentum, reversion):
        assert isinstance(strategy.PARAMETERS, dict)
        assert callable(strategy.warmup) and callable(strategy.score)
    assert momentum.PARAMETERS == {"lookback": 60, "skip": 5}
    assert reversion.PARAMETERS == {"window": 20, "entry_z": 1.0}


def test_parameters_fill_in_the_defaults_in_order():
    params = parameters(reversion, {"type": "reversion", "entry_z": 0.5})
    assert list(params.items()) == [("window", 20), ("entry_z", 0.5)]
    assert "type" not in parameters(momentum, {"type": "momentum"})


def test_the_warm_up_is_the_strategy_s():
    assert momentum.warmup({"lookback": 45, "skip": 5}) == 45
    assert reversion.warmup({"window": 12, "entry_z": 1.0}) == 12


def test_an_unknown_type_is_a_backtest_error():
    with pytest.raises(BacktestError, match="unknown signal type 'carry'"):
        get_strategy({"type": "carry"})
    with pytest.raises(BacktestError, match="unknown signal type None"):
        get_strategy({})


def test_scores_come_from_the_history_up_to_today():
    prices = {"AAA": [10.0, 11.0, 12.0, 13.0, 14.0], "BBB": [20.0, 19.0, None, 17.0, 16.0]}
    seen = []
    strategy = type(sys)("recorder")
    strategy.PARAMETERS = {}
    strategy.score = lambda history, params: seen.append((history, params)) or {"AAA": 1, "BBB": -1}
    assert strategy_scores(strategy, {}, prices, ["BBB", "AAA"], 2) == {"BBB": None, "AAA": 1}
    assert seen == [({"BBB": [20.0, 19.0, None], "AAA": [10.0, 11.0, 12.0]}, {})]


SIMPLE = '''
PARAMETERS = {"days": 3, "sign": 1, "label": "x"}


def warmup(params):
    return params["days"]


def score(history, params):
    return {s: (None if c[-1] is None or c[-1 - params["days"]] is None
                else params["sign"] * (c[-1] - c[-1 - params["days"]])) for s, c in history.items()}
'''


def test_a_new_strategy_is_one_file(plug_in, config_file):
    plug_in("simple", SIMPLE)
    config = load_config(config_file('{"signal": {"label": "y", "type": "simple", "days": 5}, "vol_window": 2}'))
    assert config["signal"] == {"label": "y", "type": "simple", "days": 5}
    assert first_trading_day(config["signal"], config) == 5
    assert signal_echo(config["signal"]) == {"type": "simple", "days": 5, "sign": 1, "label": "y"}
    assert list(signal_echo(config["signal"])) == ["type", "days", "sign", "label"]
    assert strategy_line(config["signal"]) == "Strategy: simple (days 5, sign 1, label y)"
    scores = compute_scores({"A": [1.0, 2.0, 3.0, 4.0, 5.0, 7.0]}, ["A"], 5, config["signal"])
    assert scores == {"A": 6.0}


def test_a_new_strategy_gets_today_s_messages(plug_in, config_file):
    plug_in("simple", SIMPLE)
    path = config_file('{"signal": {"type": "simple", "window": 5}}')
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert str(caught.value) == f"{path}: signal: simple has no parameter 'window'"


def test_the_built_ins_keep_their_checks(config_file):
    path = config_file('{"signal": {"type": "reversion", "window": 1, "entry_z": -1}, "top_n": 0}')
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert str(caught.value) == f"{path}: signal.window must be a whole number of at least 2"


def test_the_example_strategy_gives_its_expected_output(plug_in, tmp_path, monkeypatch, capsys):
    plug_in("channel", EXAMPLES / "strategies" / "channel.py")
    monkeypatch.chdir(APP)
    equity = tmp_path / "equity.csv"
    assert main(["--prices", "examples/prices.csv", "--config", "examples/channel.json",
                 "--equity", str(equity)]) == 0
    report = capsys.readouterr()
    assert report.out == (EXAMPLES / "expected" / "report.json").read_text(encoding="utf-8")
    assert report.err == ""
    assert equity.read_text(encoding="utf-8") == (EXAMPLES / "expected" / "equity.csv").read_text(encoding="utf-8")
    assert main(["--prices", "examples/prices.csv", "--config", "examples/channel.json", "--format", "text"]) == 0
    summary = capsys.readouterr()
    assert summary.out == (EXAMPLES / "expected" / "summary.txt").read_text(encoding="utf-8")
    assert summary.err == ""


def test_the_example_is_not_installed(config_file):
    path = config_file(json.dumps({"signal": {"type": "channel"}}))
    with pytest.raises(ConfigError, match="unknown signal type 'channel'"):
        load_config(path)
