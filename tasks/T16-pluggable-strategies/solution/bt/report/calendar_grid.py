"""The monthly returns as a calendar grid, for the text summary: one row per year, one column per month, and the
year's return at the end. A month the run does not cover is left blank."""

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def cell(value):
    """A return as a percentage with one decimal, seven characters wide."""
    return f"{value * 100:>6.1f}%"


def monthly_grid(monthly, yearly):
    """The grid's lines, header first."""
    lines = ["Year" + "".join(f"{month:>7}" for month in MONTHS) + f"{'Year':>9}"]
    for year in yearly:
        cells = []
        for month in range(1, 13):
            key = f"{year}-{month:02d}"
            cells.append(cell(monthly[key]) if key in monthly else " " * 7)
        lines.append(year + "".join(cells) + "  " + cell(yearly[year]))
    return lines
