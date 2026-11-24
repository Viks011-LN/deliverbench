"""The day loop: warm-up, schedule, sizing and the book, on the sample and on small hand-made markets."""
import pytest

from bt.config import DEFAULTS
from bt.engine import first_trading_day, run_backtest
from bt.metrics.returns import daily_returns


def config_with(**settings):
    config = dict(DEFAULTS)
    config["signal"] = dict(DEFAULTS["signal"])
    config.update(settings)
    return config


def trading_days(curve):
    """Indices of the days on which the book changed (cash moved)."""
    return [t for t in range(1, len(curve)) if curve[t]["cash"] != curve[t - 1]["cash"]]


def test_first_trading_day_momentum():
    assert first_trading_day({"type": "momentum", "lookback": 60}, config_with()) == 60
    assert first_trading_day({"type": "momentum", "lookback": 10}, config_with(vol_window=25)) == 25


def test_first_trading_day_reversion():
    assert first_trading_day({"type": "reversion", "window": 30}, config_with()) == 30
    assert first_trading_day({"type": "reversion"}, config_with(vol_window=15)) == 20


def test_nothing_is_traded_before_the_warm_up(sample, sample_config):
    dates, symbols, prices = sample
    config = sample_config("momentum")
    curve = run_backtest(dates, symbols, prices, config)["curve"]
    start = first_trading_day(config["signal"], config)
    assert all(row["nav"] == config["initial_capital"] for row in curve[:start])
    assert all(row["gross"] == 0.0 for row in curve[:start])
    assert curve[start]["gross"] > 0.0


def test_monthly_rebalancing_trades_on_month_starts(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 20, "skip": 2}, top_n=2)
    curve = run_backtest(dates, symbols, prices, config)["curve"]
    days = trading_days(curve)
    assert days[0] == 20
    assert all(dates[t][:7] != dates[t - 1][:7] for t in days[1:])


def test_daily_rebalancing_trades_more(small_market):
    dates, symbols, prices = small_market
    monthly = run_backtest(dates, symbols, prices, config_with(signal={"type": "momentum", "lookback": 20}))
    daily = run_backtest(dates, symbols, prices,
                         config_with(signal={"type": "momentum", "lookback": 20}, rebalance="daily"))
    assert daily["stats"]["trades"] > monthly["stats"]["trades"]


def test_one_row_per_day(sample, sample_config):
    dates, symbols, prices = sample
    result = run_backtest(dates, symbols, prices, sample_config("reversion"))
    assert [row["date"] for row in result["curve"]] == dates


def test_too_short_to_trade_leaves_the_capital_untouched(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 200, "skip": 5})
    result = run_backtest(dates, symbols, prices, config)
    assert result["stats"]["trades"] == 0
    assert all(row["nav"] == 1000000.0 for row in result["curve"])


def test_only_shorts_pay_borrow(small_market):
    dates, symbols, prices = small_market
    long_only = run_backtest(dates, symbols, prices, config_with(signal={"type": "momentum", "lookback": 20}))
    long_short = run_backtest(dates, symbols, prices,
                              config_with(signal={"type": "momentum", "lookback": 20}, allow_short=True))
    assert long_only["stats"]["borrow_fees"] == 0.0
    assert long_short["stats"]["borrow_fees"] > 0.0


def test_vol_target_changes_the_exposure(small_market):
    dates, symbols, prices = small_market
    plain = run_backtest(dates, symbols, prices, config_with(signal={"type": "momentum", "lookback": 20}))
    scaled = run_backtest(dates, symbols, prices,
                          config_with(signal={"type": "momentum", "lookback": 20}, vol_target=0.05))
    assert scaled["curve"][-1]["gross"] != plain["curve"][-1]["gross"]


def test_min_price_leaves_out_cheap_names(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 20}, min_price=60.0, top_n=4)
    result = run_backtest(dates, symbols, prices, config)
    assert result["units"]["UPPA"] == 0.0 or prices["UPPA"][-1] >= 60.0
    assert result["units"]["SWNG"] == 0.0


def test_the_weight_cap_holds_on_rebalancing_days(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 20}, top_n=2, max_weight=0.3)
    result = run_backtest(dates, symbols, prices, config)
    assert 0.59 < result["curve"][20]["gross"] < 0.601


def test_excluded_names_are_never_held(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 20}, rebalance="daily", exclude=["UPPA", "XXXX"])
    result = run_backtest(dates, symbols, prices, config)
    assert all(trade["symbol"] != "UPPA" for trade in result["trades"])
    assert result["trades"]


def test_cash_earns_interest_from_the_second_day(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 200, "skip": 5}, cash_rate=0.0252)
    curve = run_backtest(dates, symbols, prices, config)["curve"]
    assert curve[0]["nav"] == 1000000.0
    assert curve[1]["nav"] == 1000000.0 + 1000000.0 * 0.0252 / 252


