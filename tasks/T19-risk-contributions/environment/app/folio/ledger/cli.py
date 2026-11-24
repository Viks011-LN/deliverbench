"""Command-line interface for the ledger: ``python -m folio.ledger <command>``.

Commands:
  trades      the trades up to the valuation date (--instrument ID, --since DATE)
  pnl         realised P&L, matched FIFO, and income (--since DATE, --by instrument or sector)
  cash        cash by currency, or one currency's statement with --currency CCY
  reconcile   compare open lots and cash with positions.json; exit status 1 on any difference
  export      one CSV row per trade, with the realised P&L of each sale

The common options are folio's own and mean the same: --data-dir, --as-of,
--config and --set. The ledger reads the same data folder and settings, and
the valuation date (--as-of, settled exactly as folio settles it) is the
last day it counts.

Exit status: 0 success, 1 reconcile found a difference, 2 bad input, bad
settings or bad usage.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from folio import __version__
from folio.cli import Context, _add_common_options, _date_arg, load_context
from folio.domain.money import check_currency
from folio.errors import DataError, FolioError
from folio.ledger import cash, export, report
from folio.ledger.book import Ledger, LedgerError, load_ledger
from folio.ledger.fifo import instrument_pnl, match_fifo, sector_pnl
from folio.ledger.reconcile import reconcile

PROG = "folio-ledger"
EXIT_OK = 0
EXIT_DIFFERENCE = 1
EXIT_ERROR = 2

PNL_GROUPINGS = ("instrument", "sector")


def _since(args: argparse.Namespace, ctx: Context) -> date | None:
    if args.since is not None and args.since > ctx.as_of:
        raise LedgerError(f"--since {args.since} is after the valuation date {ctx.as_of}")
    return args.since


def cmd_trades(args: argparse.Namespace, ctx: Context, ledger: Ledger, out: TextIO) -> int:
    since = _since(args, ctx)
    trades = ledger.trades_between(since, ctx.as_of)
    subject = "Trades"
    if args.instrument is not None:
        if args.instrument not in ledger.universe:
            raise LedgerError(f"unknown instrument {args.instrument}: it is not in instruments.csv")
        trades = tuple(trade for trade in trades if trade.instrument_id == args.instrument)
        subject = f"Trades in {args.instrument}"
    title = f"{subject} {report.period(since, ctx.as_of)}"
    out.write(report.render_trades(ledger, ctx.data.portfolio, trades, title, ctx.settings.report.money_places))
    return EXIT_OK


def cmd_pnl(args: argparse.Namespace, ctx: Context, ledger: Ledger, out: TextIO) -> int:
    since = _since(args, ctx)
    base = ctx.settings.fx.base_currency
    places = ctx.settings.report.money_places
    result = match_fifo(ledger.trades_between(None, ctx.as_of), ledger.universe)
    lines = instrument_pnl(ledger, result, ctx.data.fx, base, ctx.as_of, since)
    portfolio = ctx.data.portfolio
    if args.by == "sector":
        title = f"Realised P&L (FIFO) and income by sector {report.period(since, ctx.as_of)}, in {base}"
        out.write(report.render_sector_pnl(portfolio, sector_pnl(lines, base), title, base, places))
    else:
        title = f"Realised P&L (FIFO) and income {report.period(since, ctx.as_of)}, in {base}"
        out.write(report.render_instrument_pnl(portfolio, lines, title, base, places))
    return EXIT_OK


def cmd_cash(args: argparse.Namespace, ctx: Context, ledger: Ledger, out: TextIO) -> int:
    places = ctx.settings.report.money_places
    if args.currency is not None:
        entries = cash.statement(ledger, args.currency, ctx.as_of)
        title = f"{args.currency} cash statement up to {ctx.as_of}"
        out.write(report.render_statement(ctx.data.portfolio, args.currency, entries, title, places))
        return EXIT_OK
    base = ctx.settings.fx.base_currency
    summaries = cash.summarise(ledger, ctx.as_of, ctx.data.fx, base)
    title = f"Cash by currency on {ctx.as_of}, from the trades and cash flows"
    out.write(report.render_cash(ctx.data.portfolio, summaries, title, base, places))
    return EXIT_OK


def cmd_reconcile(args: argparse.Namespace, ctx: Context, ledger: Ledger, out: TextIO) -> int:
    result = reconcile(ledger, ctx.data.portfolio, ctx.as_of)
    if result.cash_note:
        ctx.notes.append(result.cash_note)
    for difference in result.differences:
        out.write(difference.format() + "\n")
    if result.ok:
        out.write(f"OK: {result.summary()}\n")
        return EXIT_OK
    return EXIT_DIFFERENCE


def cmd_export(args: argparse.Namespace, ctx: Context, ledger: Ledger, out: TextIO) -> int:
    trades = ledger.trades_between(None, ctx.as_of)
    options = dict(portfolio_code=ctx.data.portfolio.code, base_currency=ctx.settings.fx.base_currency,
                   money_places=ctx.settings.report.money_places)
    if args.output in (None, "-"):
        export.write_csv(ledger, trades, ctx.data.fx, out, **options)
        return EXIT_OK
    path = Path(args.output)
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            count = export.write_csv(ledger, trades, ctx.data.fx, handle, **options)
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc.strerror}") from None
    ctx.notes.append(f"wrote {count} trades to {path}")
    return EXIT_OK


COMMANDS: dict[str, Callable[[argparse.Namespace, Context, Ledger, TextIO], int]] = {
    "trades": cmd_trades,
    "pnl": cmd_pnl,
    "cash": cmd_cash,
    "reconcile": cmd_reconcile,
    "export": cmd_export,
}


def _currency_arg(text: str) -> str:
    try:
        return check_currency(text.strip().upper())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every ledger command; see the module docstring."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Trades, realised P&L and cash behind the portfolio in positions.json.",
        epilog="Exit status: 0 ok, 1 reconcile found a difference, 2 error.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} (folio {__version__})")
    _add_common_options(parser, on_command=False)
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, on_command=True)

    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    trades = commands.add_parser("trades", parents=[common], help="the trades up to the valuation date")
    trades.add_argument("--instrument", metavar="ID", help="only the trades in this instrument")
    trades.add_argument("--since", type=_date_arg, metavar="DATE", help="only the trades on or after DATE")

    pnl = commands.add_parser("pnl", parents=[common], help="realised P&L (FIFO) and income")
    pnl.add_argument("--since", type=_date_arg, metavar="DATE",
                     help="only sales and income on or after DATE (default: everything)")
    pnl.add_argument("--by", choices=PNL_GROUPINGS, default="instrument",
                     help="one row per instrument or per sector (default: instrument)")

    cash_parser = commands.add_parser("cash", parents=[common], help="cash balances rebuilt from the ledger")
    cash_parser.add_argument("--currency", type=_currency_arg, metavar="CCY",
                             help="list every movement in CCY with its running balance")

    commands.add_parser("reconcile", parents=[common],
                        help="compare open lots and cash with positions.json; exit 1 on a difference")

    export_parser = commands.add_parser("export", parents=[common], help="the trades as CSV, with realised P&L")
    export_parser.add_argument("--output", "-o", metavar="FILE", help="write here instead of standard output")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None,
         today: date | None = None) -> int:
    """Run one ledger command and return the exit status.

    Shaped like folio.cli.main: ``out`` and ``err`` default to the real
    streams, ``today`` replaces the clock, and usage errors exit through
    argparse (status 2) before any file is read.
    """
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    args = build_parser().parse_args(argv)
    ctx = None
    try:
        ctx = load_context(args, today)
        ledger = load_ledger(ctx.data.path, ctx.data.universe)
        return COMMANDS[args.command](args, ctx, ledger, out)
    except FolioError as exc:
        err.write(f"{PROG}: error: {exc}\n")
        return EXIT_ERROR
    finally:
        if ctx is not None:
            for note in ctx.notes:
                err.write(f"{PROG}: note: {note}\n")
