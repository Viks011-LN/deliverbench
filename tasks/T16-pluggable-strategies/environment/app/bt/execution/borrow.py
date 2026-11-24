"""The borrow fee on short positions.

Shorts pay a fee every trading day: borrow_bps per year of their market value, a year being TRADING_DAYS days.
"""
from bt.constants import BPS

TRADING_DAYS = 252


def borrow_fee(units, price, borrow_bps):
    """The day's borrow fee on a short of `units` (negative) at `price`: a positive amount."""
    return -units * price * borrow_bps / BPS / TRADING_DAYS
