"""Generate T16's data, bundles, hidden cases and wrong solutions, and prove that the hidden checks do their job.

Reads (all written by hand):
  environment/app/     the room: the original bt package, its tests and documents, and the example strategy
                       (examples/strategies/channel.py)
  solution/bt/         the reference: the same package with the strategy slot (a complete tree)
  strategies/*.py      the three hidden strategies, written for the slot as docs/design/strategy-slot.md says
  strategies/builtins/ changed momentum and reversion, written for the slot: added at the end of
                       bt/strategies/momentum.py and reversion.py (which must exist), they show whether the built-ins
                       run through their files (gate review; added, not copied over, since 0.1.3)
Writes:
  environment/app/tests/data/, tests/golden/   the visible sample and the original's output on it
  environment/app/examples/                    the example's prices and config, and expected/: what the
                                               reference prints for it (report.json, equity.csv, summary.txt)
  tests/original/bundle.json    the original package, its tests, their data and golden files, pytest.ini
  tests/reference/bundle.json   the reference package
  tests/data/cases.json         the hidden price files, configs and command lines, and the strategies' sources
  cheats/*.sh                   the wrong solutions (WRONG below; plant.sh and tamper.sh come from
                                scripts/make_integrity_cheats.py)
Run: python generate.py [output_root]   (default: this job folder)

The expected output of a hidden case is never stored: at grading the checks produce it by running the shipped
original (the built-in strategies) or the reference with the strategy dropped in. So this file proves, on every
run (asserts):
  1. The visible tests pass on the original and on the reference.
  2. The reference prints what the original prints on every built-in case, under two hash seeds.
  3. The expected outputs of the dropped-in strategies and of the swapped built-ins come from an implementation
     independent of the reference: the original program with strategy files added the old way, five edits each
     serving a type from its file in bt/strategies/ when there is one (FILES_FIRST below), prints exactly what the
     reference prints on every dropped-in and every swapped case. FILES_FIRST ships no files for the two built-ins,
     so the swap writes the changed ones as they are, while the reference gets them added at the end of its own
     files; the reference prints the same with them added as with them copied over its files (the check before
     0.1.3). Each swapped case prints something else than the unswapped reference. The example's expected output in
     the room is the reference's.
  4. The hidden configs use only settings the README documents, each built-in strategy's six configs use every
     documented setting away from its default and give and leave out each of its parameters, and no invalid
     config names a type that the example or a hidden strategy could serve.
  5. The hidden cases run every line of the original's engine-side modules (bt/config, bt/signals, bt/portfolio,
     bt/execution, bt/metrics, bt/report, bt/engine.py, bt/cli.py) except the few listed in UNREACHED.
  6. Doing nothing (the original) fails exactly the dropped-in and the swapped-built-ins checks, and each wrong
     solution changes exactly the outputs and tests it declares (WRONG), so the selftest's declared fails are
     proved here as well. The hybrid that keeps the five special cases for the two built-ins and adds a branch for
     every other type (PATCHED_ORIGINAL) fails exactly the swapped-built-ins check. So does FILES_FIRST, which
     serves a type from its file first and ships no file for the two (second review B1): it prints the reference's
     output on every swapped case and fails only because the two files are not in its package.
  7. A right refactor that keeps other names in the built-ins' files, imported from there at start-up
     (KEEPS_NAMES: bt/signals/momentum.py re-exports the scoring from bt/strategies/momentum.py), fails no check;
     with the changed built-ins copied over its files instead of added, it would fail the swapped check (second
     review A1).
"""
import contextlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True  # no __pycache__ in the job folder

GUID = "c88534af-918a-4e91-9799-5c9bc36dcd29"
CANARY = f"harbor-canary GUID {GUID}"
SEED = 1616
APP = HERE / "environment" / "app"
SOLUTION = HERE / "solution"
HIDDEN_STRATEGIES = HERE / "strategies"
SKIP = {"__pycache__", ".pytest_cache"}
WORKERS = min(12, os.cpu_count() or 4)
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "LANG": "C.UTF-8",
       "PYTHONDONTWRITEBYTECODE": "1"}

CHECK_OUTPUT = "test_outputs::test_output_unchanged"
CHECK_DROPPED = "test_outputs::test_strategies_dropped_in"
CHECK_TESTS = "test_outputs::test_original_tests_pass"
CHECK_BUILTINS = "test_outputs::test_builtins_go_through_the_slot"
BUILTIN_STRATEGIES = HERE / "strategies" / "builtins"

TICKERS = ["ARVO", "BELK", "CIRA", "DUQX", "EKTA", "FOLM", "GARN", "HOLT", "IRSK", "JUVO"]
EXAMPLE_TICKERS = ["KEPA", "LUQV", "MIQZ", "NOXA", "ORBI", "PAXT", "QUIL", "REQX"]


# ----------------------------------------------------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------------------------------------------------

def read_tree(root: Path, sub: str) -> dict[str, str]:
    files = {}
    for path in sorted((root / sub).rglob("*")):
        if path.is_file() and not SKIP & set(path.parts) and path.suffix != ".pyc":
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return files


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def config_text(config) -> str:
    return config if isinstance(config, str) else json.dumps(config, indent=2) + "\n"


# ----------------------------------------------------------------------------------------------------------------
# Price files
# ----------------------------------------------------------------------------------------------------------------

def business_days(start: date, count: int) -> list[str]:
    days, d = [], start
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def walk(rng: random.Random, days: int, spec: dict) -> list:
    """A random walk with drift, plus what a spec asks for: a listing, gaps, a pinned price, a crash."""
    price = spec.get("price", rng.uniform(20, 200))
    out = []
    for t in range(days):
        if t:
            r = rng.gauss(spec.get("mu", 0.0003), spec.get("sigma", 0.015))
            if "crash" in spec and spec["crash"][0] <= t < spec["crash"][0] + spec["crash"][1]:
                r -= spec["crash"][2]
            price = max(1.0, price * (1.0 + r))
        out.append(round(price, 2))
    if "pin" in spec:  # a takeover target: jumps, then trades flat at the deal price (in quarters: exact in binary)
        start, length, jump = spec["pin"]
        pinned = round(out[start - 1] * (1.0 + jump) * 4) / 4
        for t in range(start, min(days, start + length)):
            out[t] = pinned
    for start, length in spec.get("gaps", []):
        for t in range(start, min(days, start + length)):
            out[t] = None
    for t in range(spec.get("listing", 0)):
        out[t] = None
    return out


def price_file(rng: random.Random, start: date, days: int, specs: dict, blank_lines=()) -> str:
    dates = business_days(start, days)
    columns = {name: walk(rng, days, spec) for name, spec in specs.items()}
    lines = ["date," + ",".join(specs)]
    for t, day in enumerate(dates):
        if t in blank_lines:
            lines.append("")
        cells = ["" if columns[name][t] is None else f"{columns[name][t]:.2f}" for name in specs]
        lines.append(day + "," + ",".join(cells))
    return "\n".join(lines) + "\n"


def plain_specs(rng: random.Random, names, mu=(-0.0004, 0.0012), sigma=(0.008, 0.025)) -> dict:
    return {name: {"mu": rng.uniform(*mu), "sigma": rng.uniform(*sigma)} for name in names}


def file_dates(text: str) -> list[str]:
    return [line.split(",", 1)[0] for line in text.splitlines()[1:] if line]


# ----------------------------------------------------------------------------------------------------------------
# The visible sample and the example
# ----------------------------------------------------------------------------------------------------------------

def sample(rng: random.Random) -> dict[str, str]:
    specs = plain_specs(rng, TICKERS[:8])
    specs["GARN"] = {"mu": 0.0045, "sigma": 0.012, "gaps": [(200, 9)]}   # a strong name, held, then a long gap
    specs["HOLT"]["listing"] = 40
    specs["IDX"] = {"price": 1000.0, "mu": 0.0003, "sigma": 0.008}       # the benchmark column
    return {
        "prices.csv": price_file(rng, date(2024, 1, 2), 400, specs),
        "momentum.json": config_text({"signal": {"type": "momentum", "lookback": 60, "skip": 5}, "top_n": 3,
                                      "rebalance": "monthly", "benchmark": "IDX"}),
        "reversion.json": config_text({"signal": {"type": "reversion", "window": 15, "entry_z": 1.0}, "top_n": 2,
                                       "allow_short": True, "rebalance": "daily", "rebalance_band": 0.01,
                                       "borrow_bps": 75.0, "exclude": ["IDX"]}),
        "bad_config.json": config_text({"lookback": 60}),
    }


