"""Command-line interface: ``python -m folio.benchmark <command>``.

Commands:
  active     active weights (book minus index) per holding, or per group with --by
  tracking   relative return and tracking error over a window; --by adds the
             allocation/selection split of the relative return
  overlap    active share and the largest over- and underweights
  export     active weights per holding as CSV

Options, before or after the command: those of folio (--data-dir, --as-of,
--config, --set), plus --benchmark FILE and --levels FILE to read other files
than benchmark.csv and benchmark_levels.csv in the data folder.

Settings, the data folder and the valuation date are loaded exactly as for
``folio``. Each command reads only the benchmark file it needs: tracking reads
the levels (and the weights too with --by), the others read the weights.

Exit status: 0 success, 2 bad input, bad settings or bad usage.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from folio import __version__
from folio.benchmark import active, allocation, csv_export, overlap, text, tracking
from folio.benchmark.levels_csv import IndexLevels, load_levels
from folio.benchmark.weights_csv import IndexWeights, load_weights
from folio.calc import exposure
from folio.calc.returns import nav_series
from folio.cli import Context, _add_common_options, load_context
from folio.errors import DataError, FolioError, ValuationError

PROG = "folio-benchmark"
WEIGHTS_FILE = "benchmark.csv"
LEVELS_FILE = "benchmark_levels.csv"

EXIT_OK = 0
EXIT_ERROR = 2


def _weights(args: argparse.Namespace, ctx: Context) -> IndexWeights:
    return load_weights(Path(args.benchmark) if args.benchmark else ctx.data.path / WEIGHTS_FILE)


def _levels(args: argparse.Namespace, ctx: Context) -> IndexLevels:
    return load_levels(Path(args.levels) if args.levels else ctx.data.path / LEVELS_FILE)


def _comparison(args: argparse.Namespace, ctx: Context) -> active.Comparison:
    comparison = active.compare(ctx.valuation(), _weights(args, ctx), ctx.data.universe)
    ctx.notes.extend(comparison.notes)
    return comparison


def cmd_active(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    comparison = _comparison(args, ctx)
    if args.by is None:
        out.write(text.render_holdings(comparison, ctx.settings.report))
    else:
        grouped = active.by_group(comparison, exposure.DIMENSIONS[args.by])
        out.write(text.render_groups(comparison, grouped, ctx.settings.report))
    return EXIT_OK


def cmd_tracking(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    valuation = ctx.valuation()
    levels = _levels(args, ctx)
    series = nav_series(valuation, ctx.data.prices, ctx.data.fx)
    window = args.window if args.window is not None else ctx.settings.risk.var_lookback_days
    summary = tracking.summarise_tracking(series, levels, window, ctx.settings.risk)
    if summary.last_level < summary.end:
        ctx.notes.append(f"the last level of {levels.code} is for {summary.last_level}; "
                         f"it stands in for every later day up to {summary.end}")
    split = None
    if args.by is not None:
        comparison = _comparison(args, ctx)
        try:
            split = allocation.split_by_group(comparison, ctx.data.prices, ctx.data.fx, levels, summary.start,
                                              exposure.DIMENSIONS[args.by])
        except ValueError as exc:
            raise ValuationError(str(exc)) from None
    out.write(text.render_tracking(valuation, summary, ctx.settings.report, split))
    return EXIT_OK


def cmd_overlap(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    comparison = _comparison(args, ctx)
    out.write(text.render_overlap(comparison, overlap.overlap(comparison, args.top), ctx.settings.report))
    return EXIT_OK


def cmd_export(args: argparse.Namespace, ctx: Context, out: TextIO) -> int:
    comparison = _comparison(args, ctx)
    if args.output in (None, "-"):
        csv_export.write_active_csv(comparison, out)
        return EXIT_OK
    path = Path(args.output)
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            count = csv_export.write_active_csv(comparison, handle)
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc.strerror}") from None
    ctx.notes.append(f"wrote {count} rows to {path}")
    return EXIT_OK


COMMANDS: dict[str, Callable[[argparse.Namespace, Context, TextIO], int]] = {
    "active": cmd_active,
    "tracking": cmd_tracking,
    "overlap": cmd_overlap,
    "export": cmd_export,
}


def _whole_number(minimum: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            value = None
        if value is None or value < minimum:
            raise argparse.ArgumentTypeError(f"expected a whole number of at least {minimum}, got {text!r}")
        return value
    return parse


def _add_benchmark_options(parser: argparse.ArgumentParser, on_command: bool) -> None:
    # Same arrangement as folio.cli._add_common_options: SUPPRESS on the
    # sub-commands, so an option given before the command is kept.
    def default(value):
        return argparse.SUPPRESS if on_command else value

    parser.add_argument("--benchmark", default=default(None), metavar="FILE",
                        help=f"index constituents and weights (default: {WEIGHTS_FILE} in the data folder)")
    parser.add_argument("--levels", default=default(None), metavar="FILE",
                        help=f"daily index levels (default: {LEVELS_FILE} in the data folder)")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every command; see the module docstring."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Compare the portfolio with its benchmark index.",
        epilog="Exit status: 0 ok, 2 error.",
    )
    parser.add_argument("--version", action="version", version=f"folio {__version__}")
    _add_common_options(parser, on_command=False)
    _add_benchmark_options(parser, on_command=False)
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, on_command=True)
    _add_benchmark_options(common, on_command=True)
    dimensions = list(exposure.DIMENSIONS)

    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    active_cmd = commands.add_parser("active", parents=[common],
                                     help="active weights per holding, or per group with --by")
    active_cmd.add_argument("--by", choices=dimensions, help="group the holdings, e.g. by sector")

    tracking_cmd = commands.add_parser("tracking", parents=[common], help="relative return and tracking error")
    tracking_cmd.add_argument("--window", type=_whole_number(2), metavar="DAYS",
                              help="number of daily returns to use (default: risk.var_lookback_days)")
    tracking_cmd.add_argument("--by", choices=dimensions,
                              help="also split the relative return into allocation and selection by group")

    overlap_cmd = commands.add_parser("overlap", parents=[common],
                                      help="active share and the largest over- and underweights")
    overlap_cmd.add_argument("--top", type=_whole_number(1), default=5, metavar="N",
                             help="how many over- and underweights to list (default: 5)")

    export_cmd = commands.add_parser("export", parents=[common], help="active weights per holding as CSV")
    export_cmd.add_argument("--output", "-o", metavar="FILE", help="write here instead of standard output")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None,
         today: date | None = None) -> int:
    """Run one command and return the exit status.

    Shaped like folio.cli.main: ``out`` and ``err`` default to the real
    streams, ``today`` replaces the clock, and usage errors exit through
    argparse (status 2) before any data is read.
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
