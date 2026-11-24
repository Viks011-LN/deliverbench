"""Text output for the value, report and risk commands.

Each renderer returns one string for the CLI to print. Rendering never
changes a number, it only formats it with the [report] settings; anything
that needs calculating belongs in calc/ or aggregate/.
"""

from __future__ import annotations

import math
from decimal import Decimal

from folio.aggregate.attribution import CASH_KEY, Contribution, total_return
from folio.aggregate.rollup import top_n
from folio.calc import bonds, exposure, fees
from folio.calc.exposure import Breakdown
from folio.calc.risk import RiskSummary, TailLoss, VolShares, confidence_label
from folio.calc.valuation import Valuation
from folio.config.settings import ReportSettings, Settings
from folio.report.tables import (
    Column,
    bucket,
    clip,
    format_money,
    format_pct,
    format_quantity,
    histogram_lines,
    render_table,
)

NAME_WIDTH = 30
MAX_HISTOGRAM_BINS = 24
VALUATION_ORDERS = ("instrument", "weight")


def header(valuation: Valuation) -> list[str]:
    return [
        f"{valuation.portfolio_name} ({valuation.portfolio_code})",
        f"Valued {valuation.as_of.isoformat()} in {valuation.base_currency}",
        "",
    ]


def render_valuation(valuation: Valuation, settings: ReportSettings, order: str = "instrument") -> str:
    """Holdings table for ``folio value``: one row per position, then cash, then NAV.

    ``order`` is "instrument" (id order) or "weight" (largest first, ties by id).
    """
    if order not in VALUATION_ORDERS:
        raise ValueError(f"unknown order {order!r}; expected one of {', '.join(VALUATION_ORDERS)}")
    places, pct = settings.money_places, settings.percent_places
    lines_in_order = list(valuation.positions)
    if order == "weight":
        lines_in_order.sort(key=lambda line: (-line.weight, line.instrument.id))
    columns = [
        Column("Instrument"),
        Column("Name"),
        Column("Kind"),
        Column("Ccy"),
        Column("Quantity", "right"),
        Column("Price", "right"),
        Column(f"Value ({valuation.base_currency})", "right"),
        Column("Weight", "right"),
        Column("On cost", "right"),
    ]
    rows = []
    for line in lines_in_order:
        on_cost = line.unrealised_pct
        rows.append([
            line.instrument.id,
            clip(line.instrument.name, NAME_WIDTH),
            line.instrument.kind,
            line.instrument.currency,
            format_quantity(line.quantity),
            f"{line.price}{'*' if line.stale else ''}",
            format_money(line.base_value.amount, places),
            format_pct(line.weight, pct),
            "" if on_cost is None else format_pct(on_cost, pct, signed=True),
        ])
    for cash in valuation.cash:
        currency = cash.local_value.currency
        rows.append(["CASH", f"Cash {currency}", "cash", currency, "", "",
                     format_money(cash.base_value.amount, places), format_pct(cash.weight, pct), ""])
    total = ["Total", "", "", "", "", "", format_money(valuation.nav.amount, places), format_pct(Decimal(1), pct), ""]

    lines = header(valuation) + [render_table(columns, rows, total), ""]
    yearly = fees.total_fund_cost(valuation)
    if not yearly.is_zero():
        base = valuation.base_currency
        lines.append(
            f"Fund running costs (est.): {base} {format_money(yearly.amount, places)} a year "
            f"({format_pct(fees.cost_ratio(valuation), pct + 1)} of NAV), "
            f"{base} {format_money(fees.year_to_date(valuation).amount, places)} so far this year"
        )
    stale = valuation.stale_positions()
    if stale:
        lines.append(f"* price older than {settings.stale_price_days} business days: "
                     + ", ".join(f"{line.instrument.id} ({line.price_date})" for line in stale))
    return "\n".join(lines).rstrip() + "\n"


