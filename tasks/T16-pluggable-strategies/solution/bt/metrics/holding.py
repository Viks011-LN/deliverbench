"""Positions, from the trade log: how many were opened and closed, and how long they were held.

A position opens with a trade from no units and closes with a trade to no units (a rebalance, a forced exit or a
stop loss); a trade that takes a position to the other side keeps it open. Days held are trading days, from the
day it opened to the day it closed.
"""


def position_stats(trades, dates):
    """The positions section of the report, in print order."""
    index = {day: i for i, day in enumerate(dates)}
    open_since = {}
    opened = 0
    spans = []
    for trade in trades:
        symbol = trade["symbol"]
        if symbol not in open_since and trade["after"] != 0.0:
            open_since[symbol] = index[trade["date"]]
            opened += 1
        elif symbol in open_since and trade["after"] == 0.0:
            spans.append((symbol, index[trade["date"]] - open_since.pop(symbol)))
    longest = None
    for symbol, days in spans:
        if longest is None or days > longest["days"]:
            longest = {"symbol": symbol, "days": days}
    return {
        "opened": opened,
        "closed": len(spans),
        "still_open": len(open_since),
        "average_days_held": sum(days for _, days in spans) / len(spans) if spans else None,
        "longest_held": longest,
    }
