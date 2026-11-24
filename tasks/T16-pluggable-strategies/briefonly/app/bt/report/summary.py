"""The one-page text summary (--format text), for the morning meeting.

Numbers are rounded for reading; the JSON report has them in full.
"""
from bt.metrics import monthly_returns, yearly_returns
from bt.metrics.drawdowns import worst_drawdowns
from bt.metrics.holding import position_stats
from bt.report.calendar_grid import monthly_grid
from bt.report.formatting import money, percent, ratio, row
from bt.signals.slot import find_strategy, parameters


def strategy_line(signal):
    """The strategy as it ran: its type, then each parameter with its value (as str() writes it), defaults filled
    in, in the order of the strategy's PARAMETERS. A strategy with no parameters shows its type alone."""
    kind = signal["type"]
    strategy = find_strategy(kind)
    params = parameters(strategy, signal) if strategy is not None else {}
    if not params:
        return f"Strategy: {kind}"
    return f"Strategy: {kind} (" + ", ".join(f"{name} {value!s}" for name, value in params.items()) + ")"


def book_line(config):
    """How the book is built: its size, its sides, the schedule and the limits."""
    sides = "long-short" if config["allow_short"] else "long only"
    line = f"Book: top {config['top_n']}, {sides}, rebalanced {config['rebalance']}"
    line += f", max weight {percent(config['max_weight'])}"
    if config["rebalance_band"] > 0:
        line += f", band {percent(config['rebalance_band'])}"
    if config["min_price"] > 0:
        line += f", min price {money(config['min_price'])}"
    if config["exclude"]:
        line += f", excluding {' '.join(config['exclude'])}"
    return line


def risk_line(config):
    """The volatility target and the drawdown control, or "none"."""
    if config["vol_target"] is None:
        target = "none"
    else:
        target = f"{percent(config['vol_target'])} over {config['vol_window']} days, leverage at most " \
                 f"{ratio(config['max_leverage'])}"
    if config["drawdown_limit"] is None:
        control = "none"
    else:
        control = f"x{ratio(config['drawdown_scale'])} beyond {percent(config['drawdown_limit'])}"
    line = f"Risk: volatility target {target}; drawdown control {control}"
    if config["stop_loss"] is not None:
        line += f"; stop loss {percent(config['stop_loss'])}"
    if config["max_turnover"] is not None:
        line += f"; turnover at most {percent(config['max_turnover'])}"
    return line


def positions_row(result, dates):
    """Positions opened and how long the closed ones were held."""
    stats = position_stats(result["trades"], dates)
    held = "n/a" if stats["average_days_held"] is None else f"{stats['average_days_held']:.1f}"
    return row("Positions", f"{stats['opened']} ({held} days)")


def benchmark_rows(benchmark):
    """The benchmark's rows of the table, when there is a benchmark."""
    if benchmark is None:
        return []
    return [
        row(f"Benchmark {benchmark['symbol']}", percent(benchmark["total_return"])),
        row("Excess return", percent(benchmark["excess_return"])),
        row("Beta", ratio(benchmark["beta"])),
        row("Tracking error", percent(benchmark["tracking_error"])),
        row("Information ratio", ratio(benchmark["information_ratio"])),
    ]


def drawdown_lines(curve):
    """The worst drawdowns, one line each."""
    lines = ["Worst drawdowns"]
    periods = worst_drawdowns(curve)
    if not periods:
        return lines + ["  none"]
    for p in periods:
        ending = f"recovered {p['recovery']}" if p["recovery"] is not None else "not recovered"
        lines.append(f"  {percent(p['depth']):>8}  {p['peak']} to {p['trough']}, {ending} ({p['days']} days)")
    return lines


def render_summary(dates, config, result, metrics, benchmark=None):
    """The summary as text, ending with a newline."""
    curve = result["curve"]
    costs = metrics["commissions"] + metrics["slippage"] + metrics["borrow_fees"]
    lines = [
        f"Backtest {dates[0]} to {dates[-1]} ({len(dates)} days)",
        strategy_line(config["signal"]),
        book_line(config),
        risk_line(config),
        "",
        row("Total return", percent(metrics["total_return"])),
        row("Annual return", percent(metrics["annual_return"])),
        row("Annual volatility", percent(metrics["annual_volatility"])),
        row("Sharpe", ratio(metrics["sharpe"])),
        row("Sortino", ratio(metrics["sortino"])),
        row("Calmar", ratio(metrics["calmar"])),
        row("Max drawdown", percent(metrics["max_drawdown"])),
        row("Hit rate", percent(metrics["hit_rate"])),
        *benchmark_rows(benchmark),
        row("Trades", f"{metrics['trades']} ({metrics['forced_exits']}f {metrics['stop_losses']}s)"),
        positions_row(result, dates),
        row("Costs", money(costs)),
        row("Interest", money(metrics["interest"])),
        row("Final NAV", money(curve[-1]["nav"])),
        "",
        *drawdown_lines(curve),
        "",
        "Monthly returns",
        *monthly_grid(monthly_returns(curve), yearly_returns(curve)),
    ]
    return "\n".join(lines) + "\n"
