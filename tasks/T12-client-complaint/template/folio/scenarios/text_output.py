"""Text output for ``python -m folio.scenarios``: the list, run and compare commands.

As in report/text_report.py, rendering only formats; every number comes
from engine.py or grouping.py. Amounts use report.money_places. Shares of
NAV get one decimal place more than report.percent_places, as return
contributions do, because the gap between a 0.4% and a 0.45% loss matters
when scenarios are set side by side.
"""

from __future__ import annotations

import textwrap
from typing import Sequence

from folio.calc.valuation import Valuation
from folio.config.settings import ReportSettings
from folio.report.tables import Column, format_money, format_pct, render_table
from folio.report.text_report import header
from folio.scenarios.engine import ScenarioResult
from folio.scenarios.grouping import GroupPnl, StressBreakdown
from folio.scenarios.shocks import Scenario

WIDTH = 100  # long lines of shocks wrap here
INDENT = "  "


def render_list(scenarios: Sequence[Scenario], source: str) -> str:
    """Every scenario with its description, in name order.

    A scenario without a description shows its shocks instead, so no row is blank.
    """
    columns = [Column("Scenario"), Column("Description")]
    rows = [[scenario.name, scenario.description or ", ".join(scenario.shock_summary())]
            for scenario in scenarios]
    plural = "" if len(scenarios) == 1 else "s"
    lines = [f"{len(scenarios)} scenario{plural} in {source}", "", render_table(columns, rows)]
    return "\n".join(lines) + "\n"


def render_run(result: ScenarioResult, breakdown: StressBreakdown, settings: ReportSettings) -> str:
    """One scenario: what it does, its P&L per group and in total, and NAV afterwards."""
    valuation = result.valuation
    places, pct = settings.money_places, settings.percent_places + 1
    base = valuation.base_currency
    scenario = result.scenario
    title = f"Scenario {scenario.name}" + (f": {scenario.description}" if scenario.description else "")
    lines = header(valuation) + _wrap(title) + _wrap(f"Shocks: {shock_text(result)}") + [""]

    columns = [
        Column(breakdown.dimension.title),
        Column("Positions", "right"),
        Column(f"Value ({base})", "right"),
        Column("Stressed", "right"),
        Column("P&L", "right"),
        Column("Of NAV", "right"),
    ]
    rows = [_group_cells(row, places, pct) for row in breakdown.rows]
    if breakdown.cash is not None:
        rows.append(_group_cells(breakdown.cash, places, pct, positions=""))
    total = _group_cells(breakdown.total, places, pct)
    lines += [f"P&L by {breakdown.dimension.name}", render_table(columns, rows, total), ""]
    lines.append(f"NAV after the scenario: {base} {format_money(result.stressed_nav.amount, places)} "
                 f"({format_pct(result.pnl_share, pct, signed=True)})")
    return "\n".join(lines) + "\n"


def render_compare(valuation: Valuation, results: Sequence[ScenarioResult], settings: ReportSettings) -> str:
    """Every scenario's total P&L, worst first, ties by name, with the line that loses most in each."""
    places, pct = settings.money_places, settings.percent_places + 1
    base = valuation.base_currency
    columns = [
        Column("Scenario"),
        Column(f"P&L ({base})", "right"),
        Column("Of NAV", "right"),
        Column("NAV after", "right"),
        Column("Largest loss"),
    ]
    rows = []
    for result in sorted(results, key=lambda result: (result.pnl.amount, result.scenario.name)):
        worst = result.worst_position()
        rows.append([
            result.scenario.name,
            format_money(result.pnl.amount, places),
            format_pct(result.pnl_share, pct, signed=True),
            format_money(result.stressed_nav.amount, places),
            "" if worst is None else f"{worst.line.instrument.id} {format_money(worst.pnl.amount, places)}",
        ])
    lines = header(valuation) + [
        f"Scenario P&L, worst first; NAV before {base} {format_money(valuation.nav.amount, places)}",
        render_table(columns, rows),
    ]
    return "\n".join(lines) + "\n"


def shock_text(result: ScenarioResult) -> str:
    """The shocks of a result in words; a historical replay also says which dates it used."""
    text = ", ".join(result.scenario.shock_summary())
    if result.window is not None:
        return f"{text}, {result.window}"
    if result.scenario.historical is not None:
        return f"{text}, each over its own dates (export lists them)"
    return text


def _group_cells(group: GroupPnl, places: int, pct: int, positions: str | None = None) -> list[str]:
    return [
        group.key,
        str(group.positions) if positions is None else positions,
        format_money(group.value.amount, places),
        format_money(group.stressed.amount, places),
        format_money(group.pnl.amount, places),
        format_pct(group.share, pct, signed=True),
    ]


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, WIDTH, subsequent_indent=INDENT, break_on_hyphens=False)
