"""Command-line interface for stress scenarios: ``python -m folio.scenarios <command>``.

Commands:
  list                 the scenarios in the scenario file
  run NAME [--by DIM]  one scenario's P&L per group and in total (default: by sector)
  compare              every scenario's total P&L, worst first
  export [-o FILE]     CSV, one row per holding per scenario

Options, accepted before or after the command: the common folio options
(--data-dir, --as-of, --config, --set; see folio/cli.py) and
  --scenarios FILE  scenario file to use instead of scenarios.toml in the
                    data folder

Settings, the data folder and the valuation date are loaded exactly as
``folio`` loads them, through folio.cli.load_context, so a scenario always
runs on the book that ``folio value`` shows. The scenario file is read and
checked against instruments.csv before any command runs.

Exit status: 0 success, 2 bad input, bad settings, a bad scenario file or
bad usage. Errors print as ``folio-scenarios: error: ...``.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from folio import __version__
from folio.calc import exposure
from folio.cli import Context, _add_common_options, load_context
from folio.errors import DataError, FolioError
from folio.scenarios import csv_output, text_output
from folio.scenarios.engine import Stresser
from folio.scenarios.grouping import group_pnl
from folio.scenarios.scenario_file import FILE_NAME, check_against, find, read_scenarios
from folio.scenarios.shocks import Scenario

PROG = "folio-scenarios"
EXIT_OK = 0
EXIT_ERROR = 2
DEFAULT_DIMENSION = "sector"


@dataclass
class Session:
    """folio's context for this run plus the scenarios, already checked against its instruments."""

    ctx: Context
    scenarios: tuple[Scenario, ...]
    source: Path

    def stresser(self) -> Stresser:
        return Stresser(self.ctx.valuation(), self.ctx.data.prices, self.ctx.data.fx)


def scenario_path(args: argparse.Namespace) -> Path:
    """--scenarios if given, else scenarios.toml in the data folder."""
    if args.scenarios is not None:
        return Path(args.scenarios)
    return Path(args.data_dir) / FILE_NAME


def cmd_list(args: argparse.Namespace, session: Session, out: TextIO) -> int:
    out.write(text_output.render_list(session.scenarios, str(session.source)))
    return EXIT_OK


def cmd_run(args: argparse.Namespace, session: Session, out: TextIO) -> int:
    scenario = find(session.scenarios, args.name, session.source.name)
    result = session.stresser().run(scenario)
    breakdown = group_pnl(result, exposure.DIMENSIONS[args.by])
    out.write(text_output.render_run(result, breakdown, session.ctx.settings.report))
    return EXIT_OK


def cmd_compare(args: argparse.Namespace, session: Session, out: TextIO) -> int:
    results = session.stresser().run_all(session.scenarios)
    out.write(text_output.render_compare(session.ctx.valuation(), results, session.ctx.settings.report))
    return EXIT_OK


def cmd_export(args: argparse.Namespace, session: Session, out: TextIO) -> int:
    results = session.stresser().run_all(session.scenarios)
    places = session.ctx.settings.report.money_places
    if args.output in (None, "-"):
        csv_output.write_csv(results, out, places)
        return EXIT_OK
    path = Path(args.output)
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            count = csv_output.write_csv(results, handle, places)
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc.strerror}") from None
    session.ctx.notes.append(f"wrote {count} rows for {len(results)} scenarios to {path}")
    return EXIT_OK


COMMANDS: dict[str, Callable[[argparse.Namespace, Session, TextIO], int]] = {
    "list": cmd_list,
    "run": cmd_run,
    "compare": cmd_compare,
    "export": cmd_export,
}


def _add_scenario_option(parser: argparse.ArgumentParser, on_command: bool) -> None:
    # Same trick as folio's common options: SUPPRESS on the sub-commands, so
    # --scenarios given before the command survives the sub-command parser.
    parser.add_argument("--scenarios", default=argparse.SUPPRESS if on_command else None, metavar="FILE",
                        help=f"scenario file (default: {FILE_NAME} in the data folder)")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every command; see the module docstring."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Stress scenarios: what-if P&L on the current book. Run as python -m folio.scenarios.",
        epilog="Exit status: 0 ok, 2 error.",
    )
    parser.add_argument("--version", action="version", version=f"folio {__version__}")
    _add_common_options(parser, on_command=False)
    _add_scenario_option(parser, on_command=False)
    common = argparse.ArgumentParser(add_help=False)
    _add_common_options(common, on_command=True)
    _add_scenario_option(common, on_command=True)

    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    commands.add_parser("list", parents=[common], help="the scenarios in the scenario file")

    run = commands.add_parser("run", parents=[common], help="one scenario's P&L per group and in total")
    run.add_argument("name", help="the scenario, as named by the list command")
    run.add_argument("--by", choices=sorted(exposure.DIMENSIONS), default=DEFAULT_DIMENSION,
                     help=f"how to group the P&L (default: {DEFAULT_DIMENSION})")

    commands.add_parser("compare", parents=[common], help="every scenario's total P&L, worst first")

    export = commands.add_parser("export", parents=[common], help="CSV, one row per holding per scenario")
    export.add_argument("--output", "-o", metavar="FILE", help="write here instead of standard output")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None, err: TextIO | None = None,
         today: date | None = None) -> int:
    """Run one command and return the exit status.

    Shaped like folio.cli.main: ``out`` and ``err`` default to the real
    streams, ``today`` replaces the clock when --as-of is not given, and usage
    errors exit through argparse (status 2) before anything is read.
    """
    out = out if out is not None else sys.stdout
    err = err if err is not None else sys.stderr
    args = build_parser().parse_args(argv)
    ctx = None
    try:
        ctx = load_context(args, today)
        source = scenario_path(args)
        scenarios = read_scenarios(source)
        check_against(scenarios, ctx.data.universe, ctx.settings.fx.base_currency, source.name)
        return COMMANDS[args.command](args, Session(ctx, scenarios, source), out)
    except FolioError as exc:
        err.write(f"{PROG}: error: {exc}\n")
        return EXIT_ERROR
    finally:
        if ctx is not None:
            for note in ctx.notes:
                err.write(f"{PROG}: note: {note}\n")
