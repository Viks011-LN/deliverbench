"""The legacy code: the reconciliation test (the 2021 runner and the engine agree, day by day, on the sample) and
the 3.x config layout.

The desk proved the package split changed nothing with the first test, and keeps it so that it stays proved.
"""
import pytest

from bt.engine import run_backtest
from bt.legacy.config_v3 import MigrationError, migrate
from bt.legacy.runner import LegacyUnsupported, run_momentum


def test_legacy_runner_matches_the_engine_on_the_sample(sample, sample_config):
    dates, symbols, prices = sample
    config = sample_config("momentum")
    legacy = run_momentum(dates, symbols, prices, config)
    engine = run_backtest(dates, symbols, prices, config)["curve"]
    assert [row["nav"] for row in legacy] == [row["nav"] for row in engine]


def test_legacy_runner_refuses_what_it_never_did(sample, sample_config):
    dates, symbols, prices = sample
    with pytest.raises(LegacyUnsupported):
        run_momentum(dates, symbols, prices, sample_config("reversion"))


def test_legacy_runner_refuses_interest(sample, sample_config):
    dates, symbols, prices = sample
    config = dict(sample_config("momentum"), cash_rate=0.01)
    with pytest.raises(LegacyUnsupported, match="interest"):
        run_momentum(dates, symbols, prices, config)


def test_migrate_moves_the_signal_parameters_into_the_signal():
    old = {"lookback": 40, "top_n": 2, "skip": 3}
    assert migrate(old) == {"signal": {"type": "momentum", "lookback": 40, "skip": 3}, "top_n": 2}


def test_migrate_renames_old_settings():
    old = {"signal": "momentum", "capital": 250000, "cost_bps": 3.0, "max_position": 0.2, "fill_days": 2}
    assert migrate(old) == {"signal": {"type": "momentum"}, "initial_capital": 250000, "commission_bps": 3.0,
                            "max_weight": 0.2, "max_fill_gap": 2}


def test_migrate_keeps_the_order_of_the_old_file():
    assert list(migrate({"top_n": 1, "frequency": "weekly", "allow_short": True})) == [
        "signal", "top_n", "rebalance", "allow_short"]


def test_migrate_refuses_a_new_config():
    with pytest.raises(MigrationError, match="already has a signal section"):
        migrate({"signal": {"type": "momentum"}})


def test_migrate_refuses_mixed_parameters():
    with pytest.raises(MigrationError, match="'entry_z' is a reversion parameter"):
        migrate({"signal": "momentum", "entry_z": 1.0})
