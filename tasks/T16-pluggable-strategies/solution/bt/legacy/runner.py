"""The 2021 runner: momentum only, long only, monthly, no volatility target, no drawdown control.

Kept because the reconciliation test (tests/test_legacy.py) runs it next to the engine on the sample: the two
must agree on every day's NAV, which is how the desk proved the package split changed nothing. It is not wired
into the command line. It refuses anything the old runner never did rather than run it differently.
"""
from bt.constants import BPS
from bt.data.calendar import new_month, parse_day
from bt.data.series import forward_fill
from bt.portfolio.caps import apply_weight_cap
from bt.portfolio.ranking import scores_to_weights
from bt.signals.momentum import LOOKBACK, SKIP, momentum_score


class LegacyUnsupported(ValueError):
    """The config uses something the 2021 runner never had."""


def check_supported(config):
    signal = config["signal"]
    if signal.get("type") != "momentum":
        raise LegacyUnsupported("the legacy runner runs momentum only")
    if config["allow_short"]:
        raise LegacyUnsupported("the legacy runner is long only")
    if config["rebalance"] != "monthly":
        raise LegacyUnsupported("the legacy runner rebalances monthly")
    if config["vol_target"] is not None or config["drawdown_limit"] is not None:
        raise LegacyUnsupported("the legacy runner has no volatility target or drawdown control")
    if config["min_price"] > 0 or config["exclude"]:
        raise LegacyUnsupported("the legacy runner has no price floor and no exclusion list")
    if config["cash_rate"] != 0.0:
        raise LegacyUnsupported("the legacy runner pays no interest on cash")
    if config["stop_loss"] is not None or config["max_turnover"] is not None or config["min_history"] > 1:
        raise LegacyUnsupported("the legacy runner has no stop loss, turnover cap or minimum history")


def run_momentum(dates, symbols, raw_prices, config):
    """The old day loop. Returns one {"date", "nav"} row per day."""
    check_supported(config)
    signal = config["signal"]
    lookback = signal.get("lookback", LOOKBACK)
    skip = signal.get("skip", SKIP)
    prices = {symbol: forward_fill(raw_prices[symbol], config["max_fill_gap"]) for symbol in symbols}
    start = max(lookback, config["vol_window"])
    cash = float(config["initial_capital"])
    units = {symbol: 0.0 for symbol in symbols}
    last = {symbol: None for symbol in symbols}
    rows = []

    def costs(notional):
        fee = notional * config["commission_bps"] / BPS
        if fee < config["min_commission"]:
            fee = config["min_commission"]
        return fee, notional * config["slippage_bps"] / BPS

    for t in range(len(dates)):
        for symbol in symbols:
            price = prices[symbol][t]
            if price is not None:
                last[symbol] = price
            elif units[symbol] != 0.0:
                notional = abs(units[symbol]) * last[symbol]
                fee, slip = costs(notional)
                cash += units[symbol] * last[symbol]
                cash -= fee + slip
                units[symbol] = 0.0
        nav = cash
        for symbol in symbols:
            if units[symbol] != 0.0:
                nav += units[symbol] * last[symbol]
        month_start = t > 0 and new_month(parse_day(dates[t]), parse_day(dates[t - 1]))
        if t >= start and (t == start or month_start):
            scores = {}
            for symbol in symbols:
                series = prices[symbol]
                scores[symbol] = None if series[t] is None else momentum_score(series, t, lookback, skip)
            weights = apply_weight_cap(scores_to_weights(scores, config["top_n"], False), config["max_weight"])
            for symbol in symbols:
                price = prices[symbol][t]
                if price is None:
                    continue
                target = weights.get(symbol, 0.0) * 1.0 * nav / price
                trade = target - units[symbol]
                if trade == 0.0:
                    continue
                notional = abs(trade) * price
                if notional < config["rebalance_band"] * nav:
                    continue
                fee, slip = costs(notional)
                cash -= trade * price
                cash -= fee + slip
                units[symbol] = target
        value = cash
        for symbol in symbols:
            if units[symbol] != 0.0:
                value += units[symbol] * last[symbol]
        rows.append({"date": dates[t], "nav": value})
    return rows