def example(rng: random.Random) -> dict[str, str]:
    specs = plain_specs(rng, EXAMPLE_TICKERS, sigma=(0.01, 0.03))
    specs["NOXA"]["listing"] = 25
    return {
        "prices.csv": price_file(rng, date(2025, 2, 3), 215, specs),
        "channel.json": config_text({"signal": {"type": "channel", "days": 30, "neutral": 0.15}, "top_n": 3,
                                     "allow_short": True, "rebalance": "weekly", "max_weight": 0.35}),
    }


EXAMPLE_ARGS = [["--prices", "examples/prices.csv", "--config", "examples/channel.json", "--equity", "equity.csv"],
                ["--prices", "examples/prices.csv", "--config", "examples/channel.json", "--format", "text"]]


# ----------------------------------------------------------------------------------------------------------------
# The hidden data
# ----------------------------------------------------------------------------------------------------------------

def hidden_prices(rng: random.Random) -> dict[str, str]:
    files = {}
    # Broad: ten names, across two New Years (both weeks split between years), a late listing.
    specs = plain_specs(rng, TICKERS)
    specs["IRSK"]["listing"] = 60
    specs["IDX"] = {"price": 2500.0, "mu": 0.0002, "sigma": 0.009}
    files["P1"] = price_file(rng, date(2024, 9, 2), 420, specs)
    # Gaps: strong names that go missing (a short gap, a long one), blank lines in the file.
    specs = plain_specs(rng, TICKERS[:8])
    specs["GARN"] = {"mu": 0.004, "sigma": 0.01, "gaps": [(150, 12)]}
    specs["ARVO"] = {"mu": 0.003, "sigma": 0.012, "gaps": [(230, 4)]}
    specs["EKTA"]["gaps"] = [(300, 20)]
    files["P2"] = price_file(rng, date(2025, 1, 6), 360, specs, blank_lines=(40, 200))
    # A takeover target pinned at its deal price (no movement at all), and a cheap name under the price floors.
    specs = plain_specs(rng, TICKERS[:6], mu=(-0.0005, 0.001))
    specs["DUQX"] = {"mu": 0.0, "sigma": 0.01, "pin": (60, 80, 0.35)}
    specs["CIRA"] = {"price": 8.0, "mu": 0.001, "sigma": 0.02}
    files["P3"] = price_file(rng, date(2025, 3, 3), 260, specs)
    # A crash that trips the drawdown control, across New Year 2025.
    specs = plain_specs(rng, TICKERS[:8], mu=(-0.0002, 0.0008))
    for spec in specs.values():
        spec["crash"] = (250, 10, 0.03)
    specs["IDX"] = {"price": 800.0, "mu": 0.0003, "sigma": 0.007, "crash": (250, 10, 0.025)}
    files["P4"] = price_file(rng, date(2024, 6, 3), 380, specs)
    # A bear market: everything falls.
    files["P5"] = price_file(rng, date(2025, 1, 6), 240, plain_specs(rng, TICKERS[:6], mu=(-0.004, -0.001)))
    # A short file: some warm-ups never end; a gap leaves a held name with no volatility for a while.
    specs = plain_specs(rng, TICKERS[:5])
    specs["CIRA"]["gaps"] = [(50, 7)]
    files["P6"] = price_file(rng, date(2026, 1, 5), 70, specs)
    # Across New Year 2026, a Thursday.
    specs = plain_specs(rng, TICKERS[:8], sigma=(0.01, 0.03))
    specs["BELK"]["gaps"] = [(70, 7)]
    specs["IDX"] = {"price": 120.0, "mu": 0.0001, "sigma": 0.01, "gaps": [(120, 3)]}
    files["P7"] = price_file(rng, date(2025, 10, 1), 200, specs)
    # A tiny file for the invalid configs.
    files["P8"] = price_file(rng, date(2026, 2, 2), 30, plain_specs(rng, TICKERS[:3]))
    return files


MOMENTUM_CONFIGS = [
    ("P1", {"signal": {"type": "momentum", "skip": 3, "lookback": 40}, "top_n": 4, "rebalance": "weekly",
            "max_weight": 0.3, "vol_target": 0.12, "max_leverage": 1.3, "benchmark": "IDX", "min_history": 90}),
    ("P2", {"signal": {"type": "momentum"}, "top_n": 2, "rebalance": "daily", "rebalance_band": 0.03,
            "commission_bps": 8.0, "min_commission": 150.0, "max_fill_gap": 3, "stop_loss": 0.06,
            "exclude": ["DUQX", "ZZZZ"]}),
    ("P4", {"signal": {"type": "momentum", "lookback": 30, "skip": 0}, "allow_short": True, "rebalance": "weekly",
            "drawdown_limit": 0.06, "drawdown_scale": 0.25, "borrow_bps": 120.0, "risk_free_rate": 0.03,
            "cash_rate": 0.035, "max_turnover": 0.4, "benchmark": "IDX"}),
    ("P3", {"signal": {"type": "momentum", "lookback": 50}, "initial_capital": 250000, "top_n": 1,
            "max_weight": 1.0, "min_price": 15.0, "slippage_bps": 6.5, "vol_target": 0.2, "vol_window": 30}),
    ("P6", {"signal": {"skip": 10, "type": "momentum"}, "allow_short": True, "vol_target": 0.08,
            "max_leverage": 2.5}),   # with a later start, the 60-day warm-up never ends: a run with no trade
    ("P7", {"signal": {"type": "momentum", "lookback": 25, "skip": 2}, "top_n": 5, "max_weight": 0.25,
            "rebalance": "weekly", "drawdown_limit": 0.05}),
]

REVERSION_CONFIGS = [
    ("P1", {"signal": {"type": "reversion", "window": 15}, "allow_short": True, "top_n": 3, "rebalance": "weekly",
            "vol_target": 0.1, "max_leverage": 2.0, "exclude": ["IDX"], "cash_rate": -0.01}),
    ("P2", {"signal": {"entry_z": 0.5, "type": "reversion", "window": 10}, "allow_short": True, "rebalance": "daily",
            "rebalance_band": 0.02, "min_commission": 60.0, "borrow_bps": 80.0, "max_fill_gap": 8,
            "stop_loss": 0.04, "max_turnover": 0.3}),
    ("P3", {"signal": {"type": "reversion"}, "initial_capital": 5000000.0, "top_n": 2, "min_price": 10.0,
            "rebalance": "daily", "commission_bps": 2.5, "slippage_bps": 1.0}),
    ("P4", {"signal": {"type": "reversion", "window": 25, "entry_z": 1.5}, "allow_short": True,
            "rebalance": "weekly", "vol_target": 0.15, "vol_window": 40, "drawdown_limit": 0.04,
            "drawdown_scale": 0.3, "risk_free_rate": 0.02, "benchmark": "IDX", "min_history": 200}),
    ("P6", {"signal": {"type": "reversion", "window": 8, "entry_z": 0}, "top_n": 2, "max_weight": 0.6,
            "rebalance": "daily", "vol_window": 5}),
    ("P7", {"signal": {"type": "reversion", "entry_z": 2}, "allow_short": True, "rebalance": "weekly",
            "vol_target": 0.12}),
]

INVALID_CONFIGS = [
    ("not_json", '{"top_n": 3,\n'),
    ("lookback_at_the_top", {"signal": {"type": "momentum"}, "lookback": 60}),
    ("signal_not_an_object", {"signal": "reversion"}),
    ("unknown_type", {"signal": {"type": "carry", "lookback": 20}}),
    ("no_type", {"signal": {"window": 15}}),
    ("type_capitalised", {"signal": {"type": "Momentum"}}),
    ("momentum_with_a_window", {"signal": {"type": "momentum", "lookback": 40, "window": 20}}),
    ("lookback_not_whole", {"signal": {"type": "momentum", "lookback": 60.0}}),
    ("skip_not_below_lookback", {"signal": {"type": "momentum", "lookback": 10, "skip": 10}}),
    ("window_of_one", {"signal": {"type": "reversion", "window": 1, "entry_z": 0.5}}),
    ("entry_z_negative_and_quarterly", {"rebalance": "quarterly", "signal": {"type": "reversion", "entry_z": -0.5}}),
    ("top_n_zero_and_unknown_parameter", {"top_n": 0, "signal": {"type": "momentum", "horizon": 5}}),
]

