"""One config over several values of one setting:

    python -m bt.tools.sweep --prices P.csv --config C.json --set KEY=V1,V2,... [--start D] [--end D]

KEY is a setting (`top_n`) or a parameter of the signal (`signal.lookback`); each value is read as JSON (`20`,
`0.5`, `true`, `null`, `"weekly"`). Every run is checked and run exactly as `python -m bt` would run the config with
that one value changed, and prints one line: the value, total return, annual volatility, Sharpe, max drawdown and
trades. A value the config check refuses gets its message on that line instead, and the sweep goes on.
"""
import argparse
import copy
import json
import sys

from bt.config.loader import read_json
from bt.config.validate import validate_config
from bt.data import apply_window, load_prices
from bt.data.benchmark import split_benchmark
from bt.engine import run_backtest
from bt.errors import BacktestError, ConfigError
from bt.metrics import compute_metrics
from bt.report.formatting import percent, ratio


def parse_setting(text):
    """KEY=V1,V2,... as (["signal", "lookback"], [values]). Values are JSON, split on commas outside quotes."""
    if "=" not in text:
        raise BacktestError(f"--set {text!r}: expected KEY=VALUE,VALUE,...")
    key, _, values = text.partition("=")
    path = key.strip().split(".")
    if len(path) > 2 or (len(path) == 2 and path[0] != "signal") or not all(path):
        raise BacktestError(f"--set {text!r}: KEY is a setting or signal.<parameter>")
    try:
        parsed = json.loads(f"[{values}]")
    except json.JSONDecodeError:
        raise BacktestError(f"--set {text!r}: the values must be JSON, separated by commas") from None
    if not parsed:
        raise BacktestError(f"--set {text!r}: no values")
    return path, parsed


def with_value(raw, path, value):
    """A copy of the raw config with one setting (or signal parameter) set."""
    changed = copy.deepcopy(raw)
    if len(path) == 1:
        changed[path[0]] = value
    else:
        signal = changed.get("signal")
        if not isinstance(signal, dict):
            signal = {"type": "momentum"}
        signal = dict(signal)
        signal[path[1]] = value
        changed["signal"] = signal
    return changed


def run_one(label, raw, dates, symbols, prices, prices_path):
    """One run's line of the table."""
    try:
        config = validate_config(label, raw)
        traded, traded_prices, _ = split_benchmark(prices_path, config, symbols, prices)
    except ConfigError as exc:
        return f"refused: {exc}"
    except BacktestError as exc:
        return f"refused: {exc}"
    result = run_backtest(dates, traded, traded_prices, config)
    m = compute_metrics(result["curve"], result["stats"], config)
    return (f"{percent(m['total_return']):>10}{percent(m['annual_volatility']):>10}{ratio(m['sharpe']):>8}"
            f"{percent(m['max_drawdown']):>10}{m['trades']:>8}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.sweep", description="Sweep one setting.")
    parser.add_argument("--prices", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--set", required=True, dest="setting", help="KEY=V1,V2,... (KEY may be signal.<name>)")
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args(argv)
    try:
        path, values = parse_setting(args.setting)
        dates, symbols, prices = load_prices(args.prices)
        raw = read_json(args.config)
        dates, prices = apply_window(dates, symbols, prices, args.start, args.end)
    except BacktestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    key = ".".join(path)
    print(f"{key:<16}{'return':>10}{'vol':>10}{'sharpe':>8}{'max dd':>10}{'trades':>8}")
    for value in values:
        label = f"{args.config} with {key}={json.dumps(value)}"
        print(f"{json.dumps(value):<16}" + run_one(label, with_value(raw, path, value), dates, symbols, prices,
                                                    args.prices))
    return 0


if __name__ == "__main__":
    sys.exit(main())
