"""The daily equity curve, written as CSV with --equity."""
from bt.constants import EQUITY_COLUMNS


def equity_line(row):
    """One row of the curve, every number written in full (repr), so nothing is lost to rounding."""
    return f"{row['date']},{row['nav']!r},{row['cash']!r},{row['gross']!r},{row['net']!r}\n"


def write_equity_curve(path, curve):
    """Write the curve: a header, then one line per day."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write(",".join(EQUITY_COLUMNS) + "\n")
        for row in curve:
            handle.write(equity_line(row))