# Each strategy dropped in, on four inputs: (price file, config, options).
DROPPED_CONFIGS = {
    "channel": [
        ("P1", {"signal": {"type": "channel", "days": 25}, "allow_short": True, "rebalance": "weekly"}, "O1"),
        ("P4", {"signal": {"type": "channel"}, "top_n": 4, "vol_target": 0.1, "benchmark": "IDX"}, "O2"),
        ("P2", {"signal": {"neutral": 0.3, "type": "channel", "days": 15}, "allow_short": True,
                "rebalance": "daily"}, "O1"),
        ("P7", {"signal": {"type": "channel", "days": 60, "neutral": 0.0}}, "O3"),
    ],
    "pullback": [
        ("P1", {"signal": {"type": "pullback"}, "allow_short": True, "top_n": 3, "rebalance": "weekly"}, "O1"),
        ("P4", {"signal": {"type": "pullback", "lookback": 60, "recent": 5}, "allow_short": True,
                "drawdown_limit": 0.05}, "O2"),
        ("P2", {"signal": {"tilt": 1.0, "type": "pullback", "lookback": 120}, "rebalance": "weekly",
                "vol_target": 0.12, "exclude": ["GARN"]}, "O1"),
        ("P6", {"signal": {"type": "pullback", "lookback": 40, "recent": 20}, "rebalance": "daily"}, "O1"),
    ],
    "steady": [
        ("P1", {"signal": {"type": "steady"}, "top_n": 4, "min_history": 120, "benchmark": "IDX"}, "O1"),
        ("P3", {"signal": {"type": "steady", "days": 150}, "allow_short": True, "rebalance": "weekly"}, "O2"),
        ("P5", {"signal": {"floor": 0.0, "type": "steady", "days": 40}, "allow_short": True,
                "rebalance": "weekly"}, "O3"),
        ("P7", {"signal": {"type": "steady", "days": 30}, "rebalance": "weekly"}, "O1"),
    ],
    "breakout": [
        ("P1", {"signal": {"type": "breakout", "window": 30}, "allow_short": True, "rebalance": "daily",
                "stop_loss": 0.05}, "O1"),
        ("P4", {"signal": {"type": "breakout"}, "top_n": 2, "rebalance": "weekly"}, "O2"),
        ("P5", {"signal": {"margin": 0.01, "type": "breakout", "window": 20}, "allow_short": True,
                "rebalance": "daily"}, "O1"),
        ("P2", {"signal": {"type": "breakout", "window": 40, "margin": 0.02}, "rebalance": "weekly",
                "vol_target": 0.1}, "O3"),
    ],
}


# The built-ins swapped for changed versions (strategies/builtins/), on four inputs. Every parameter is given in
# the note's order, with no volatility target and no weekly schedule, so that only an engine that does not run the
# built-ins through their files differs here.
SWAPPED_CONFIGS = [
    ("P2", {"signal": {"type": "momentum", "lookback": 40, "skip": 3}, "top_n": 3, "rebalance": "monthly"}, "O1"),
    ("P3", {"signal": {"type": "momentum", "lookback": 30, "skip": 2}, "allow_short": True,
            "rebalance": "daily"}, "O2"),
    ("P2", {"signal": {"type": "reversion", "window": 12, "entry_z": 1.0}, "allow_short": True,
            "rebalance": "daily"}, "O1"),
    ("P5", {"signal": {"type": "reversion", "window": 20, "entry_z": 1.5}, "top_n": 2, "rebalance": "monthly"}, "O3"),
]


def options(name: str, dates: list[str]) -> list[str]:
    """The three option sets: the report, the equity curve and the trade log; the summary from a later start; the
    HTML page, the equity curve and the trade log over a window."""
    if name == "O1":
        return ["--equity", "equity.csv", "--trades", "trades.csv"]
    if name == "O2":
        return ["--format", "text", "--start", dates[25]]
    return ["--format", "html", "--start", dates[10], "--end", dates[-15], "--equity", "equity.csv", "--trades",
            "trades.csv"]


def case(name: str, prices: str, config, opts: list[str], strategy: str | None = None) -> dict:
    item = {"name": name, "prices": prices, "files": {"data/config.json": config_text(config)},
            "args": ["--prices", "data/prices.csv", "--config", "data/config.json", *opts]}
    if strategy:
        item["strategy"] = strategy
    return item


def hidden_cases(prices: dict[str, str]) -> tuple[list[dict], list[dict], list[dict]]:
    builtin, dropped, swapped = [], [], []
    for kind, configs in (("momentum", MOMENTUM_CONFIGS), ("reversion", REVERSION_CONFIGS)):
        for i, (file, config) in enumerate(configs, 1):
            for opt in ("O1", "O2", "O3"):
                builtin.append(case(f"{kind}{i}_{file}_{opt}", file, config, options(opt, file_dates(prices[file]))))
    for name, config in INVALID_CONFIGS:
        builtin.append(case(f"invalid_{name}", "P8", config, options("O1", file_dates(prices["P8"]))))
    for strategy, inputs in DROPPED_CONFIGS.items():
        for i, (file, config, opt) in enumerate(inputs, 1):
            dropped.append(case(f"{strategy}{i}_{file}_{opt}", file, config, options(opt, file_dates(prices[file])),
                                strategy))
    for i, (file, config, opt) in enumerate(SWAPPED_CONFIGS, 1):
        item = case(f"swapped{i}_{config['signal']['type']}_{file}_{opt}", file, config,
                    options(opt, file_dates(prices[file])))
        item["swap"] = True
        swapped.append(item)
    return builtin, dropped, swapped


# ----------------------------------------------------------------------------------------------------------------
# Running a tree (a bt package) on cases, in a subprocess, each case in a fresh folder
# ----------------------------------------------------------------------------------------------------------------

DRIVER = r'''
import contextlib, io, json, os, sys, tempfile, traceback
from pathlib import Path

tree, spec_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, tree)
spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
covered = set()
if spec.get("cover"):
    mon = sys.monitoring
    mon.use_tool_id(mon.COVERAGE_ID, "t16-proof")
    root = os.path.join(tree, "bt") + os.sep

    def on_line(code, line):
        if code.co_filename.startswith(root):
            covered.add((os.path.relpath(code.co_filename, tree), line))
        return mon.DISABLE

    mon.register_callback(mon.COVERAGE_ID, mon.events.LINE, on_line)
    mon.set_events(mon.COVERAGE_ID, mon.events.LINE)
from bt.cli import main

results = []
for item in spec["cases"]:
    with tempfile.TemporaryDirectory() as tmp:
        files = {"data/prices.csv": spec["prices"][item["prices"]], **item["files"]}
        for rel, text in files.items():
            path = Path(tmp) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    status = main(list(item["args"]))
                except SystemExit as exc:
                    status = exc.code
                except Exception:
                    traceback.print_exc()
                    status = 1
        finally:
            os.chdir("/")
        files = [Path(tmp) / name for name in ("equity.csv", "trades.csv")]
        results.append([status, out.getvalue(), err.getvalue(),
                        *[f.read_text(encoding="utf-8") if f.exists() else None for f in files]])
Path(out_path).write_text(json.dumps({"results": results, "covered": sorted(covered)}), encoding="utf-8")
'''