def render_breakdown(valuation: Valuation, breakdown: Breakdown, settings: ReportSettings,
                     contributions: dict[str, Contribution] | None = None) -> str:
    """Exposure table for ``folio report --by ...``, optionally with return contributions."""
    places, pct = settings.money_places, settings.percent_places
    columns = [
        Column(breakdown.dimension.title),
        Column("Positions", "right"),
        Column("Market value", "right"),
        Column("Weight", "right"),
    ]
    if contributions is not None:
        columns.append(Column("Contrib", "right"))

    def contrib(key: str) -> list[str]:
        if contributions is None:
            return []
        part = contributions.get(key)
        # TODO: rows folded into "Other" by report.top_n get no contribution yet.
        return ["" if part is None else format_pct(part.contribution, pct + 1, signed=True)]

    rows = []
    shown_value = Decimal(0)
    for row in breakdown.rows:
        rows.append([row.key, str(row.positions), format_money(row.value.amount, places),
                     format_pct(row.share, pct)] + contrib(row.key))
        shown_value += row.value.amount
    if settings.show_cash and not breakdown.cash.is_zero():
        cash_share = breakdown.cash.amount / breakdown.nav.amount
        rows.append(["Cash", "", format_money(breakdown.cash.amount, places), format_pct(cash_share, pct)]
                    + contrib(CASH_KEY))
        shown_value += breakdown.cash.amount

    total = ["Total", str(breakdown.positions), format_money(shown_value, places),
             format_pct(shown_value / breakdown.nav.amount, pct)]
    if contributions is not None:
        total.append(format_pct(total_return(contributions), pct + 1, signed=True))

    lines = header(valuation) + [f"Exposure by {breakdown.dimension.name}", render_table(columns, rows, total)]
    return "\n".join(lines) + "\n"


def render_vol_shares(valuation: Valuation, shares: VolShares, settings: ReportSettings) -> str:
    """Shares of volatility for ``folio report --by risk``: by holding, then by sector.

    Holdings come largest share first (ties by id), as `folio value --sort weight` orders weights; the sector
    table is a breakdown like ``folio report --by sector`` (report.top_n and report.show_cash apply).
    """
    pct = settings.percent_places
    holdings = sorted(zip(valuation.positions, shares.positions),
                      key=lambda pair: (-pair[1], pair[0].instrument.id))
    columns = [Column("Instrument"), Column("Name"), Column("Sector"), Column("Weight", "right"),
               Column("Vol share", "right")]
    rows = [[line.instrument.id, clip(line.instrument.name, NAME_WIDTH), line.instrument.sector,
             format_pct(line.weight, pct), format_pct(share, pct)] for line, share in holdings]
    cash_weight = valuation.cash_total.amount / valuation.nav.amount
    shown_weight = sum((line.weight for line in valuation.positions), Decimal(0))
    shown_share = math.fsum(shares.positions)
    if settings.show_cash and valuation.cash:
        rows.append(["Cash", "", "", format_pct(cash_weight, pct), format_pct(shares.cash_total, pct)])
        shown_weight += cash_weight
        shown_share += shares.cash_total
    total = ["Total", "", "", format_pct(shown_weight, pct), format_pct(shown_share, pct)]
    window = f"{shares.observations} daily returns, {shares.start} to {shares.end}"
    lines = header(valuation) + [f"Share of volatility by holding ({window})", render_table(columns, rows, total)]

    weights = {row.key: row.share for row in exposure.by_sector(valuation).rows}
    groups = top_n(shares.by_group(valuation, exposure.SECTOR.key), settings.top_n)
    columns = [Column("Sector"), Column("Positions", "right"), Column("Weight", "right"),
               Column("Vol share", "right")]
    rows = []
    for group in groups:
        weight = weights.get(group.key)
        if weight is None:  # folded into "Other" by report.top_n
            weight = sum((line.weight for line, _ in group.members), Decimal(0))
        rows.append([group.key, str(group.count), format_pct(weight, pct), format_pct(group.total, pct)])
    if settings.show_cash and valuation.cash:
        rows.append(["Cash", "", format_pct(cash_weight, pct), format_pct(shares.cash_total, pct)])
    total = ["Total", str(len(valuation.positions)), format_pct(shown_weight, pct), format_pct(shown_share, pct)]
    lines += ["", "Share of volatility by sector", render_table(columns, rows, total)]
    return "\n".join(lines) + "\n"


