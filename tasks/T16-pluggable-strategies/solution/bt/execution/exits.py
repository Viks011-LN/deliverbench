"""Closing a position outside a rebalancing: forced exits and stop losses.

A price is carried forward for at most max_fill_gap days. When a held name's price is missing for longer, the
position is sold (or bought back) at its last price, with the usual commission and slippage: a forced exit. With a
stop_loss, a position that has moved against its entry price by that fraction at today's close is closed at that
close: a stop loss. Both count as trades, each also as its own kind, and go into the trade log with their reason.
"""
from bt.constants import REASON_FORCED_EXIT, REASON_STOP_LOSS
from bt.execution.costs import trade_cost


def close_position(book, symbol, price, config, reason):
    """Close the position in `symbol` at `price`. Updates the book's cash, P&L, units, statistics and log."""
    held = book.units[symbol]
    notional = abs(held) * price
    fee, slip = trade_cost(notional, config)
    book.cash += held * price
    book.cash -= fee + slip
    book.pnl[symbol] -= fee + slip
    book.stats["commissions"] += fee
    book.stats["slippage"] += slip
    book.stats["traded_notional"] += notional
    book.units[symbol] = 0.0
    book.entry_price[symbol] = None
    book.stats["trades"] += 1
    book.record(symbol, -held, price, notional, fee, slip, reason)


def forced_exit(book, symbol, config):
    """Close the position in `symbol` at its last price: its price has been missing beyond the fill gap."""
    close_position(book, symbol, book.last_price[symbol], config, REASON_FORCED_EXIT)
    book.stats["forced_exits"] += 1


def stopped_out(held, price, entry, stop_loss):
    """True if a position of `held` units entered at `entry` has lost stop_loss of its entry price at `price`."""
    if held > 0.0:
        return price <= entry * (1.0 - stop_loss)
    return price >= entry * (1.0 + stop_loss)


def stop_loss_exit(book, symbol, config):
    """Close the position in `symbol` at today's close: it hit its stop."""
    close_position(book, symbol, book.last_price[symbol], config, REASON_STOP_LOSS)
    book.stats["stop_losses"] += 1