def run_tree(package: dict[str, str], cases: list[dict], prices: dict[str, str], seed: int = 0,
             strategies: dict[str, str] | None = None, cover: bool = False) -> tuple[list, list]:
    """(results, covered lines) of a bt package on the cases: results are [status, stdout, stderr, equity]."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        write_tree(tree, package)
        for name, text in (strategies or {}).items():
            write(tree / "bt" / "strategies" / f"{name}.py", text)
        spec, out = Path(tmp) / "spec.json", Path(tmp) / "out.json"
        spec.write_text(json.dumps({"cases": cases, "prices": prices, "cover": cover}), encoding="utf-8")
        proc = subprocess.run([sys.executable, "-I", "-c", DRIVER, str(tree), str(spec), str(out)],
                              env={**ENV, "PYTHONHASHSEED": str(seed)}, capture_output=True, text=True,
                              timeout=1200)
        assert proc.returncode == 0, proc.stderr[-2000:]
        data = json.loads(out.read_text(encoding="utf-8"))
    return data["results"], [tuple(x) for x in data["covered"]]


def run_tests(package: dict[str, str], restored: dict[str, str]) -> dict[str, str]:
    """The original tests, restored with their data, golden files and pytest.ini, run against a package.
    {test id: passed / failed / error / skipped}."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "app"
        write_tree(root, {**package, **restored})
        junit = Path(tmp) / "junit.xml"
        subprocess.run([sys.executable, "-I", "-m", "pytest", "-c", str(root / "pytest.ini"), f"--rootdir={root}",
                        "-o", "addopts=", "-p", "no:cacheprovider", f"--junitxml={junit}", "-q", str(root / "tests")],
                       cwd=root, env=ENV, capture_output=True, text=True, timeout=1200)
        if not junit.is_file():
            return {}
        report = ET.parse(junit).getroot()
    results = {}
    for item in report.iter("testcase"):
        status = "passed"
        for child in item:
            if child.tag in ("failure", "error", "skipped"):
                status = {"failure": "failed", "error": "error", "skipped": "skipped"}[child.tag]
        results[f"{item.get('classname')}::{item.get('name')}"] = status
    return results


def run_cli(package: dict[str, str], files: dict[str, str], args: list[str], strategies=None) -> tuple:
    """One real `python -m bt` run in a folder holding the package and files: (status, stdout, stderr, folder
    contents after the run)."""
    with tempfile.TemporaryDirectory() as tmp:
        write_tree(Path(tmp), {**package, **files})
        for name, text in (strategies or {}).items():
            write(Path(tmp) / "bt" / "strategies" / f"{name}.py", text)
        proc = subprocess.run([sys.executable, "-E", "-s", "-m", "bt", *args], cwd=tmp, capture_output=True,
                              text=True, env={**ENV, "PYTHONHASHSEED": "0"})
        produced = {p.name: p.read_text(encoding="utf-8") for p in Path(tmp).glob("*.csv")}
        return proc.returncode, proc.stdout, proc.stderr, produced


# ----------------------------------------------------------------------------------------------------------------
# The original with each strategy added the old way: the independent implementation behind the expected outputs
# ----------------------------------------------------------------------------------------------------------------

PLUG = '''

def _plugged(kind):
    """A strategy added the old way: its module, if bt/strategies/<kind>.py exists (generate.py's proof only)."""
    import importlib
    import pathlib
    if not isinstance(kind, str) or not kind.isidentifier():
        return None
    if not (pathlib.Path(__file__).resolve().parents[1] / "strategies" / f"{kind}.py").is_file():
        return None
    return importlib.import_module(f"bt.strategies.{kind}")


def _plugged_params(signal):
    module = _plugged(signal["type"])
    return {name: signal.get(name, default) for name, default in module.PARAMETERS.items()}
'''

PATCHED_ORIGINAL = [
    # 1. validation: a type that has a module passes, with its own parameter list
    ("bt/config/signal_params.py", '''    kind = signal.get("type")
    if kind not in SIGNAL_TYPES:
''', '''    kind = signal.get("type")
    if kind not in SIGNAL_TYPES and _plugged(kind) is not None:
        for key in signal:
            if key != "type" and key not in _plugged(kind).PARAMETERS:
                raise ConfigError(f"{where}: signal: {kind} has no parameter {key!r}")
        return
    if kind not in SIGNAL_TYPES:
'''),
    ("bt/config/signal_params.py", '''    return signal.get(name, SIGNAL_DEFAULTS[signal["type"]][name])
''', '''    if signal["type"] not in SIGNAL_TYPES:
        return _plugged_params(signal)[name]
    return signal.get(name, SIGNAL_DEFAULTS[signal["type"]][name])
'''),
    ("bt/config/signal_params.py", '''        if not is_number(entry_z) or entry_z < 0:
            raise ConfigError(f"{where}: signal.entry_z must be a number of at least 0")
''', '''        if not is_number(entry_z) or entry_z < 0:
            raise ConfigError(f"{where}: signal.entry_z must be a number of at least 0")
''' + PLUG),
    # 2. the warm-up
    ("bt/engine.py", '''    return signal.get("window", reversion.WINDOW)
''', '''    if signal["type"] != "reversion":
        from bt.config.signal_params import _plugged, _plugged_params
        return _plugged(signal["type"]).warmup(_plugged_params(signal))
    return signal.get("window", reversion.WINDOW)
'''),
    # 3. the scoring
    ("bt/signals/__init__.py", '''    kind = signal["type"]
    scores = {}
''', '''    kind = signal["type"]
    plugged = None
    if kind not in ("momentum", "reversion"):
        from bt.config.signal_params import _plugged, _plugged_params
        history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
        plugged = _plugged(kind).score(history, _plugged_params(signal))
    scores = {}
'''),
    ("bt/signals/__init__.py", '''        else:
            raise BacktestError(f"unknown signal type {kind!r}")
''', '''        else:
            scores[symbol] = plugged.get(symbol)
'''),
    # 4. the report's echo
    ("bt/report/json_report.py", '''    return dict(signal)
''', '''    from bt.config.signal_params import _plugged_params
    return {"type": kind, **_plugged_params(signal)}
'''),
    # 5. the summary's line
    ("bt/report/summary.py", '''    return f"Strategy: {kind}"
''', '''    from bt.config.signal_params import _plugged_params
    described = ", ".join(f"{name} {value}" for name, value in _plugged_params(signal).items())
    return f"Strategy: {kind} ({described})"
'''),
]


FILES_FIRST = [
    # 1. validation: a type with a file in bt/strategies/ is checked against that file's parameters
    ("bt/config/signal_params.py", '''    kind = signal.get("type")
    if kind not in SIGNAL_TYPES:
''', '''    kind = signal.get("type")
    if _plugged(kind) is not None:
        for key in signal:
            if key != "type" and key not in _plugged(kind).PARAMETERS:
                raise ConfigError(f"{where}: signal: {kind} has no parameter {key!r}")
        return
    if kind not in SIGNAL_TYPES:
'''),
    ("bt/config/signal_params.py", '''    return signal.get(name, SIGNAL_DEFAULTS[signal["type"]][name])
''', '''    if _plugged(signal["type"]) is not None:
        return _plugged_params(signal)[name]
    return signal.get(name, SIGNAL_DEFAULTS[signal["type"]][name])
'''),
    PATCHED_ORIGINAL[2],
    # 2. the warm-up
    ("bt/engine.py", '''    if signal["type"] == "momentum":
        return signal.get("lookback", momentum.LOOKBACK)
''', '''    from bt.config.signal_params import _plugged, _plugged_params
    if _plugged(signal["type"]) is not None:
        return _plugged(signal["type"]).warmup(_plugged_params(signal))
    if signal["type"] == "momentum":
        return signal.get("lookback", momentum.LOOKBACK)
'''),
    # 3. the scoring
    ("bt/signals/__init__.py", '''    kind = signal["type"]
    scores = {}
''', '''    kind = signal["type"]
    from bt.config.signal_params import _plugged, _plugged_params
    plugged = None
    if _plugged(kind) is not None:
        history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
        plugged = _plugged(kind).score(history, _plugged_params(signal))
    scores = {}
'''),
    ("bt/signals/__init__.py", '''            scores[symbol] = None
        elif kind == "momentum":
''', '''            scores[symbol] = None
        elif plugged is not None:
            scores[symbol] = plugged.get(symbol)
        elif kind == "momentum":
'''),
    # 4. the report's echo
    ("bt/report/json_report.py", '''    kind = signal["type"]
    if kind == "momentum":
        return {"type": "momentum",
''', '''    kind = signal["type"]
    from bt.config.signal_params import _plugged, _plugged_params
    if _plugged(kind) is not None:
        return {"type": kind, **_plugged_params(signal)}
    if kind == "momentum":
        return {"type": "momentum",
'''),
    # 5. the summary's line
    ("bt/report/summary.py", '''    kind = signal["type"]
    if kind == "momentum":
        return (f"Strategy: momentum''', '''    kind = signal["type"]
    from bt.config.signal_params import _plugged, _plugged_params
    if _plugged(kind) is not None:
        described = ", ".join(f"{name} {value}" for name, value in _plugged_params(signal).items())
        return f"Strategy: {kind} ({described})"
    if kind == "momentum":
        return (f"Strategy: momentum'''),
]


