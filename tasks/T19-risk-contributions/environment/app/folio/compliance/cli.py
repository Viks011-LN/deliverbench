"""Command-line interface: ``python -m folio.compliance <command>``.

Checks the portfolio against the client's investment guidelines after
trading. This is not ``folio check-limits``: the desk's limits are folio
settings that the desk owns, while the mandate belongs to the client and
lives in its own file (guidelines.toml in the data folder, or --guidelines
FILE), with the client's restricted list beside it in restricted.csv.
Nothing here reads or changes folio's [limits].

Commands:
  check        run the guidelines in force; exit status 1 if any is violated
  restricted   holdings on the restricted list on the valuation date
  mandate      the guidelines in the mandate, as a table

The common options are folio's own and behave the same way, before or after
the command: --data-dir, --as-of, --config and --set. Of the settings, only
[report] and [fx] matter here (places, base currency, stale prices).

Exit status: 0 success, 1 a guideline is violated (check only), 2 bad input,
bad settings, a bad mandate or bad usage.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from folio import __version__
from folio.cli import Context, _add_common_options, load_context
from folio.compliance import text
from folio.compliance.checker import run_guidelines
from folio.compliance.mandate import Mandate
from folio.compliance.registry import (
    MANDATE_FILE,
    RESTRICTED_FILE,
    build_guidelines,
    needs_restricted_list,
    read_mandate,
)
from folio.compliance.restricted import restricted_holdings, upcoming_restrictions
from folio.compliance.restricted_list import load_restricted
from folio.errors import ConfigError, DataError, FolioError

PROG = "folio-compliance"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2


def read_client_mandate(args: argparse.Namespace, ctx: Context) -> Mandate:
    """The mandate from --guidelines, else from the data folder, checked against the portfolio held."""
    if args.guidelines is not None:
        path = Path(args.guidelines)
    else:
        path = ctx.data.path / MANDATE_FILE
        if not path.is_file():
            raise ConfigError(f"no {MANDATE_FILE} in {ctx.data.path}; "
                              f"give the client's mandate with --guidelines FILE")
    mandate = read_mandate(path)
    mandate.require_portfolio(ctx.data.portfolio.code)
    return mandate


def cmd_check(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    mandate = read_client_mandate(args, ctx)
    # A guideline switched off is a waiver the client agreed to; say so on every run.
    for term in mandate.terms:
        if not term.enabled:
            ctx.notes.append(f"{term.key} is switched off in {mandate.source}")
    restricted = None
    if needs_restricted_list(mandate):
        path = ctx.data.path / RESTRICTED_FILE
        if not path.is_file():
            raise DataError(f"{mandate.source} has restricted_holdings in force but there is no {path}; "
                            f"add the client's list or set enabled = false")
        restricted = load_restricted(path)
    result = run_guidelines(ctx.valuation(), build_guidelines(mandate, restricted))
    out.write(text.render_check(result, ctx.settings.report, explain=args.explain))
    return EXIT_OK if result.ok else EXIT_VIOLATION


def cmd_restricted(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    restricted = load_restricted(ctx.data.path / RESTRICTED_FILE)
    valuation = ctx.valuation()
    held = restricted_holdings(valuation, restricted)
    coming = upcoming_restrictions(valuation, restricted)
    out.write(text.render_restricted(valuation, held, coming, restricted, ctx.settings.report))
    return EXIT_OK


def cmd_mandate(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    mandate = read_client_mandate(args, ctx)
    out.write(text.render_mandate(mandate, ctx.data.portfolio.name, ctx.settings.report))
    return EXIT_OK


COMMANDS: dict[str, Callable[[argparse.Namespace, Context, TextIO], int]] = {
    "check": cmd_check,
    "restricted": cmd_restricted,
    "mandate": cmd_mandate,
}


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every command; see the module docstring."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Check the portfolio against the client's investment guidelines.",
        epilog="Exit status: 0 ok, 1 a guideline is violated (check), 2 error.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} (folio {__version__})")
    _add_common_options(parser, on_command=False)
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, on_command=True)
    mandate_file = argparse.ArgumentParser(add_help=False)
    mandate_file.add_argument("--guidelines", metavar="FILE",
                              help=f"mandate file to use instead of {MANDATE_FILE} in the data folder")

    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    check = commands.add_parser("check", parents=[common, mandate_file],
                                help="run the guidelines in force; exit 1 on a violation")
    check.add_argument("--explain", action="store_true",
                       help="also show each guideline's headroom: how far its tightest subject is from the limit")
    commands.add_parser("restricted", parents=[common],
                        help="holdings on the restricted list on the valuation date")
    commands.add_parser("mandate", parents=[common, mandate_file],
                        help="the guidelines in the mandate, as a table")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None,
         today: date | None = None) -> int:
    """Run one command and return the exit status.

    Shaped like folio.cli.main: ``out`` and ``err`` default to the real
    streams, ``today`` replaces the clock in tests, and usage errors exit
    through argparse (status 2) before any file is read.
    """
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    args = build_parser().parse_args(argv)
    ctx = None
    try:
        ctx = load_context(args, today)
        return COMMANDS[args.command](args, ctx, out)
    except FolioError as exc:
        err.write(f"{PROG}: error: {exc}\n")
        return EXIT_ERROR
    finally:
        if ctx is not None:
            for note in ctx.notes:
                err.write(f"{PROG}: note: {note}\n")