def test_the_trade_log_matches_the_statistics(sample, sample_config):
    dates, symbols, prices = sample
    result = run_backtest(dates, symbols, prices, sample_config("momentum"))
    assert len(result["trades"]) == result["stats"]["trades"]
    forced = [t for t in result["trades"] if t["reason"] == "forced exit"]
    assert len(forced) == result["stats"]["forced_exits"]


def test_the_turnover_cap_limits_each_rebalancing(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 20}, rebalance="daily", max_turnover=0.2)
    result = run_backtest(dates, symbols, prices, config)
    by_day = {}
    for trade in result["trades"]:
        by_day[trade["date"]] = by_day.get(trade["date"], 0.0) + trade["notional"]
    navs = {row["date"]: row["nav"] for row in result["curve"]}
    first = dates[20]
    assert by_day[first] == pytest.approx(0.2 * 1000000.0)
    assert all(total <= 0.2 * navs[day] * 1.01 for day, total in by_day.items())


def test_turnover_under_the_cap_is_untouched(small_market):
    dates, symbols, prices = small_market
    plain = run_backtest(dates, symbols, prices, config_with(signal={"type": "momentum", "lookback": 20}))
    capped = run_backtest(dates, symbols, prices,
                          config_with(signal={"type": "momentum", "lookback": 20}, max_turnover=5.0))
    assert capped == plain


def test_min_history_waits_for_a_late_listing(tmp_path):
    from conftest import trending, weekdays, write_prices
    from bt.data import load_prices
    from datetime import date
    days = weekdays(date(2025, 6, 2), 80)
    columns = {"OLD": trending(50.0, 0.001, 80), "NEW": [None] * 30 + trending(20.0, 0.01, 50)}
    dates, symbols, prices = load_prices(str(write_prices(tmp_path / "p.csv", days, columns)))
    settings = dict(signal={"type": "momentum", "lookback": 10, "skip": 1}, rebalance="daily", top_n=2)
    early = run_backtest(dates, symbols, prices, config_with(**settings))
    late = run_backtest(dates, symbols, prices, config_with(min_history=30, **settings))
    first_new = lambda result: min(t["date"] for t in result["trades"] if t["symbol"] == "NEW")  # noqa: E731
    assert first_new(early) == dates[40]
    assert first_new(late) == dates[59]


def test_a_stop_loss_closes_a_falling_position(small_market):
    dates, symbols, prices = small_market
    settings = dict(signal={"type": "momentum", "lookback": 20}, top_n=1)
    first = run_backtest(dates, symbols, prices, config_with(**settings))["trades"][0]
    assert first["date"] == dates[20] and first["side"] == "buy"
    held = first["symbol"]
    prices[held] = [p * (0.8 if t >= 30 else 1.0) for t, p in enumerate(prices[held])]
    plain = run_backtest(dates, symbols, prices, config_with(**settings))
    stopped = run_backtest(dates, symbols, prices, config_with(stop_loss=0.1, **settings))
    assert plain["stats"]["stop_losses"] == 0
    assert stopped["stats"]["stop_losses"] == 1
    assert [t["date"] for t in stopped["trades"] if t["reason"] == "stop loss"] == [dates[30]]


def test_profit_and_loss_adds_up(sample, sample_config):
    dates, symbols, prices = sample
    result = run_backtest(dates, symbols, prices, sample_config("reversion"))
    total = sum(result["pnl"].values())
    assert result["curve"][-1]["nav"] - 1000000.0 == pytest.approx(total, abs=1e-4)


def test_runs_are_reproducible(sample, sample_config):
    dates, symbols, prices = sample
    first = run_backtest(dates, symbols, prices, sample_config("momentum"))
    second = run_backtest(dates, symbols, prices, sample_config("momentum"))
    assert first == second


def test_the_sample_has_a_forced_exit(sample, sample_config):
    dates, symbols, prices = sample
    result = run_backtest(dates, symbols, prices, sample_config("momentum"))
    assert result["stats"]["forced_exits"] >= 1


def test_drawdown_control_cuts_exposure_after_a_fall(small_market):
    dates, symbols, prices = small_market
    for symbol in symbols:
        prices[symbol] = [p * (0.7 if 80 <= t < 140 else 1.0) for t, p in enumerate(prices[symbol])]
    settings = dict(signal={"type": "momentum", "lookback": 20, "skip": 2}, rebalance="daily")
    plain = run_backtest(dates, symbols, prices, config_with(**settings))
    controlled = run_backtest(dates, symbols, prices, config_with(drawdown_limit=0.1, **settings))
    assert plain["curve"][110]["gross"] > 0.7
    assert controlled["curve"][110]["gross"] < 0.5


def test_daily_returns_of_a_flat_run_are_zero(small_market):
    dates, symbols, prices = small_market
    config = config_with(signal={"type": "momentum", "lookback": 200, "skip": 5})
    curve = run_backtest(dates, symbols, prices, config)["curve"]
    assert set(daily_returns(curve)) == {0.0}