def apply_edits(files: dict[str, str], edits: list) -> dict[str, str]:
    files = dict(files)
    for rel, old, new in edits:
        assert files[rel].count(old) == 1, (rel, old)
        files[rel] = files[rel].replace(old, new)
    return files


def with_builtins_swapped(package: dict[str, str], texts: dict[str, str], append: bool = True) -> dict[str, str]:
    """The package with the changed built-ins put in as the swapped-built-ins check puts them: added at the end of
    bt/strategies/<name>.py, so their three names come last and win while every other name stays, or written as they
    are where the package has no such file. append=False copies them over the files (the check before 0.1.3)."""
    files = dict(package)
    for name, text in texts.items():
        rel = f"bt/strategies/{name}.py"
        files[rel] = files[rel] + "\n\n" + text if append and rel in files else text
    return files


# A right refactor laid out the other way round (second review A1): the momentum arithmetic lives in the strategy's
# file, and bt/signals/momentum.py, which bt/signals/__init__.py imports at start-up, re-exports it from there.
KEEPS_NAMES = [
    ("bt/strategies/momentum.py", '''from bt.signals.momentum import momentum_score
''', '''
LOOKBACK = 60    # days
SKIP = 5         # days


def momentum_score(series, t, lookback, skip):
    """Return from `lookback` days ago to `skip` days ago; None when either price is missing."""
    start = series[t - lookback]
    end = series[t - skip]
    if start is None or end is None:
        return None
    return end / start - 1.0

'''),
    ("bt/signals/momentum.py", '''LOOKBACK = 60    # days
SKIP = 5         # days


def momentum_score(series, t, lookback, skip):
    """Return from `lookback` days ago to `skip` days ago; None when either price is missing.
    (t >= lookback: the engine only asks after its warm-up.)"""
    start = series[t - lookback]
    end = series[t - skip]
    if start is None or end is None:
        return None
    return end / start - 1.0
''', '''from bt.strategies.momentum import LOOKBACK, SKIP, momentum_score  # one implementation, in the strategy's file
'''),
]


# ----------------------------------------------------------------------------------------------------------------
# The wrong solutions: edits on the reference (each one a lure of docs/job-plans/T16-PLAN.md)
# ----------------------------------------------------------------------------------------------------------------

WRONG = [
    {"script": "keeps_a_list", "name": "a slot whose engine still keeps a list of the two strategies",
     "edits": [("bt/strategies/__init__.py", '''    if not (FOLDER / f"{kind}.py").is_file():
''', '''    if kind not in ("momentum", "reversion") or not (FOLDER / f"{kind}.py").is_file():
''')],
     "fails": [CHECK_DROPPED]},
    {"script": "warmup_from_names", "name": "the warm-up still worked out from `lookback` or `window`",
     "edits": [("bt/engine.py", '''    strategy, params = configured(signal)
    return strategy.warmup(params)
''', '''    strategy, params = configured(signal)
    if "lookback" in params:
        return params["lookback"]
    return params.get("window", 20)
''')],
     "fails": [CHECK_DROPPED]},
    {"script": "history_by_day", "name": "history passed as a matrix by day (a list of {symbol: close}), the "
                                         "built-in strategies rewritten to read it",
     "edits": [("bt/signals/__init__.py", '''    history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
''', '''    history = [{symbol: prices[symbol][d] for symbol in symbols} for d in range(t + 1)]
'''), ("bt/strategies/momentum.py", '''    for symbol, closes in history.items():
''', '''    for symbol in history[-1]:
        closes = [day[symbol] for day in history]
'''), ("bt/strategies/reversion.py", '''    for symbol, closes in history.items():
''', '''    for symbol in history[-1]:
        closes = [day[symbol] for day in history]
''')],
     "fails": [CHECK_DROPPED, CHECK_BUILTINS]},
    {"script": "history_window", "name": "history cut to the last warm-up + 1 closes instead of everything since "
                                         "the run's first day",
     "edits": [("bt/signals/__init__.py", '''    history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
''', '''    first = max(0, t - strategy.warmup(params))
    history = {symbol: prices[symbol][first:t + 1] for symbol in symbols}
''')],
     "fails": [CHECK_DROPPED]},
    {"script": "history_without_today", "name": "history without today's close (the built-in strategies left as "
                                                "they are)",
     "edits": [("bt/signals/__init__.py", '''    history = {symbol: prices[symbol][:t + 1] for symbol in symbols}
''', '''    history = {symbol: prices[symbol][:t] for symbol in symbols}
''')],
     "fails": [CHECK_OUTPUT, CHECK_DROPPED, CHECK_BUILTINS, CHECK_TESTS]},
    {"script": "defaults_left_to_strategy", "name": "defaults left to each strategy: the engine passes only the "
                                                    "parameters the config gives",
     "edits": [("bt/signals/__init__.py", '''    strategy, params = configured(signal)
''', '''    strategy, params = configured(signal)
    params = {name: value for name, value in params.items() if name in signal}
'''), ("bt/engine.py", '''    strategy, params = configured(signal)
''', '''    strategy, params = configured(signal)
    params = {name: value for name, value in params.items() if name in signal}
'''), ("bt/strategies/momentum.py", '''def warmup(params):
    return params["lookback"]
''', '''def warmup(params):
    return params.get("lookback", PARAMETERS["lookback"])
'''), ("bt/strategies/momentum.py", '''    lookback = params["lookback"]
    skip = params["skip"]
    scores = {}
''', '''    lookback = params.get("lookback", PARAMETERS["lookback"])
    skip = params.get("skip", PARAMETERS["skip"])
    scores = {}
'''), ("bt/strategies/reversion.py", '''def warmup(params):
    return params["window"]
''', '''def warmup(params):
    return params.get("window", PARAMETERS["window"])
'''), ("bt/strategies/reversion.py", '''    window = params["window"]
    entry_z = params["entry_z"]
    scores = {}
''', '''    window = params.get("window", PARAMETERS["window"])
    entry_z = params.get("entry_z", PARAMETERS["entry_z"])
    scores = {}
''')],
     "fails": [CHECK_DROPPED]},
    {"script": "merged_std", "name": "the two rolling standard deviations merged into one (the volatility scale "
                                     "uses the scoring code's)",
     "edits": [("bt/portfolio/volatility.py", '''    total = 0.0
    for i in range(end, end - window, -1):
        value = returns[i]
        if value is None:
            return None
        total += value
    mean = total / window
    squares = 0.0
    for i in range(end, end - window, -1):
        deviation = returns[i] - mean
        squares += deviation * deviation
    return math.sqrt(squares / (window - 1))
''', '''    from bt.signals.stats import rolling_std
    return rolling_std(returns, end, window)
''')],
     "fails": [CHECK_OUTPUT, CHECK_DROPPED]},
    {"script": "sum_rewritten", "name": "a sum rewritten while the scoring code moves (reversion's mean as a loop "
                                        "for sum())",
     "edits": [("bt/signals/stats.py", '''    return sum(chunk) / window
''', '''    total = 0.0
    for value in chunk:
        total += value
    return total / window
''')],
     "fails": [CHECK_OUTPUT, CHECK_TESTS]},
    {"script": "validation_order", "name": "new validation that checks the signal after the other settings (a "
                                           "config with two problems reports the other one)",
     "edits": [("bt/config/validate.py", '''    config = merged(raw)

    check_signal(where, config["signal"])

''', '''    config = merged(raw)

'''), ("bt/config/validate.py", '''        raise ConfigError(f"{where}: cash_rate must be a number")
    return config
''', '''        raise ConfigError(f"{where}: cash_rate must be a number")
    check_signal(where, config["signal"])
    return config
''')],
     "fails": [CHECK_OUTPUT]},
    {"script": "echo_in_config_order", "name": "the report's echo rebuilt in the config's key order",
     "edits": [("bt/report/json_report.py", '''    return {"type": signal["type"], **signal_parameters(signal)}
''', '''    params = signal_parameters(signal)
    echo = {"type": signal["type"]}
    for name in signal:
        if name != "type":
            echo[name] = params[name]
    for name, value in params.items():
        echo.setdefault(name, value)
    return echo
''')],
     "fails": [CHECK_OUTPUT, CHECK_DROPPED]},
    {"script": "fixes_week_quirk", "name": "the week-number quirk fixed on the way (ISO year and week compared)",
     "edits": [("bt/data/calendar.py", '''    return today.isocalendar()[1] != before.isocalendar()[1] or today.year != before.year
''', '''    return today.isocalendar()[:2] != before.isocalendar()[:2]
''')],
     "fails": [CHECK_OUTPUT, CHECK_DROPPED]},
    {"script": "int_default", "name": "reversion's defaults taken from the scoring module's constants (entry_z 1, "
                                      "not the documented 1.0)",
     "edits": [("bt/strategies/reversion.py", '''from bt.signals.reversion import reversion_score

PARAMETERS = {"window": 20, "entry_z": 1.0}
''', '''from bt.signals.reversion import ENTRY_Z, WINDOW, reversion_score

PARAMETERS = {"window": WINDOW, "entry_z": ENTRY_Z}
''')],
     "fails": [CHECK_OUTPUT]},
    {"script": "drops_legacy", "name": "the 2021 runner deleted as dead code (one existing test imports it)",
     "edits": [], "remove": ["bt/legacy"],
     "fails": [CHECK_TESTS]},
    {"script": "hybrid", "name": "a hybrid: the two built-ins still special-cased in the five places, a branch for "
                                 "every other type added beside each (PATCHED_ORIGINAL)",
     "base": "original", "edits": PATCHED_ORIGINAL,
     "fails": [CHECK_BUILTINS]},
    {"script": "files_first", "name": "a hybrid the other way round: a type served from its file in bt/strategies/ "
                                      "first, the five special cases kept as the fallback, no files for the two "
                                      "built-ins (FILES_FIRST)",
     "base": "original", "edits": FILES_FIRST,
     "fails": [CHECK_BUILTINS]},
]


