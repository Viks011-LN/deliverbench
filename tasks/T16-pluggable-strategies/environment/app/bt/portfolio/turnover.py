"""The turnover cap: on a rebalancing day, the trades together may move at most max_turnover of the NAV.

When the planned trades would move more, every one of them is cut by the same factor, so each name moves the same
fraction of the way to its target; the rest waits for the next rebalancing. The band (rebalance_band) applies to
the cut trades.
"""


def planned_turnover(targets, units, prices_today):
    """The notional the trades to `targets` would move, added up in the order of `targets`."""
    total = 0.0
    for symbol, target in targets.items():
        total += abs(target - units[symbol]) * prices_today[symbol]
    return total


def limit_turnover(targets, units, prices_today, nav, max_turnover):
    """The targets after the cap: unchanged without a cap or within it, else each trade cut by the same factor."""
    if max_turnover is None:
        return targets
    total = planned_turnover(targets, units, prices_today)
    limit = max_turnover * nav
    if total <= limit:
        return targets
    factor = limit / total
    return {symbol: units[symbol] + factor * (target - units[symbol]) for symbol, target in targets.items()}
