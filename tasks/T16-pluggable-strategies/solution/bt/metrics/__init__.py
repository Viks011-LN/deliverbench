"""The summary metrics of a run, from its equity curve and trading statistics (docs/metrics.md defines each one).
The benchmark's figures are in benchmark.py and the drawdown periods in drawdowns.py."""
import math

from bt.metrics.drawdown import max_drawdown
from bt.metrics.periods import monthly_returns, yearly_returns
from bt.metrics.ratios import TRADING_DAYS, calmar_ratio, sharpe_ratio, sortino_ratio
from bt.metrics.returns import daily_returns, mean, sample_std, wins_and_losses


def compute_metrics(curve, stats, config):
    """The summary metrics of a run, in the order the report prints them."""
    navs = [row["nav"] for row in curve]
    returns = daily_returns(curve)
    days = len(returns)
    wins, losses = wins_and_losses(returns)
    worst_drawdown = max_drawdown(navs)
    annual_return = mean(returns) * TRADING_DAYS
    return {
        "total_return": navs[-1] / navs[0] - 1.0,
        "annual_return": annual_return,
        "annual_volatility": sample_std(returns) * math.sqrt(TRADING_DAYS) if days >= 2 else None,
        "sharpe": sharpe_ratio(returns, config["risk_free_rate"]),
        "sortino": sortino_ratio(returns, config["risk_free_rate"]),
        "max_drawdown": worst_drawdown,
        "calmar": calmar_ratio(annual_return, worst_drawdown),
        "hit_rate": wins / (wins + losses) if wins + losses > 0 else None,
        "best_day": max(returns),
        "worst_day": min(returns),
        "average_gross": sum(row["gross"] for row in curve) / len(curve),
        "average_net": sum(row["net"] for row in curve) / len(curve),
        "average_holdings": sum(row["holdings"] for row in curve) / len(curve),
        "turnover": stats["traded_notional"] / (sum(navs) / len(navs)) / (days / TRADING_DAYS),
        "trades": stats["trades"],
        "forced_exits": stats["forced_exits"],
        "stop_losses": stats["stop_losses"],
        "commissions": stats["commissions"],
        "slippage": stats["slippage"],
        "borrow_fees": stats["borrow_fees"],
        "interest": stats["interest"],
    }


__all__ = ["compute_metrics", "max_drawdown", "monthly_returns", "sharpe_ratio", "sortino_ratio",
           "yearly_returns"]
