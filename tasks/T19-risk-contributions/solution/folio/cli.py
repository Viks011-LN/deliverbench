"""Command-line interface: ``folio <command>`` or ``python -m folio <command>``.

Commands:
  value          holdings valued in the base currency, with NAV
  risk           volatility, historical VaR and expected shortfall
  report         exposure breakdown: --by sector, currency or kind; --by risk
                 gives each holding's and sector's share of volatility instead
  export         positions as CSV or JSON, with each one's share of volatility
  check-limits   run the limit rules; exit status 1 if any limit is breached

Common options, accepted before or after the command:
  --data-dir DIR    folder with instruments.csv, positions.json, prices.csv
                    and fx.csv (default: ./data)
  --as-of DATE      valuation date (default: today; a date after the last
                    price becomes the last price date)
  --config FILE     settings file to use instead of ./folio.toml
  --set KEY=VALUE   override one setting, e.g. limits.sector_max_share=0.3;
                    may be repeated

Exit status: 0 success, 1 a limit is breached (check-limits only),
2 bad input, bad settings or bad usage.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from folio import __version__
from folio.aggregate.attribution import contributions
from folio.calc import exposure
from folio.calc.returns import nav_series
from folio.calc.risk import RiskSummary, VolShares, summarise_risk, tail_losses, vol_shares
from folio.calc.valuation import Valuation, resolve_as_of, value_portfolio
from folio.config.loader import load_settings
from folio.config.settings import Settings
from folio.data.business_days import parse_date
from folio.data.folder import DataFolder, load_folder
from folio.errors import DataError, FolioError, RiskError, ValuationError
from folio.limits.checker import build_rules, needs_risk, needs_vol_shares, run_checks
from folio.report import csv_export, json_export, text_report

EXIT_OK = 0
EXIT_BREACH = 1
EXIT_ERROR = 2

REPORT_DIMENSIONS = ("sector", "currency", "kind")
RISK_REPORT = "risk"  # report --by risk: shares of volatility, not a breakdown of NAV
EXPORT_WRITERS = {"csv": csv_export.write_csv, "json": json_export.write_json}


@dataclass
class Context:
    """Settings and data for one run, loaded once and shared by the commands."""

    settings: Settings
    data: DataFolder
    as_of: date
    notes: list[str] = field(default_factory=list)
    _valuation: Valuation | None = None
    _vol_shares: VolShares | None = None

    def valuation(self) -> Valuation:
        if self._valuation is None:
            self._valuation = value_portfolio(
                self.data.portfolio,
                self.data.universe,
                self.data.prices,
                self.data.fx,
                self.as_of,
                base_currency=self.settings.fx.base_currency,
                stale_after_days=self.settings.report.stale_price_days,
            )
            stale = self._valuation.stale_positions()
            if stale:
                self.notes.append("stale prices used for " + ", ".join(
                    f"{line.instrument.id} ({line.price_date})" for line in stale))
        return self._valuation

    def risk(self) -> RiskSummary:
        valuation = self.valuation()
        series = nav_series(valuation, self.data.prices, self.data.fx)
        return summarise_risk(series, valuation.nav, self.settings.risk)

    def vol_shares(self) -> VolShares:
        """Each line's share of volatility (docs/risk-notes.md), on the same window as risk()."""
        if self._vol_shares is None:
            self._vol_shares = vol_shares(self.valuation(), self.data.prices, self.data.fx, self.settings.risk)
        return self._vol_shares


def load_context(args: argparse.Namespace, today: date | None = None) -> Context:
    """Load settings and the data folder, and settle the valuation date.

    ``today`` replaces the clock in tests; it is only used when --as-of is not given.
    """
    overrides = list(args.set or []) + list(getattr(args, "set_after", None) or [])
    settings = load_settings(overrides=overrides, config_path=args.config)
    data = load_folder(args.data_dir, base_currency=settings.fx.base_currency,
                       pivot=settings.fx.pivot_currency, max_rate_age_days=settings.fx.max_rate_age_days)
    # The only place folio looks at the clock.
    requested = args.as_of if args.as_of is not None else (today or date.today())
    as_of, note = resolve_as_of(requested, data.prices)
    return Context(settings, data, as_of, data.warnings + ([note] if note else []))


