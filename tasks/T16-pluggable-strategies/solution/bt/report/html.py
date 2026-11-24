"""The HTML report (--format html): the summary's content as one self-contained page, for e-mail.

It holds what the text summary holds (the run, the table, the worst drawdowns, the monthly returns), plus a chart
of the NAV drawn as an inline SVG line. Numbers are rounded as in the summary; the chart's points are rounded to
one decimal of a pixel. No scripts, no external files.
"""
from html import escape

from bt.metrics import monthly_returns, yearly_returns
from bt.metrics.drawdowns import worst_drawdowns
from bt.report.calendar_grid import MONTHS
from bt.report.formatting import money, percent, ratio
from bt.report.summary import book_line, risk_line, strategy_line

CHART_WIDTH = 640
CHART_HEIGHT = 200
STYLE = ("body{font-family:sans-serif;margin:24px}table{border-collapse:collapse}"
         "td,th{padding:2px 8px;text-align:right}td:first-child,th:first-child{text-align:left}"
         "polyline{fill:none;stroke:#1f4e79;stroke-width:1.5}")


def chart_points(curve):
    """The NAV as SVG points: x across the days, y from the lowest NAV (bottom) to the highest (top)."""
    navs = [row["nav"] for row in curve]
    low, high = min(navs), max(navs)
    span = high - low if high > low else 1.0
    step = CHART_WIDTH / (len(navs) - 1)
    points = []
    for i, nav in enumerate(navs):
        x = i * step
        y = CHART_HEIGHT - (nav - low) / span * CHART_HEIGHT
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def table(rows):
    """A two-column table of (label, value) rows."""
    cells = "".join(f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>" for label, value in rows)
    return f"<table>{cells}</table>"


def metric_rows(curve, metrics, benchmark):
    rows = [
        ("Total return", percent(metrics["total_return"])),
        ("Annual return", percent(metrics["annual_return"])),
        ("Annual volatility", percent(metrics["annual_volatility"])),
        ("Sharpe", ratio(metrics["sharpe"])),
        ("Sortino", ratio(metrics["sortino"])),
        ("Max drawdown", percent(metrics["max_drawdown"])),
        ("Hit rate", percent(metrics["hit_rate"])),
    ]
    if benchmark is not None:
        rows += [(f"Benchmark {benchmark['symbol']}", percent(benchmark["total_return"])),
                 ("Excess return", percent(benchmark["excess_return"])),
                 ("Beta", ratio(benchmark["beta"]))]
    rows += [("Trades", str(metrics["trades"])), ("Final NAV", money(curve[-1]["nav"]))]
    return rows


def monthly_table(curve):
    monthly, yearly = monthly_returns(curve), yearly_returns(curve)
    head = "<tr><th>Year</th>" + "".join(f"<th>{m}</th>" for m in MONTHS) + "<th>Year</th></tr>"
    body = ""
    for year in yearly:
        cells = "".join(f"<td>{percent(monthly[key]) if key in monthly else ''}</td>"
                        for key in (f"{year}-{month:02d}" for month in range(1, 13)))
        body += f"<tr><td>{year}</td>{cells}<td>{percent(yearly[year])}</td></tr>"
    return f"<table>{head}{body}</table>"


def drawdown_list(curve):
    items = []
    for p in worst_drawdowns(curve):
        ending = f"recovered {p['recovery']}" if p["recovery"] is not None else "not recovered"
        items.append(f"<li>{percent(p['depth'])}: {p['peak']} to {p['trough']}, {ending}</li>")
    return "<ul>" + ("".join(items) or "<li>none</li>") + "</ul>"


def render_html(dates, config, result, metrics, benchmark=None):
    """The page, ending with a newline."""
    curve = result["curve"]
    title = f"Backtest {dates[0]} to {dates[-1]}"
    parts = [
        "<!DOCTYPE html>",
        f"<html><head><meta charset=\"utf-8\"><title>{escape(title)}</title><style>{STYLE}</style></head><body>",
        f"<h1>{escape(title)} ({len(dates)} days)</h1>",
        f"<p>{escape(strategy_line(config['signal']))}<br>{escape(book_line(config))}<br>"
        f"{escape(risk_line(config))}</p>",
        f"<svg width=\"{CHART_WIDTH}\" height=\"{CHART_HEIGHT}\" viewBox=\"0 0 {CHART_WIDTH} {CHART_HEIGHT}\">"
        f"<polyline points=\"{chart_points(curve)}\"/></svg>",
        "<h2>Results</h2>",
        table(metric_rows(curve, metrics, benchmark)),
        "<h2>Worst drawdowns</h2>",
        drawdown_list(curve),
        "<h2>Monthly returns</h2>",
        monthly_table(curve),
        "</body></html>",
    ]
    return "\n".join(parts) + "\n"
