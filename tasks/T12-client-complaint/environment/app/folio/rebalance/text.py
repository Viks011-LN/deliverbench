"""Text output for the drift and propose commands.

As in report/text_report.py, rendering only formats: every number comes from
drift.py, engine.py or effect.py and is rounded here with the [report]
settings. Weights, bands and drift all use report.percent_places, so a drift
can print as +0.5% against a band of 0.5% and still be outside it; the
Status column, worked out on exact values, is what counts.

Targets are listed in drift order (largest drift first, cash last), and the
weights after a proposal keep the order of the drift it started from, so the
two tables can be read side by side.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from folio.calc.valuation import Valuation
from folio.config.settings import ReportSettings
from folio.domain.money import quantize
from folio.rebalance.drift import Drift, outside_band
from folio.rebalance.effect import Effect
from folio.rebalance.engine import BUY, SELL, Proposal
from folio.report.tables import Column, format_money, format_pct, format_quantity, render_table
from folio.report.text_report import header

OUTSIDE = "outside"


def render_drift(valuation: Valuation, drifts: Sequence[Drift], settings: ReportSettings) -> str:
    """Table for ``drift``: every target with its current and model weight, band and drift."""
    pct = settings.percent_places
    columns = [Column("Target"), Column("Scope"), Column("Holdings", "right"), Column("Now", "right"),
               Column("Model", "right"), Column("Band", "right"), Column("Drift", "right"), Column("Status")]
    rows = [
        [drift.target.label, drift.target.scope, "" if drift.target.is_cash else str(len(drift.members)),
         format_pct(drift.current, pct), format_pct(drift.target.weight, pct), format_pct(drift.target.band, pct),
         format_pct(drift.drift, pct, signed=True), OUTSIDE if drift.outside else ""]
        for drift in drifts
    ]
    lines = header(valuation) + ["Drift from the model weights", render_table(columns, rows), "",
                                 band_summary(drifts)]
    return "\n".join(lines) + "\n"


def band_summary(drifts: Sequence[Drift]) -> str:
    count = len(outside_band(drifts))
    if not count:
        return "Every target is inside its band."
    return f"{count} of {len(drifts)} targets outside their band."


def render_proposal(proposal: Proposal, effect: Effect, settings: ReportSettings) -> str:
    """Report for ``propose``: the trades, what was left out, cash and weights after."""
    valuation, rules = proposal.valuation, proposal.rules
    base, places, pct = valuation.base_currency, settings.money_places, settings.percent_places
    lines = header(valuation) + [
        f"Proposed trades (minimum ticket {base} {format_money(rules.min_ticket.amount, places)}, "
        f"cash buffer {format_pct(rules.cash_buffer, pct)} of NAV)"]
    if proposal.trades:
        sold, bought = proposal.total(SELL).amount, proposal.total(BUY).amount
        lines += [_trade_table(proposal, places, pct), "",
                  f"Sells {base} {format_money(sold, places)}, buys {base} {format_money(bought, places)}, "
                  f"net cash {_signed_money(sold - bought, places)}; "
                  f"{format_pct(proposal.traded_share, pct)} of NAV traded."]
    elif outside_band(proposal.before):
        lines.append("No trades: the dealing rules left out every trade the targets asked for.")
    else:
        lines.append("No trades: every target is inside its band.")
    if proposal.buy_scale is not None:
        lines.append(f"Buys cut to {format_pct(proposal.buy_scale, pct)} of their size to keep "
                     f"{format_pct(rules.cash_buffer, pct)} of NAV in cash.")
    if proposal.skipped:
        lines += ["", "Left out", _skipped_table(proposal, places)]

    lines += ["", "Cash after the trades", _cash_table(effect, places),
              f"Cash after: {format_pct(effect.cash_weight, pct)} of NAV (model "
              f"{format_pct(proposal.targets.cash.weight, pct)}, buffer {format_pct(rules.cash_buffer, pct)})."]
    for currency in effect.short_currencies:
        lines.append(f"{currency} ends below zero: buy it against another currency before the trades settle.")
    lines += ["", "Weights after the trades", _after_table(proposal, effect, pct), "", band_summary(effect.after)]
    return "\n".join(lines) + "\n"


def _trade_table(proposal: Proposal, places: int, pct: int) -> str:
    columns = [Column("Side"), Column("Instrument"), Column("Kind"), Column("Ccy"), Column("Quantity", "right"),
               Column("Price", "right"), Column(f"Value ({proposal.valuation.base_currency})", "right"),
               Column("Before", "right"), Column("After", "right"), Column("Target")]
    rows = [
        [trade.side, trade.instrument.id, trade.instrument.kind, trade.instrument.currency,
         format_quantity(trade.quantity), str(trade.price), format_money(trade.base_value.amount, places),
         format_pct(trade.weight_before, pct), format_pct(trade.weight_after, pct), trade.target.label]
        for trade in proposal.trades
    ]
    return render_table(columns, rows)


def _skipped_table(proposal: Proposal, places: int) -> str:
    columns = [Column("Instrument"), Column("Side"), Column("Quantity", "right"),
               Column(f"Value ({proposal.valuation.base_currency})", "right"), Column("Target"), Column("Reason")]
    rows = [
        [item.instrument.id, item.side, format_quantity(item.quantity) if item.quantity else "",
         format_money(item.base_value.amount, places), item.target.label, item.reason]
        for item in proposal.skipped
    ]
    return render_table(columns, rows)


def _cash_table(effect: Effect, places: int) -> str:
    columns = [Column("Currency"), Column("Now", "right"), Column("Sells", "right"), Column("Buys", "right"),
               Column("After", "right"), Column(f"After ({effect.base_currency})", "right")]
    rows = [
        [move.currency, format_money(move.before.amount, places), format_money(move.sold.amount, places),
         format_money(move.bought.amount, places), format_money(move.after.amount, places),
         format_money(move.after.amount * move.fx_rate, places)]
        for move in effect.cash
    ]
    total = ["Total", "", "", "", "", format_money(effect.cash_after.amount, places)]
    return render_table(columns, rows, total)


def _after_table(proposal: Proposal, effect: Effect, pct: int) -> str:
    after = {(drift.target.scope, drift.target.key): drift for drift in effect.after}
    columns = [Column("Target"), Column("Scope"), Column("Before", "right"), Column("After", "right"),
               Column("Model", "right"), Column("Band", "right"), Column("Drift", "right"), Column("Status")]
    rows = []
    for before in proposal.before:
        target = before.target
        now = after[(target.scope, target.key)]
        rows.append([target.label, target.scope, format_pct(before.current, pct), format_pct(now.current, pct),
                     format_pct(target.weight, pct), format_pct(target.band, pct),
                     format_pct(now.drift, pct, signed=True), OUTSIDE if now.outside else ""])
    return render_table(columns, rows)


def _signed_money(amount: Decimal, places: int) -> str:
    rounded = quantize(amount, places)
    return ("+" if rounded > 0 else "") + format_money(rounded, places)
