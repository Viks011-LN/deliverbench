"""Command-line interface: ``python -m folio.rebalance <command>``.

Commands:
  drift     each target with its current weight, band and drift
  propose   the trades that bring targets outside their band back to the
            model, then the weights after them
  export    the proposed trades as CSV

Options, accepted before or after the command:
  --targets FILE    model weights (default: targets.csv in the data folder)
  --rules FILE      dealing rules (default: trading.toml in the data folder)
and folio's own --data-dir, --as-of, --config and --set, which mean the same
here: the book is loaded and valued exactly as ``folio value`` does it.

propose and export also take --cash-buffer SHARE and --min-ticket AMOUNT,
which replace the rules file's values for one run, so the exported trades
can match a proposal looked at with different numbers.

Exit status: 0 success, 2 bad input, bad settings or bad usage. drift exits
0 whatever it finds: it reports, it does not check.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable, Sequence, TextIO

from folio.cli import Context, _add_common_options, load_context
from folio.domain.money import to_decimal
from folio.errors import DataError, FolioError
from folio.rebalance import export, text
from folio.rebalance.dealing import DealingRules, check_cash_buffer, load_rules
from folio.rebalance.drift import cash_weight_of, holdings_of, measure_drift
from folio.rebalance.effect import effect_of
from folio.rebalance.engine import Proposal, propose
from folio.rebalance.sizing import Quotes
from folio.rebalance.targets import TargetSet, load_targets

PROG = "folio-rebalance"
EXIT_OK = 0
EXIT_ERROR = 2

TARGETS_FILE = "targets.csv"
RULES_FILE = "trading.toml"


def load_target_file(args: argparse.Namespace, ctx: Context) -> TargetSet:
    path = getattr(args, "targets", None) or ctx.data.path / TARGETS_FILE
    return load_targets(path, ctx.data.universe)


def load_rules_file(args: argparse.Namespace, ctx: Context) -> DealingRules:
    """The dealing rules, with --cash-buffer and --min-ticket applied."""
    path = getattr(args, "rules", None) or ctx.data.path / RULES_FILE
    rules = load_rules(path, ctx.data.universe, ctx.settings.fx.base_currency)
    return rules.with_overrides(cash_buffer=getattr(args, "cash_buffer", None),
                                min_ticket=getattr(args, "min_ticket", None))


def build_proposal(args: argparse.Namespace, ctx: Context) -> Proposal:
    targets = load_target_file(args, ctx)
    rules = load_rules_file(args, ctx)
    valuation = ctx.valuation()
    quotes = Quotes(valuation, ctx.data.universe, ctx.data.prices, ctx.data.fx)
    return propose(valuation, targets, rules, quotes)


def cmd_drift(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    targets = load_target_file(args, ctx)
    valuation = ctx.valuation()
    drifts = measure_drift(targets, holdings_of(valuation), cash_weight_of(valuation))
    out.write(text.render_drift(valuation, drifts, ctx.settings.report))
    return EXIT_OK


def cmd_propose(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    proposal = build_proposal(args, ctx)
    out.write(text.render_proposal(proposal, effect_of(proposal), ctx.settings.report))
    return EXIT_OK


def cmd_export(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    proposal = build_proposal(args, ctx)
    places = ctx.settings.report.money_places
    if args.output in (None, "-"):
        export.write_trades(proposal, out, places)
        return EXIT_OK
    path = Path(args.output)
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            count = export.write_trades(proposal, handle, places)
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc.strerror}") from None
    ctx.notes.append(f"wrote {count} trades to {path}")
    return EXIT_OK


COMMANDS: dict[str, Callable[[argparse.Namespace, Context, TextIO], int]] = {
    "drift": cmd_drift,
    "propose": cmd_propose,
    "export": cmd_export,
}


def _share_arg(text: str) -> Decimal:
    try:
        return check_cash_buffer(to_decimal(text, what="cash buffer"), name="the cash buffer")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _amount_arg(text: str) -> Decimal:
    try:
        value = to_decimal(text, what="minimum ticket")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"minimum ticket must be 0 or more, got {text}")
    return value


def _add_input_options(parser: argparse.ArgumentParser, on_command: bool) -> None:
    # SUPPRESS on the sub-commands, as in folio.cli, so a file given before
    # the command is not reset by the sub-command parser.
    default = argparse.SUPPRESS if on_command else None
    parser.add_argument("--targets", default=default, metavar="FILE",
                        help=f"model weights (default: {TARGETS_FILE} in the data folder)")
    parser.add_argument("--rules", default=default, metavar="FILE",
                        help=f"dealing rules (default: {RULES_FILE} in the data folder)")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every command; see the module docstring."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Rebalancing proposals: bring the book back to its model weights.",
        epilog="Exit status: 0 ok, 2 error.",
    )
    _add_common_options(parser, on_command=False)
    _add_input_options(parser, on_command=False)
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, on_command=True)
    _add_input_options(common, on_command=True)
    sizing = argparse.ArgumentParser(add_help=False)
    sizing.add_argument("--cash-buffer", type=_share_arg, metavar="SHARE",
                        help="share of NAV to keep in cash after the trades, e.g. 0.01 (default: rules file)")
    sizing.add_argument("--min-ticket", type=_amount_arg, metavar="AMOUNT",
                        help="smallest trade worth dealing, in the base currency (default: rules file)")

    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    commands.add_parser("drift", parents=[common], help="each target's current weight, band and drift")
    commands.add_parser("propose", parents=[common, sizing],
                        help="trades back to the model weights, then the weights after")
    trades = commands.add_parser("export", parents=[common, sizing], help="the proposed trades as CSV")
    trades.add_argument("--output", "-o", metavar="FILE", help="write here instead of standard output")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None,
         today: date | None = None) -> int:
    """Run one command and return the exit status, like folio.cli.main.

    ``out`` and ``err`` default to the real streams; tests pass StringIO and
    ``today`` in place of the clock. Usage errors exit through argparse
    (status 2) before any data is read.
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
