"""Returns per calendar month and per calendar year, compounded from the day-on-day NAV ratios."""
from bt.data.calendar import month_key, year_key


def period_returns(curve, key):
    """Return per period, where key(date) names a day's period. The first day's period starts at its NAV."""
    out = {}
    period = key(curve[0]["date"])
    growth = 1.0
    for i in range(1, len(curve)):
        name = key(curve[i]["date"])
        if name != period:
            out[period] = growth - 1.0
            period = name
            growth = 1.0
        growth *= curve[i]["nav"] / curve[i - 1]["nav"]
    out[period] = growth - 1.0
    return out


def monthly_returns(curve):
    """Return per calendar month ("YYYY-MM")."""
    return period_returns(curve, month_key)


def yearly_returns(curve):
    """Return per calendar year ("YYYY")."""
    return period_returns(curve, year_key)
