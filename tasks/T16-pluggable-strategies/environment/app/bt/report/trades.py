"""The trade log, written as CSV with --trades: one line per trade, in the order they were made.

`units` is signed (bought positive, sold negative); `side` says the same in a word. Numbers are written in full
(repr), as in the equity curve. A forced exit has the reason "forced exit", every other trade "rebalance".
"""
from bt.constants import TRADE_COLUMNS


def trade_line(trade):
    return (f"{trade['date']},{trade['symbol']},{trade['side']},{trade['units']!r},{trade['price']!r},"
            f"{trade['notional']!r},{trade['commission']!r},{trade['slippage']!r},{trade['reason']}\n")


def write_trade_log(path, trades):
    """Write the log: a header, then one line per trade."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write(",".join(TRADE_COLUMNS) + "\n")
        for trade in trades:
            handle.write(trade_line(trade))


def trades_by_symbol(trades):
    """How many trades each symbol had, in the order each first traded."""
    counts = {}
    for trade in trades:
        counts[trade["symbol"]] = counts.get(trade["symbol"], 0) + 1
    return counts
