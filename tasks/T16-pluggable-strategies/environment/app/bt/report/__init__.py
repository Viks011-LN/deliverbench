"""The outputs: the JSON report (json_report.py), the equity curve (equity.py), the trade log (trades.py), the
text summary (summary.py, with formatting.py and calendar_grid.py) and the HTML page (html.py)."""
from bt.report.equity import write_equity_curve
from bt.report.html import render_html
from bt.report.json_report import build_report
from bt.report.summary import render_summary
from bt.report.trades import write_trade_log

__all__ = ["build_report", "render_html", "render_summary", "write_equity_curve", "write_trade_log"]
