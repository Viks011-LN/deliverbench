"""Risk-adjusted ratios: Sharpe, Sortino and Calmar. Each is None where it is undefined."""
import math

from bt.metrics.returns import mean, sample_std

TRADING_DAYS = 252


def sharpe_ratio(returns, risk_free_rate):
    """Annualised Sharpe ratio of daily returns over the daily risk-free rate; None when it is undefined."""
    if len(returns) < 2:
        return None
    daily_rf = risk_free_rate / TRADING_DAYS
    excess = [r - daily_rf for r in returns]
    sd = sample_std(excess)
    if sd == 0.0:
        return None
    return mean(excess) / sd * math.sqrt(TRADING_DAYS)


def sortino_ratio(returns, risk_free_rate):
    """Annualised Sortino ratio: like Sharpe, but only days below the target count as risk. None when there are no
    such days."""
    if len(returns) < 2:
        return None
    target = risk_free_rate / TRADING_DAYS
    downside = 0.0
    for r in returns:
        if r < target:
            downside += (r - target) * (r - target)
    if downside == 0.0:
        return None
    downside_deviation = math.sqrt(downside / len(returns))
    return (mean(returns) - target) / downside_deviation * math.sqrt(TRADING_DAYS)


def calmar_ratio(annual_return, worst_drawdown):
    """Annual return over the worst drawdown; None if the NAV never fell."""
    if worst_drawdown < 0.0:
        return annual_return / -worst_drawdown
    return None
