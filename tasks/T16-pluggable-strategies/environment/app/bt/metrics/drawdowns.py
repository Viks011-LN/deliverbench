"""The drawdown periods of a run: from a high, down to the trough, and back to the high (or not yet).

A period starts at the last high before the NAV falls, its trough is the lowest NAV before it gets back to that
high, and it ends on the first day the NAV is at or above the high again (its recovery). A period still open on
the last day has no recovery. The report lists the worst ones (constants.WORST_DRAWDOWNS).
"""
from bt.constants import WORST_DRAWDOWNS


def period(curve, peak, trough, recovery):
    """One period, from the indices of its high, its trough and its recovery (None if it has not recovered)."""
    end = recovery if recovery is not None else len(curve) - 1
    return {
        "peak": curve[peak]["date"],
        "trough": curve[trough]["date"],
        "recovery": curve[recovery]["date"] if recovery is not None else None,
        "depth": curve[trough]["nav"] / curve[peak]["nav"] - 1.0,
        "days": end - peak,
    }


def drawdown_periods(curve):
    """Every drawdown period of the run, oldest first."""
    periods = []
    peak = 0
    trough = None
    for i in range(1, len(curve)):
        nav = curve[i]["nav"]
        if nav >= curve[peak]["nav"]:
            if trough is not None:
                periods.append(period(curve, peak, trough, i))
                trough = None
            peak = i
        elif trough is None or nav < curve[trough]["nav"]:
            trough = i
    if trough is not None:
        periods.append(period(curve, peak, trough, None))
    return periods


def worst_drawdowns(curve, count=WORST_DRAWDOWNS):
    """The `count` deepest periods, deepest first (an earlier high first between two of the same depth)."""
    return sorted(drawdown_periods(curve), key=lambda p: (p["depth"], p["peak"]))[:count]