def cmd_value(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    out.write(text_report.render_valuation(ctx.valuation(), ctx.settings.report, order=args.sort))
    return EXIT_OK


def cmd_risk(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    valuation = ctx.valuation()
    tail = None
    if args.by is not None:
        dimension = exposure.DIMENSIONS[args.by]
        losses = tail_losses(valuation, ctx.data.prices, ctx.data.fx, ctx.settings.risk, dimension.key,
                             cash_by_currency=dimension.includes_cash)
        tail = (dimension.title, losses)
    out.write(text_report.render_risk(valuation, ctx.risk(), ctx.settings, histogram=args.histogram, tail=tail))
    return EXIT_OK


def cmd_report(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    valuation = ctx.valuation()
    if args.by == RISK_REPORT:
        if args.since is not None:
            raise ValuationError("--since gives contributions to return; it does not apply to report --by risk")
        out.write(text_report.render_vol_shares(valuation, ctx.vol_shares(), ctx.settings.report))
        return EXIT_OK
    dimension = exposure.DIMENSIONS[args.by]
    result = exposure.breakdown(valuation, dimension, top=ctx.settings.report.top_n)
    parts = None
    if args.since is not None:
        try:
            parts = contributions(valuation, ctx.data.prices, ctx.data.fx, args.since, dimension.key,
                                  cash_by_currency=dimension.includes_cash)
        except ValueError as exc:
            raise ValuationError(str(exc)) from None
    out.write(text_report.render_breakdown(valuation, result, ctx.settings.report, parts))
    return EXIT_OK


def cmd_export(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    valuation = ctx.valuation()
    write = EXPORT_WRITERS[args.format]
    places = ctx.settings.report.money_places
    try:
        shares = ctx.vol_shares()
    except RiskError as exc:  # the export still goes out, without the shares
        shares = None
        ctx.notes.append(f"vol_share left blank: {exc}")
    if args.output in (None, "-"):
        write(valuation, out, places, shares)
        return EXIT_OK
    path = Path(args.output)
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            count = write(valuation, handle, places, shares)
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc.strerror}") from None
    ctx.notes.append(f"wrote {count} positions to {path}")
    return EXIT_OK


def cmd_check_limits(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    rules = build_rules(ctx.settings.limits)
    valuation = ctx.valuation()
    risk = ctx.risk() if needs_risk(rules) else None
    shares = ctx.vol_shares() if needs_vol_shares(rules) else None
    result = run_checks(valuation, rules, risk, shares)
    places = ctx.settings.report.percent_places
    for breach in result.breaches:
        out.write(breach.format(places) + "\n")
    if args.verbose:
        for nearest in result.nearest:
            out.write(nearest.format(places) + "\n")
    if result.ok:
        out.write(f"OK: {len(result.rules)} rules checked, no breaches\n")
        return EXIT_OK
    return EXIT_BREACH


COMMANDS: dict[str, Callable[[argparse.Namespace, Context, TextIO], int]] = {
    "value": cmd_value,
    "risk": cmd_risk,
    "report": cmd_report,
    "export": cmd_export,
    "check-limits": cmd_check_limits,
}


def _date_arg(text: str) -> date:
    try:
        return parse_date(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _add_common_options(parser: argparse.ArgumentParser, on_command: bool) -> None:
    # On the sub-commands the defaults are SUPPRESS, so an option given before
    # the command is not reset when the sub-command parser runs.
    def default(value):
        return argparse.SUPPRESS if on_command else value

    parser.add_argument("--data-dir", default=default("data"), metavar="DIR",
                        help="folder with the input files (default: ./data)")
    parser.add_argument("--as-of", type=_date_arg, default=default(None), metavar="DATE",
                        help="valuation date, YYYY-MM-DD (default: today)")
    parser.add_argument("--config", default=default(None), metavar="FILE",
                        help="settings file to use instead of ./folio.toml")
    parser.add_argument("--set", dest="set_after" if on_command else "set", action="append",
                        default=default(None), metavar="KEY=VALUE",
                        help="override a setting, e.g. limits.sector_max_share=0.3 (repeatable)")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every command; see the module docstring."""
    parser = argparse.ArgumentParser(
        prog="folio",
        description="Valuation, risk and limit checks for a portfolio.",
        epilog="Exit status: 0 ok, 1 limit breach (check-limits), 2 error.",
    )
    parser.add_argument("--version", action="version", version=f"folio {__version__}")
    _add_common_options(parser, on_command=False)
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, on_command=True)

    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    value = commands.add_parser("value", parents=[common], help="holdings valued in the base currency")
    value.add_argument("--sort", choices=text_report.VALUATION_ORDERS, default="instrument",
                       help="row order: instrument id or largest weight first (default: instrument)")

    risk = commands.add_parser("risk", parents=[common], help="volatility, VaR and expected shortfall")
    risk.add_argument("--histogram", action="store_true", help="also draw a histogram of the daily returns")
    risk.add_argument("--by", choices=REPORT_DIMENSIONS,
                      help="also split expected shortfall by sector, currency or kind")

    report = commands.add_parser("report", parents=[common], help="exposure breakdown")
    report.add_argument("--by", choices=REPORT_DIMENSIONS + (RISK_REPORT,), default="sector",
                        help="how to break down NAV (default: sector), or risk for each holding's and "
                             "sector's share of volatility")
    report.add_argument("--since", type=_date_arg, metavar="DATE",
                        help="add each row's contribution to return since DATE")

    export = commands.add_parser("export", parents=[common], help="positions as CSV or JSON")
    export.add_argument("--format", choices=sorted(EXPORT_WRITERS), default="csv")
    export.add_argument("--output", "-o", metavar="FILE", help="write here instead of standard output")

    limits = commands.add_parser("check-limits", parents=[common],
                                 help="run the limit rules; exit 1 on a breach")
    limits.add_argument("--verbose", "-v", action="store_true",
                        help="also show how close each rule without a breach is to its limit")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None,
         today: date | None = None) -> int:
    """Run one command and return the exit status.

    ``out`` and ``err`` default to the real streams; tests pass StringIO. Usage
    errors exit through argparse (status 2) before any data is read.
    """
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    args = build_parser().parse_args(argv)
    ctx = None
    try:
        ctx = load_context(args, today)
        return COMMANDS[args.command](args, ctx, out)
    except FolioError as exc:
        err.write(f"folio: error: {exc}\n")
        return EXIT_ERROR
    finally:
        if ctx is not None:
            for note in ctx.notes:
                err.write(f"folio: note: {note}\n")