def wrong_package(reference: dict[str, str], original: dict[str, str], wrong: dict) -> dict[str, str]:
    files = apply_edits(original if wrong.get("base") == "original" else reference, wrong["edits"])
    for prefix in wrong.get("remove", []):
        files = {rel: text for rel, text in files.items() if not rel.startswith(prefix + "/")}
    return files


def cheat_script(wrong: dict) -> str:
    lines = ["#!/bin/bash", f"# {CANARY}", f"# A CHEAT (generate.py): {wrong['name']}.", "set -e"]
    if wrong.get("base") != "original":  # the reference with a few edits; else the room's own bt, edited
        lines += ["rm -rf /app/bt", "cp -r /solution/bt /app/bt"]
    if wrong["edits"]:
        edits = json.dumps([list(e) for e in wrong["edits"]])
        assert "'''" not in edits
        lines += ["python3 - <<'EOF'", "import json", "from pathlib import Path", "",
                  f"EDITS = json.loads(r'''{edits}''')", "for rel, old, new in EDITS:",
                  "    path = Path('/app') / rel", "    text = path.read_text(encoding='utf-8')",
                  "    assert text.count(old) == 1, (rel, old)",
                  "    path.write_text(text.replace(old, new), encoding='utf-8')", "EOF"]
    for prefix in wrong.get("remove", []):
        lines.append(f"rm -rf /app/{prefix}")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------------------------
# The proofs
# ----------------------------------------------------------------------------------------------------------------

def documented_settings() -> tuple[set[str], dict[str, set[str]]]:
    """The settings the README's tables document: (top-level settings, {signal type: parameters})."""
    readme = (APP / "README.md").read_text(encoding="utf-8")
    config_part = readme.split("## The config file", 1)[1].split("### Signals", 1)[0]
    settings = {line.split("`")[1] for line in config_part.splitlines() if line.startswith("| `")}
    signals_part = readme.split("### Signals", 1)[1].split("## Conventions", 1)[0]
    params: dict[str, set[str]] = {}
    kind = None
    for line in signals_part.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[1].startswith("`"):
            continue
        if cells[0].startswith("`"):
            kind = cells[0].strip("`")
        params.setdefault(kind, set()).add(cells[1].strip("`"))
    return settings, params


def check_hidden_configs() -> None:
    settings, params = documented_settings()
    namespace = {}
    exec((APP / "bt" / "config" / "defaults.py").read_text(encoding="utf-8"), namespace)
    defaults = {key: value for key, value in namespace["DEFAULTS"].items() if key != "signal"}
    assert set(defaults) | {"signal"} == settings
    for kind, configs in (("momentum", MOMENTUM_CONFIGS), ("reversion", REVERSION_CONFIGS)):
        assert len(configs) == 6
        used = set()
        given, left_out = set(), set()
        for _, config in configs:
            assert set(config) <= settings, (kind, set(config) - settings)
            assert config["signal"]["type"] == kind
            assert set(config["signal"]) - {"type"} <= params[kind], config
            used |= {key for key in config if key != "signal" and config[key] != defaults[key]}
            given |= set(config["signal"]) - {"type"}
            left_out |= params[kind] - set(config["signal"])
        assert used == set(defaults), (kind, "settings never used away from their default", set(defaults) - used)
        assert given == params[kind] == left_out, (kind, given, left_out)
    for strategy, inputs in DROPPED_CONFIGS.items():
        for _, config, _ in inputs:
            assert set(config) <= settings and config["signal"]["type"] == strategy
    served = {"channel", *DROPPED_CONFIGS}
    for name, config in INVALID_CONFIGS:
        if isinstance(config, dict) and isinstance(config.get("signal"), dict):
            assert config["signal"].get("type") not in served, name
        else:
            assert not any(f'"{s}"' in config_text(config) for s in served), name


# Lines of the original's engine-side modules that no hidden case runs, by (module, function, line), and why.
# Every other line runs.
NOT_SIGNAL = "a check on a plain setting, which the slot leaves alone; tests/test_config.py runs every message"
UNREACHED = {
    ("bt/signals/__init__.py", "compute_scores", 'raise BacktestError(f"unknown signal type {kind!r}")'):
        "validation refuses an unknown type before any scoring",
    ("bt/report/json_report.py", "signal_echo", "return dict(signal)"): "only the two types reach the report",
    ("bt/report/summary.py", "strategy_line", 'return f"Strategy: {kind}"'): "only the two types reach the summary",
    ("bt/cli.py", "main", "except OSError as exc:"): "no hidden case names a missing file (tests/test_cli.py does)",
    ("bt/cli.py", "main", "return 2"): "the return after a missing file (the one after a config problem runs)",
    ("bt/cli.py", "main", 'print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)'):
        "the same",
    ("bt/metrics/ratios.py", "sharpe_ratio", "return None"): "a run of two days; the visible tests run it",
    ("bt/metrics/ratios.py", "sortino_ratio", "return None"): "the same",
    ("bt/config/validate.py", "validate_config", 'raise ConfigError(f"{where}: the config must be a JSON object")'):
        NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config",
     "raise ConfigError(f\"{where}: rebalance must be one of {', '.join(REBALANCE_FREQUENCIES)}\")"): NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config",
     'raise ConfigError(f"{where}: {key} must be a whole number of at least {minimum}")'): NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config", 'raise ConfigError(f"{where}: allow_short must be true or false")'):
        NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config", 'raise ConfigError(f"{where}: {key} must be a positive number")'):
        NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config",
     'raise ConfigError(f"{where}: {key} must be a number of at least 0")'): NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config",
     'raise ConfigError(f"{where}: {key} must be a positive number or null")'): NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config",
     'raise ConfigError(f"{where}: drawdown_scale must be above 0 and at most 1")'): NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config",
     'raise ConfigError(f"{where}: stop_loss must be above 0 and below 1, or null")'): NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config", 'raise ConfigError(f"{where}: exclude must be a list of symbols")'):
        NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config", 'raise ConfigError(f"{where}: benchmark must be a symbol or null")'):
        NOT_SIGNAL,
    ("bt/config/validate.py", "validate_config", 'raise ConfigError(f"{where}: cash_rate must be a number")'):
        NOT_SIGNAL,
    ("bt/metrics/benchmark.py", "total_return", "return None"):
        "a benchmark with fewer than two closes in the period; tests/test_benchmark.py runs it",
    ("bt/metrics/benchmark.py", "capture", "return None"): "the same, for a benchmark that never rises or falls",
    ("bt/metrics/benchmark.py", "benchmark_metrics", "return figures"): "the same, for fewer than two paired days",
    ("bt/report/trades.py", "trades_by_symbol", "counts = {}"):
        "a helper nothing in the program calls (tests/test_report.py does)",
    ("bt/report/trades.py", "trades_by_symbol", "for trade in trades:"): "the same",
    ("bt/report/trades.py", "trades_by_symbol", 'counts[trade["symbol"]] = counts.get(trade["symbol"], 0) + 1'):
        "the same",
    ("bt/report/trades.py", "trades_by_symbol", "return counts"): "the same",
}
COVERED_MODULES = ("bt/config/", "bt/signals/", "bt/portfolio/", "bt/execution/", "bt/metrics/", "bt/report/",
                   "bt/engine.py", "bt/cli.py")


