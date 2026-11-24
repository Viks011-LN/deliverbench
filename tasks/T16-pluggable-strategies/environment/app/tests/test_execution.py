"""Execution: costs, the borrow fee, forced exits and the book."""
import pytest

from bt.config import DEFAULTS
from bt.execution import Book, borrow_fee, trade_cost
from bt.execution.costs import commission, slippage

CONFIG = dict(DEFAULTS)


def test_commission_and_slippage_in_basis_points():
    assert commission(100000.0, 5.0, 0.0) == 100000.0 * 5.0 / 10000.0
    assert slippage(100000.0, 2.0) == 100000.0 * 2.0 / 10000.0


def test_minimum_commission():
    assert commission(1000.0, 5.0, 25.0) == 25.0


def test_trade_cost_uses_the_config():
    assert trade_cost(200000.0, CONFIG) == (100.0, 40.0)


def test_borrow_fee_is_a_daily_share_of_the_yearly_rate():
    assert borrow_fee(-100.0, 50.0, 50.0) == pytest.approx(5000.0 * 0.005 / 252)


def test_a_new_book_is_all_cash():
    book = Book(1000000.0, ["A", "B"])
    assert book.cash == 1000000.0
    assert book.units == {"A": 0.0, "B": 0.0}
    assert book.value() == 1000000.0
    assert book.stats["trades"] == 0


def test_trade_to_buys_and_pays_costs():
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, CONFIG)
    book.trade_to("A", 1000.0, 50.0, 1000000.0, CONFIG)
    assert book.units["A"] == 1000.0
    assert book.cash == 1000000.0 - 50000.0 - (25.0 + 10.0)
    assert book.pnl["A"] == -35.0
    assert book.stats["trades"] == 1
    assert book.stats["traded_notional"] == 50000.0


def test_trades_inside_the_band_are_skipped():
    config = dict(CONFIG, rebalance_band=0.1)
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, config)
    book.trade_to("A", 1000.0, 50.0, 1000000.0, config)
    assert book.units["A"] == 0.0 and book.stats["trades"] == 0


def test_mark_books_profit_and_loss():
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, CONFIG)
    book.trade_to("A", 100.0, 50.0, 1000000.0, CONFIG)
    book.mark({"A": 52.0}, CONFIG)
    assert book.pnl["A"] == pytest.approx(200.0 - 3.5)
    assert book.last_price["A"] == 52.0


def test_a_missing_price_forces_an_exit_at_the_last_price():
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, CONFIG)
    book.trade_to("A", 100.0, 50.0, 1000000.0, CONFIG)
    cash_before = book.cash
    book.mark({"A": None}, CONFIG)
    assert book.units["A"] == 0.0
    assert book.stats["forced_exits"] == 1 and book.stats["trades"] == 2
    assert book.cash == pytest.approx(cash_before + 5000.0 - 2.5 - 1.0)


def test_shorts_pay_borrow():
    config = dict(CONFIG, borrow_bps=100.0)
    book = Book(1000000.0, ["A"])
    book.mark({"A": 20.0}, config)
    book.trade_to("A", -500.0, 20.0, 1000000.0, config)
    cash = book.cash
    book.charge_borrow(config)
    fee = borrow_fee(-500.0, 20.0, 100.0)
    assert book.cash == cash - fee
    assert book.stats["borrow_fees"] == fee


def test_trades_are_logged_with_their_reason():
    book = Book(1000000.0, ["A"])
    book.begin_day("2026-01-05")
    book.mark({"A": 50.0}, CONFIG)
    book.trade_to("A", 100.0, 50.0, 1000000.0, CONFIG)
    book.begin_day("2026-01-06")
    book.mark({"A": None}, CONFIG)
    assert [(t["date"], t["side"], t["units"], t["reason"]) for t in book.log] == [
        ("2026-01-05", "buy", 100.0, "rebalance"), ("2026-01-06", "sell", -100.0, "forced exit")]
    assert book.log[0]["commission"] == 2.5 and book.log[0]["slippage"] == 1.0


def test_skipped_trades_are_not_logged():
    config = dict(CONFIG, rebalance_band=0.1)
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, config)
    book.trade_to("A", 1000.0, 50.0, 1000000.0, config)
    assert book.log == []


def test_cash_earns_the_cash_rate():
    book = Book(1000000.0, ["A"])
    book.accrue_interest(dict(CONFIG, cash_rate=0.0252))
    assert book.cash == 1000000.0 + 1000000.0 * 0.0252 / 252
    assert book.stats["interest"] == 1000000.0 * 0.0252 / 252


def test_a_negative_balance_pays_interest():
    book = Book(1000.0, ["A"])
    book.cash = -500.0
    book.accrue_interest(dict(CONFIG, cash_rate=0.05))
    assert book.cash < -500.0 and book.stats["interest"] < 0.0


def test_no_interest_at_a_zero_rate():
    book = Book(1000.0, ["A"])
    book.accrue_interest(CONFIG)
    assert book.cash == 1000.0 and book.stats["interest"] == 0.0


def test_a_new_position_records_its_entry_price():
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, CONFIG)
    book.trade_to("A", 100.0, 50.0, 1000000.0, CONFIG)
    book.mark({"A": 55.0}, CONFIG)
    book.trade_to("A", 150.0, 55.0, 1000000.0, CONFIG)
    assert book.entry_price["A"] == 50.0
    book.trade_to("A", -40.0, 55.0, 1000000.0, CONFIG)
    assert book.entry_price["A"] == 55.0
    book.trade_to("A", 0.0, 55.0, 1000000.0, CONFIG)
    assert book.entry_price["A"] is None


def test_a_long_position_is_stopped_out_at_the_close():
    config = dict(CONFIG, stop_loss=0.1)
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, config)
    book.trade_to("A", 100.0, 50.0, 1000000.0, config)
    book.mark({"A": 45.5}, config)
    book.check_stops({"A": 45.5}, config)
    assert book.units["A"] == 100.0
    book.mark({"A": 45.0}, config)
    book.check_stops({"A": 45.0}, config)
    assert book.units["A"] == 0.0
    assert book.stats["stop_losses"] == 1 and book.stats["trades"] == 2
    assert book.log[-1]["reason"] == "stop loss" and book.log[-1]["price"] == 45.0


def test_a_short_position_is_stopped_out_when_the_price_rises():
    config = dict(CONFIG, stop_loss=0.2)
    book = Book(1000000.0, ["A"])
    book.mark({"A": 20.0}, config)
    book.trade_to("A", -100.0, 20.0, 1000000.0, config)
    book.mark({"A": 24.0}, config)
    book.check_stops({"A": 24.0}, config)
    assert book.units["A"] == 0.0 and book.log[-1]["side"] == "buy"


def test_no_stops_without_a_stop_loss():
    book = Book(1000000.0, ["A"])
    book.mark({"A": 50.0}, CONFIG)
    book.trade_to("A", 100.0, 50.0, 1000000.0, CONFIG)
    book.mark({"A": 1.0}, CONFIG)
    book.check_stops({"A": 1.0}, CONFIG)
    assert book.units["A"] == 100.0


def test_end_of_day_exposures():
    book = Book(1000.0, ["A", "B"])
    book.mark({"A": 10.0, "B": 10.0}, CONFIG)
    book.units = {"A": 50.0, "B": -20.0}
    book.cash = 650.0
    row = book.end_of_day("2026-01-05")
    assert row["nav"] == 650.0 + 500.0 - 200.0
    assert row["gross"] == 700.0 / 950.0
    assert row["net"] == 300.0 / 950.0
    assert row["holdings"] == 2
