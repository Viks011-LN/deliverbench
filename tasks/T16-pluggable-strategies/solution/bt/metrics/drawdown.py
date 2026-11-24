"""The worst drawdown of a run (the drawdown control during a run is bt/portfolio/drawdown.py)."""


def max_drawdown(navs):
    """The worst fall from a previous high, as a negative fraction (0.0 if the NAV never fell)."""
    peak = navs[0]
    worst = 0.0
    for nav in navs:
        if nav > peak:
            peak = nav
        fall = nav / peak - 1.0
        if fall < worst:
            worst = fall
    return worst