def code_lines(package: dict[str, str]) -> dict[tuple[str, int], str]:
    """{(module, line): the function it is in} for every line of code in the covered modules' functions."""
    lines = {}
    for rel, text in package.items():
        if not rel.endswith(".py") or not rel.startswith(COVERED_MODULES):
            continue
        stack = [compile(text, rel, "exec")]
        while stack:
            code = stack.pop()
            stack += [c for c in code.co_consts if hasattr(c, "co_code")]
            if code.co_name == "<module>":
                continue
            for _, _, line in code.co_lines():
                if line is not None and line != code.co_firstlineno:
                    lines[(rel, line)] = code.co_qualname
    return lines


def check_coverage(original: dict[str, str], covered: list) -> None:
    lines = code_lines(original)
    ran = set(covered)
    unreached = set()
    problems = []
    for (rel, line), function in sorted(lines.items()):
        if (rel, line) in ran:
            continue
        key = (rel, function, original[rel].splitlines()[line - 1].strip())
        if key in UNREACHED:
            unreached.add(key)
        else:
            problems.append(f"{rel} line {line} ({function}): {key[2]}")
    assert not problems, ("no hidden case runs these lines of the original", problems)
    assert unreached == set(UNREACHED), ("UNREACHED lists lines that do run", set(UNREACHED) - unreached)


def differs(results_a: list, results_b: list) -> bool:
    return any(a != b for a, b in zip(results_a, results_b, strict=True))


def first_difference(results_a, results_b, cases) -> str:
    for a, b, item in zip(results_a, results_b, cases):
        if a != b:
            for part, x, y in zip(("status", "stdout", "stderr", "equity", "trades"), a, b):
                if x != y:
                    return f"{item['name']}: {part}: {str(x)[:300]!r} != {str(y)[:300]!r}"
    return "no difference"


def check_wrong(wrong, package, builtin, dropped, swapped, prices, strategies, builtins_swapped, want_builtin,
                want_dropped, want_swapped, restored, want_tests) -> tuple[str, list[str]]:
    got_builtin, _ = run_tree(package, builtin, prices)
    got_dropped, _ = run_tree(package, dropped, prices, strategies=strategies)
    got_swapped, _ = run_tree(with_builtins_swapped(package, builtins_swapped), swapped, prices)
    tests = run_tests(package, restored)
    missing = [f"bt/strategies/{name}.py" for name in builtins_swapped if f"bt/strategies/{name}.py" not in package]
    failed = []
    if differs(got_builtin, want_builtin):
        failed.append(CHECK_OUTPUT)
    if differs(got_dropped, want_dropped):
        failed.append(CHECK_DROPPED)
    if missing or differs(got_swapped, want_swapped):   # the check's first step: the two files are in the package
        failed.append(CHECK_BUILTINS)
    failing_tests = [t for t in want_tests if tests.get(t) != "passed"]
    if set(tests) != set(want_tests) or failing_tests:
        failed.append(CHECK_TESTS)
    moved = (sum(a != b for a, b in zip(got_builtin, want_builtin)), sum(a != b for a, b in zip(got_dropped, want_dropped)),
             sum(a != b for a, b in zip(got_swapped, want_swapped)), len(failing_tests))
    return wrong["script"], (failed, moved, missing)


# ----------------------------------------------------------------------------------------------------------------

