"""How the text summary writes numbers. The JSON report and the equity curve write every number in full."""


def percent(value):
    """A fraction as a percentage with two decimals ("12.34%"); "n/a" for None."""
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def ratio(value):
    """A ratio with two decimals; "n/a" for None."""
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def money(value):
    """An amount with thousands separators and two decimals."""
    return f"{value:,.2f}"


def row(label, value):
    """One line of the summary's table: the label left, the value right."""
    return f"{label:<20}{value:>18}"
