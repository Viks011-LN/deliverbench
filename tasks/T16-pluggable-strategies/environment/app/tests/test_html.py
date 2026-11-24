"""The HTML report (--format html)."""
from conftest import DATA, run_cli

from bt.config import DEFAULTS
from bt.report.html import CHART_HEIGHT, chart_points, drawdown_list, render_html, table

CURVE = [
    {"date": "2026-01-05", "nav": 100.0, "cash": 100.0, "gross": 0.0, "net": 0.0, "holdings": 0},
    {"date": "2026-01-06", "nav": 110.0, "cash": 50.0, "gross": 0.5, "net": 0.5, "holdings": 1},
    {"date": "2026-01-07", "nav": 105.0, "cash": 50.0, "gross": 0.5, "net": 0.5, "holdings": 1},
]
METRICS = {"total_return": 0.05, "annual_return": 0.2, "annual_volatility": 0.1, "sharpe": 2.0, "sortino": 3.0,
           "max_drawdown": -0.045, "calmar": 4.4, "hit_rate": 0.5, "trades": 1}


def test_the_chart_spans_the_box():
    points = chart_points(CURVE).split()
    assert points[0] == f"0.0,{CHART_HEIGHT:.1f}"
    assert points[1] == "320.0,0.0"
    assert points[2] == "640.0,100.0"


def test_a_flat_curve_lies_on_the_bottom():
    flat = [dict(row, nav=100.0) for row in CURVE]
    assert {p.split(",")[1] for p in chart_points(flat).split()} == {f"{CHART_HEIGHT:.1f}"}


def test_table_escapes_its_text():
    assert table([("A & B", "<1%")]) == "<table><tr><td>A &amp; B</td><td>&lt;1%</td></tr></table>"


def test_drawdown_list():
    assert drawdown_list(CURVE) == "<ul><li>-4.55%: 2026-01-06 to 2026-01-07, not recovered</li></ul>"
    assert drawdown_list(CURVE[:1]) == "<ul><li>none</li></ul>"


def test_the_page_names_the_strategy():
    config = dict(DEFAULTS, signal={"type": "reversion", "window": 12, "entry_z": 0.75})
    page = render_html(["2026-01-05", "2026-01-06", "2026-01-07"], config, {"curve": CURVE}, METRICS)
    assert page.startswith("<!DOCTYPE html>\n")
    assert page.endswith("</body></html>\n")
    assert "<p>Strategy: reversion (window 12, entry_z 0.75)<br>" in page
    assert "<h1>Backtest 2026-01-05 to 2026-01-07 (3 days)</h1>" in page


def test_html_from_the_command_line():
    proc = run_cli("--prices", str(DATA / "prices.csv"), "--config", str(DATA / "momentum.json"), "--format", "html")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("<table>") == 2
    assert "<td>Benchmark IDX</td>" in proc.stdout
