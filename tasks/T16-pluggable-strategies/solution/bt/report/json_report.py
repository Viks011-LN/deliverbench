"""The JSON report printed on stdout (the default output).

Every number is written in full (json writes floats as repr does), so nothing is lost to rounding and two runs
can be compared byte for byte (bt/tools/compare.py does it). The key order is fixed: the operations team's parsers
read some fields by position (docs/operations.md).
"""
from bt.config.signal_params import signal_parameters
from bt.metrics import monthly_returns, yearly_returns
from bt.metrics.drawdowns import worst_drawdowns
from bt.metrics.holding import position_stats


def signal_echo(signal):
    """The signal as it ran: its type, then each of its parameters with defaults filled in, in the type's order."""
    return {"type": signal["type"], **signal_parameters(signal)}


def strategy_section(config):
    """The settings that shape the book."""
    return {
        "signal": signal_echo(config["signal"]),
        "top_n": config["top_n"],
        "allow_short": config["allow_short"],
        "max_weight": config["max_weight"],
        "min_price": config["min_price"],
        "exclude": config["exclude"],
        "rebalance": config["rebalance"],
        "rebalance_band": config["rebalance_band"],
        "vol_target": config["vol_target"],
        "vol_window": config["vol_window"],
        "max_leverage": config["max_leverage"],
        "drawdown_limit": config["drawdown_limit"],
        "drawdown_scale": config["drawdown_scale"],
        "stop_loss": config["stop_loss"],
        "max_turnover": config["max_turnover"],
        "min_history": config["min_history"],
        "benchmark": config["benchmark"],
    }


def costs_section(config):
    """The cost settings, and the rate on cash."""
    return {
        "commission_bps": config["commission_bps"],
        "min_commission": config["min_commission"],
        "slippage_bps": config["slippage_bps"],
        "borrow_bps": config["borrow_bps"],
        "cash_rate": config["cash_rate"],
    }


def final_positions(symbols, result, final_nav):
    """The positions held at the end: units, last price, value and weight of the final NAV."""
    positions = {}
    for symbol in symbols:
        held = result["units"][symbol]
        if held != 0.0:
            price = result["last_price"][symbol]
            positions[symbol] = {
                "units": held,
                "price": price,
                "value": held * price,
                "weight": held * price / final_nav,
            }
    return positions


def build_report(dates, symbols, config, result, metrics, benchmark=None):
    """The full report, as a dict in print order. `benchmark` is the benchmark section, when there is one."""
    curve = result["curve"]
    report = {
        "period": {"start": dates[0], "end": dates[-1], "days": len(dates)},
        "capital": {"initial": config["initial_capital"], "final": curve[-1]["nav"]},
        "strategy": strategy_section(config),
        "costs": costs_section(config),
        "metrics": metrics,
    }
    if benchmark is not None:
        report["benchmark"] = benchmark
    report["drawdowns"] = worst_drawdowns(curve)
    report["positions"] = position_stats(result["trades"], dates)
    report["monthly_returns"] = monthly_returns(curve)
    report["yearly_returns"] = yearly_returns(curve)
    report["pnl_by_symbol"] = result["pnl"]
    report["final_positions"] = final_positions(symbols, result, curve[-1]["nav"])
    return report
