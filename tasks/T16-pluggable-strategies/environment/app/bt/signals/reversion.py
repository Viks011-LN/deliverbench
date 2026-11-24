"""Mean reversion: buy what is cheap against its own recent average, sell what is dear.

The score of a stock on day t is minus the z-score of its price against the moving average of the last
`window` prices (today's included): a stock far below its average scores high. Inside the entry band
(|z| < entry_z) the score is 0, which keeps the stock out of the book.
"""
from bt.signals.stats import rolling_mean, rolling_std, zscore

WINDOW = 20      # days
ENTRY_Z = 1      # standard deviations


def reversion_score(series, t, window, entry_z):
    """Minus the z-score of today's price against its moving average; 0 inside the entry band. None when the
    window is incomplete or the price did not move at all over it."""
    std = rolling_std(series, t, window)
    if std is None or std == 0.0:
        return None
    mean = rolling_mean(series, t, window)
    z = zscore(series[t], mean, std)
    if abs(z) < entry_z:
        return 0.0
    return -z