def main(root: Path) -> None:
    rng = random.Random(SEED)
    sample_files = sample(rng)
    example_files = example(rng)
    prices = hidden_prices(rng)
    builtin, dropped, swapped = hidden_cases(prices)
    assert len(builtin) == 6 * 3 * 2 + 12 and len(dropped) == 16 and len(swapped) == 4
    every = builtin + dropped + swapped
    assert len({c["name"] for c in every}) == len(every)
    check_hidden_configs()

    room = read_tree(APP, "bt")
    room_tests = {rel: text for rel, text in read_tree(APP, "tests").items() if rel.endswith(".py")}
    reference = read_tree(SOLUTION, "bt")
    strategies = {"channel": (APP / "examples" / "strategies" / "channel.py").read_text(encoding="utf-8")}
    for path in sorted(HIDDEN_STRATEGIES.glob("*.py")):
        strategies[path.stem] = path.read_text(encoding="utf-8")
    assert set(strategies) == set(DROPPED_CONFIGS)
    builtins_swapped = {path.stem: path.read_text(encoding="utf-8") for path in sorted(BUILTIN_STRATEGIES.glob("*.py"))}
    assert set(builtins_swapped) == {"momentum", "reversion"}
    for name, text in builtins_swapped.items():  # the note's three names and the built-ins' own parameters
        namespace = {}
        exec(text, namespace)
        assert {"PARAMETERS", "warmup", "score"} <= set(namespace) and "check" not in namespace
        line = next(line for line in reference[f"bt/strategies/{name}.py"].splitlines()
                    if line.startswith("PARAMETERS = "))
        assert namespace["PARAMETERS"] == eval(line.split(" = ", 1)[1]), name
    patched = apply_edits(room, PATCHED_ORIGINAL)
    files_first = apply_edits(room, FILES_FIRST)
    keeps_names = apply_edits(reference, KEEPS_NAMES)
    assert not any(f"bt/strategies/{name}.py" in files_first for name in builtins_swapped)

    # The visible sample's golden files: the original's own output on it.
    sample_root = {f"tests/data/{name}": text for name, text in sample_files.items()}
    golden = {}
    for kind in ("momentum", "reversion"):
        args = ["--prices", "tests/data/prices.csv", "--config", f"tests/data/{kind}.json"]
        status, out, err, produced = run_cli(room, sample_root, [*args, "--equity", "equity.csv", "--trades",
                                                                  "trades.csv"])
        assert status == 0, err
        golden[f"{kind}_report.json"], golden[f"{kind}_equity.csv"] = out, produced["equity.csv"]
        if kind == "momentum":
            golden["momentum_trades.csv"] = produced["trades.csv"]
        golden["sample_warnings.txt"] = err
        status, out, err2, _ = run_cli(room, sample_root, [*args, "--format", "text"])
        assert status == 0 and err2 == err
        golden[f"{kind}_summary.txt"] = out
    assert golden["sample_warnings.txt"].startswith("warning: GARN")
    assert json.loads(golden["momentum_report.json"])["metrics"]["forced_exits"] >= 1
    restored = {**sample_root, **{f"tests/golden/{name}": text for name, text in golden.items()},
                **room_tests, "pytest.ini": (APP / "pytest.ini").read_text(encoding="utf-8")}

    # The example's expected output: the reference with the example dropped in.
    example_root = {f"examples/{name}": text for name, text in example_files.items()}
    expected = {}
    for args, label in zip(EXAMPLE_ARGS, ("report.json", "summary.txt")):
        status, out, err, produced = run_cli(reference, example_root, args, {"channel": strategies["channel"]})
        assert status == 0 and err == "", err
        expected[label] = out
        if "equity.csv" in produced:
            expected["equity.csv"] = produced["equity.csv"]
    for other in (patched,):
        for args, label in zip(EXAMPLE_ARGS, ("report.json", "summary.txt")):
            assert run_cli(other, example_root, args, {"channel": strategies["channel"]})[1] == expected[label]
    status, _, err, _ = run_cli(room, example_root, EXAMPLE_ARGS[0])
    assert status == 2 and err == "error: examples/channel.json: unknown signal type 'channel'\n", err

    # Run everything.
    jobs = {
        "original": lambda: run_tree(room, builtin, prices, cover=True),
        "original_dropped": lambda: run_tree(room, dropped, prices, strategies=strategies),
        "reference0": lambda: run_tree(reference, builtin, prices, seed=0),
        "reference1": lambda: run_tree(reference, builtin, prices, seed=1),
        "reference_dropped0": lambda: run_tree(reference, dropped, prices, seed=0, strategies=strategies),
        "reference_dropped1": lambda: run_tree(reference, dropped, prices, seed=1, strategies=strategies),
        "patched_dropped": lambda: run_tree(patched, dropped, prices, strategies=strategies),
        "files_first_dropped": lambda: run_tree(files_first, dropped, prices, strategies=strategies),
        "files_first_builtin": lambda: run_tree(files_first, builtin, prices),
        "reference_unswapped": lambda: run_tree(reference, swapped, prices),
        "reference_swapped0": lambda: run_tree(with_builtins_swapped(reference, builtins_swapped), swapped, prices,
                                               seed=0),
        "reference_swapped1": lambda: run_tree(with_builtins_swapped(reference, builtins_swapped), swapped, prices,
                                               seed=1),
        "reference_copied_over": lambda: run_tree(with_builtins_swapped(reference, builtins_swapped, append=False),
                                                  swapped, prices),
        "files_first_swapped": lambda: run_tree(with_builtins_swapped(files_first, builtins_swapped), swapped,
                                                prices),
        "original_swapped": lambda: run_tree(with_builtins_swapped(room, builtins_swapped), swapped, prices),
        "tests_original": lambda: run_tests(room, restored),
        "tests_reference": lambda: run_tests(reference, restored),
    }
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        done = {name: future.result() for name, future in futures.items()}
    original, covered = done["original"]
    want_dropped = done["reference_dropped0"][0]

    assert all(r[0] in (0, 2) for r in original)
    assert [r[0] for r in original].count(2) == len(INVALID_CONFIGS)
    for r, item in zip(original, builtin):
        if item["name"].startswith("invalid_"):
            assert r[0] == 2 and r[1] == "" and r[2].startswith("error: data/config.json: ") and r[3:] == [None, None], r
    assert done["reference0"][0] == original, first_difference(done["reference0"][0], original, builtin)
    assert done["reference1"][0] == original, first_difference(done["reference1"][0], original, builtin)
    assert done["reference_dropped1"][0] == want_dropped
    assert all(r[0] == 0 for r in want_dropped), [(c["name"], r[2][-300:]) for r, c in zip(want_dropped, dropped)
                                                  if r[0] != 0]
    assert done["patched_dropped"][0] == want_dropped, first_difference(done["patched_dropped"][0], want_dropped,
                                                                        dropped)
    assert done["files_first_dropped"][0] == want_dropped, first_difference(done["files_first_dropped"][0],
                                                                            want_dropped, dropped)
    assert done["files_first_builtin"][0] == original
    want_swapped = done["reference_swapped0"][0]
    assert all(r[0] == 0 for r in want_swapped)
    assert done["reference_swapped1"][0] == want_swapped
    assert done["reference_copied_over"][0] == want_swapped, first_difference(done["reference_copied_over"][0],
                                                                              want_swapped, swapped)
    assert done["files_first_swapped"][0] == want_swapped, first_difference(done["files_first_swapped"][0],
                                                                            want_swapped, swapped)
    assert all(a != b for a, b in zip(want_swapped, done["reference_unswapped"][0])), \
        "a swapped case prints what the reference prints without the swap"
    tests_original = done["tests_original"]
    assert len(tests_original) >= 100, len(tests_original)
    assert set(tests_original.values()) == {"passed"}, {k: v for k, v in tests_original.items() if v != "passed"}
    assert done["tests_reference"] == tests_original, {k: v for k, v in done["tests_reference"].items()
                                                       if v != "passed"}
    check_coverage(room, covered)

    # Doing nothing: the original refuses every dropped-in strategy and ignores the swapped built-ins.
    assert all(r[0] == 2 and "unknown signal type" in r[2] for r in done["original_dropped"][0])
    assert done["original_swapped"][0] == done["reference_unswapped"][0]

    # Each wrong solution changes exactly what it declares; the right refactor that keeps other names in the
    # built-ins' files (KEEPS_NAMES) fails nothing.
    right = {"script": "keeps_names", "fails": []}
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(check_wrong, w, wrong_package(reference, room, w), builtin, dropped, swapped, prices,
                               strategies, builtins_swapped, original, want_dropped, want_swapped, restored,
                               tests_original) for w in WRONG]
        futures.append(pool.submit(check_wrong, right, keeps_names, builtin, dropped, swapped, prices, strategies,
                                   builtins_swapped, original, want_dropped, want_swapped, restored, tests_original))
        outcomes = dict(f.result() for f in futures)
    for wrong in [*WRONG, right]:
        failed, moved, missing = outcomes[wrong["script"]]
        assert failed == wrong["fails"], (wrong["script"], failed, moved, missing)
        if "--verbose" in sys.argv:
            print(f"  {wrong['script']}: {moved[0]} of {len(builtin)} built-in cases, {moved[1]} of {len(dropped)} "
                  f"dropped-in cases, {moved[2]} of {len(swapped)} swapped cases and {moved[3]} visible tests differ"
                  + (f"; not in the package: {', '.join(missing)}" if missing else ""))
    # FILES_FIRST fails the swapped check only at its first step: with the changed files written in, it prints the
    # reference's output on every swapped case (proved above), but it ships neither built-in file.
    assert outcomes["files_first"][2] == [f"bt/strategies/{name}.py" for name in builtins_swapped]
    assert outcomes["files_first"][1][2] == 0
    # KEEPS_NAMES with the changed built-ins copied over its files (the check before 0.1.3) dies at start-up.
    item = swapped[0]
    status, _, err, _ = run_cli(with_builtins_swapped(keeps_names, builtins_swapped, append=False),
                                {"data/prices.csv": prices[item["prices"]], **item["files"]}, item["args"])
    assert status == 1 and "ImportError" in err, (status, err[-300:])

    # Write.
    for name, text in sample_files.items():
        write(root / "environment" / "app" / "tests" / "data" / name, text)
    for name, text in golden.items():
        write(root / "environment" / "app" / "tests" / "golden" / name, text)
    for name, text in example_files.items():
        write(root / "environment" / "app" / "examples" / name, text)
    for name, text in expected.items():
        write(root / "environment" / "app" / "examples" / "expected" / name, text)
    write(root / "tests" / "original" / "bundle.json",
          json.dumps({"_canary": CANARY, "files": {**room, **restored}}, indent=1) + "\n")
    write(root / "tests" / "reference" / "bundle.json",
          json.dumps({"_canary": CANARY, "files": reference}, indent=1) + "\n")
    write(root / "tests" / "data" / "cases.json",
          json.dumps({"_canary": CANARY, "prices": prices, "strategies": strategies, "builtins": builtins_swapped,
                      "builtin": builtin, "dropped": dropped, "swapped": swapped}, indent=1) + "\n")
    for wrong in WRONG:
        path = root / "cheats" / f"{wrong['script']}.sh"
        write(path, cheat_script(wrong))
        with contextlib.suppress(OSError):
            path.chmod(0o755)
    print(f"{len(builtin)} built-in, {len(dropped)} dropped-in and {len(swapped)} swapped cases; the reference "
          f"agrees with the original and with the old way; {len(tests_original)} visible tests pass on both; every engine-side "
          f"line runs but {len(UNREACHED)}; {len(WRONG)} wrong solutions fail as declared; a right refactor that "
          f"keeps other names in the built-ins' files fails nothing")


if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if a != "--verbose"]
    main(Path(arguments[0]) if arguments else HERE)
