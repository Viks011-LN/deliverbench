"""Text output for folio.compliance: VIOLATION lines, the headroom table, the mandate and the restricted list.

As in folio's report/text_report.py, rendering never changes a number; it
only formats with folio's [report] settings. VIOLATION lines have the shape
of folio's BREACH lines, so one grep finds both, but use the client's word:

    VIOLATION issuer_max_share ADZM: 7.4% > 7.0%
    VIOLATION govt_min_share government bonds: 14.2% < 15.0%
    VIOLATION max_positions positions: 42 > 40
    VIOLATION restricted_holdings TNSL: 0.9% held, restricted since 2026-10-01 (...)

Like the comparisons themselves, the lines are about exact values: a share
just over its limit can print as "7.0% > 7.0%" at one decimal place.
"""

from __future__ import annotations

from decimal import Decimal

from folio.calc.valuation import Valuation
from folio.compliance.checker import ComplianceResult, Headroom
from folio.compliance.guideline import MAX_COUNT, MIN_SHARE, NONE_HELD, Reading
from folio.compliance.mandate import Mandate
from folio.compliance.registry import guideline_class
from folio.compliance.restricted import RestrictedHolding
from folio.compliance.restricted_list import RestrictedList
from folio.config.settings import ReportSettings
from folio.report.tables import Column, clip, format_money, format_pct, format_quantity, render_table
from folio.report.text_report import header

NAME_WIDTH = 30


def format_figure(value: Decimal, kind: str, places: int = 1) -> str:
    """A count as a whole number, anything else as a percentage of NAV."""
    if kind == MAX_COUNT:
        return format_quantity(value)
    return format_pct(value, places)


def format_limit(kind: str, limit: Decimal, places: int = 1) -> str:
    """``max 7.0%``, ``min 15.0%``, ``max 40`` or ``none held``."""
    if kind == NONE_HELD:
        return "none held"
    word = "min" if kind == MIN_SHARE else "max"
    return f"{word} {format_figure(limit, kind, places)}"


def format_violation(reading: Reading, places: int = 1) -> str:
    """One VIOLATION line for a reading that violates its guideline."""
    actual = format_figure(reading.actual, reading.kind, places)
    if reading.kind == NONE_HELD:
        body = f"{actual} held"
    else:
        sign = "<" if reading.kind == MIN_SHARE else ">"
        body = f"{actual} {sign} {format_figure(reading.limit, reading.kind, places)}"
    if reading.detail:
        body += f", {reading.detail}"
    return f"VIOLATION {reading.guideline} {reading.subject}: {body}"


def render_check(result: ComplianceResult, settings: ReportSettings, explain: bool = False) -> str:
    """Output of ``check``: the violations, the headroom table with ``explain``, then OK if all passed."""
    lines = [format_violation(reading, settings.percent_places) for reading in result.violations]
    if explain:
        if lines:
            lines.append("")
        lines += ["Headroom (tightest subject of each guideline)",
                  render_headroom(result.headroom, result.nav.currency, settings)]
    if result.ok:
        if explain:
            lines.append("")
        count = len(result.checked)
        lines.append(f"OK: {count} guideline{'' if count == 1 else 's'} checked")
    return "\n".join(lines) + "\n"


def render_headroom(headroom: tuple[Headroom, ...], currency: str, settings: ReportSettings) -> str:
    """One row per guideline: its tightest subject, the limit and how far it is from it."""
    pct, places = settings.percent_places, settings.money_places
    columns = [Column("Guideline"), Column("Tightest"), Column("Actual", "right"), Column("Limit", "right"),
               Column("Headroom", "right"), Column(f"In {currency}", "right")]
    rows = []
    for entry in headroom:
        limit = format_limit(entry.kind, entry.limit, pct)
        reading = entry.tightest
        if reading is None:
            rows.append([entry.guideline, entry.remark, "", limit, "", ""])
            continue
        amount = "" if entry.amount is None else format_money(entry.amount.amount, places)
        rows.append([entry.guideline, clip(reading.subject, NAME_WIDTH),
                     format_figure(reading.actual, entry.kind, pct), limit,
                     format_figure(reading.headroom, entry.kind, pct), amount])
    return render_table(columns, rows)


def render_mandate(mandate: Mandate, portfolio_name: str, settings: ReportSettings) -> str:
    """Output of ``mandate``: who the mandate is for, then one row per guideline it lists."""
    lines = [
        f"Mandate for {portfolio_name} ({mandate.portfolio})",
        f"Client: {mandate.client}",
        f"From {mandate.source}: {len(mandate.terms)} guidelines, {len(mandate.enabled_terms)} in force",
        "",
    ]
    columns = [Column("Guideline"), Column("Covers"), Column("Limit", "right"), Column("Status"), Column("Note")]
    rows = []
    for term in mandate.terms:
        limit = format_limit(term.kind, term.value if term.value is not None else Decimal(0), settings.percent_places)
        rows.append([term.key, guideline_class(term.key).title, limit, "in force" if term.enabled else "off",
                     term.note])
    lines.append(render_table(columns, rows))
    return "\n".join(lines) + "\n"


def render_restricted(valuation: Valuation, held: list[RestrictedHolding], coming: list[RestrictedHolding],
                      restricted: RestrictedList, settings: ReportSettings) -> str:
    """Output of ``restricted``: holdings restricted on the valuation date, then those about to be."""
    as_of, pct = valuation.as_of, settings.percent_places
    lines = header(valuation) + ["Restricted holdings"]
    lines.append(_holdings_table(held, pct) if held else "None.")
    if coming:
        lines += ["", "Coming onto the list", _holdings_table(coming, pct)]
    counts = (f"{len(restricted.in_force(as_of))} in force, {len(restricted.lifted(as_of))} lifted, "
              f"{len(restricted.not_yet(as_of))} not yet in force")
    lines += ["", f"{restricted.source} on {as_of}: {len(restricted)} entries, {counts}"]
    return "\n".join(lines) + "\n"


def _holdings_table(holdings: list[RestrictedHolding], places: int) -> str:
    columns = [Column("Instrument"), Column("Name"), Column("Weight", "right"), Column("Listed as"),
               Column("From"), Column("Reason")]
    rows = [
        [holding.position.instrument.id, clip(holding.position.instrument.name, NAME_WIDTH),
         format_pct(holding.position.weight, places), holding.restriction.describe(),
         holding.restriction.start.isoformat(), holding.restriction.reason]
        for holding in holdings
    ]
    return render_table(columns, rows)