def render_risk(valuation: Valuation, summary: RiskSummary, settings: Settings, histogram: bool = False,
                tail: tuple[str, list[TailLoss]] | None = None) -> str:
    """Risk summary for ``folio risk``.

    Optionally followed by a histogram of the daily returns and by ``tail``,
    a (column title, tail_losses()) pair splitting expected shortfall by group.
    """
    places, pct = settings.report.money_places, settings.report.percent_places
    base = valuation.base_currency
    level = f"{confidence_label(summary.confidence)} {summary.horizon_days}d"
    pairs = [
        ("Window", f"{summary.start} to {summary.end}, {summary.observations} daily returns"),
        ("Volatility (ann.)", format_pct(summary.volatility, pct)),
        (f"VaR {level}", f"{format_pct(summary.var, pct)}  {base} {format_money(summary.var_amount.amount, places)}"),
        (f"ES {level}", f"{format_pct(summary.expected_shortfall, pct)}  "
                        f"{base} {format_money(summary.es_amount.amount, places)}"),
        ("Return", f"{format_pct(summary.period_return, pct, signed=True)}  "
                   f"({format_pct(summary.annualised_return, pct, signed=True)} annualised)"),
    ]
    if summary.drawdown is not None:
        drawdown = summary.drawdown
        recovered = f", recovered {drawdown.recovered}" if drawdown.recovered else ", not recovered"
        pairs.append(("Max drawdown",
                      f"{format_pct(drawdown.depth, pct)}  {drawdown.peak} to {drawdown.trough}{recovered}"))
    pairs.append(("Worst day", f"{format_pct(summary.worst_day[1], pct, signed=True)}  {summary.worst_day[0]}"))
    pairs.append(("Best day", f"{format_pct(summary.best_day[1], pct, signed=True)}  {summary.best_day[0]}"))
    duration = bonds.duration_summary(valuation)
    if duration is not None:
        on_bonds, on_nav, bond_share = duration
        pairs.append(("Duration (mod.)", f"{on_bonds:.2f} on bonds ({format_pct(bond_share, pct)} of NAV), "
                                         f"{on_nav:.2f} on NAV"))

    width = max(len(label) for label, _ in pairs)
    lines = header(valuation) + [f"{label.ljust(width)}  {value}" for label, value in pairs]
    if histogram:
        edges = histogram_edges(summary.returns, settings.risk.histogram_step)
        bins = bucket(summary.returns, edges, label=lambda edge: format_pct(edge, pct))
        lines += ["", f"Daily returns ({summary.observations})"] + histogram_lines(bins)
    if tail is not None:
        title, losses = tail
        rows = [[loss.key, format_pct(loss.loss, pct + 1), format_pct(loss.share, pct)] for loss in losses]
        total = ["Total", format_pct(sum(loss.loss for loss in losses), pct + 1), format_pct(1.0, pct)]
        columns = [Column(title), Column("Tail loss", "right"), Column("Share", "right")]
        lines += ["", f"Expected shortfall {confidence_label(summary.confidence)} 1d by {title.lower()}",
                  render_table(columns, rows, total)]
    return "\n".join(lines) + "\n"


def histogram_edges(returns: tuple[float, ...], step: float) -> list[float]:
    """Edges at multiples of ``step``, symmetric around zero, wide enough for every return.

    Capped at MAX_HISTOGRAM_BINS so one wild day does not draw a page of empty bins;
    the open end bins catch whatever falls outside.
    """
    reach = max((abs(value) for value in returns), default=step)
    half = min(max(math.ceil(reach / step), 1), MAX_HISTOGRAM_BINS // 2)
    return [round(index * step, 10) for index in range(-half, half + 1)]
