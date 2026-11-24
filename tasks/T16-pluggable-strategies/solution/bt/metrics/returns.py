"""Daily returns of the NAV, and the plain statistics the metrics use."""
import math


def daily_returns(curve):
    """Day-on-day returns of the NAV (one fewer than the days of the curve)."""
    returns = []
    for i in range(1, len(curve)):
        returns.append(curve[i]["nav"] / curve[i - 1]["nav"] - 1.0)
    return returns


def mean(values):
    """Arithmetic mean, added up left to right."""
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def sample_std(values):
    """Sample standard deviation (n - 1 in the denominator)."""
    m = mean(values)
    total = 0.0
    for value in values:
        total += (value - m) * (value - m)
    return math.sqrt(total / (len(values) - 1))


def wins_and_losses(returns):
    """(days up, days down); a flat day is neither."""
    wins = 0
    losses = 0
    for r in returns:
        if r > 0.0:
            wins += 1
        elif r < 0.0:
            losses += 1
    return wins, losses
