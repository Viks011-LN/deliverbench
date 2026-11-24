"""What differs between two JSON reports: python -m bt.tools.compare A.json B.json [--tolerance X]

Prints one line per difference, with the path to it ("metrics.sharpe: 1.0 != 1.1", "drawdowns[0].trough: ..."),
then how many there are. Keys must come in the same order (the report's order is part of it). Numbers must be the
same number of the same JSON kind (1 and 1.0 differ), unless --tolerance is given, when two numbers within it of
each other count as the same.

Exit status: 0 if the reports are the same, 1 if they differ, 2 if a file cannot be read or is not JSON.

The desk uses it to check that a change to the code moved nothing: run the program before and after the change on
the same inputs, then compare the two reports with no tolerance.
"""
import argparse
import json
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def same_number(a, b, tolerance):
    if tolerance > 0.0:
        return abs(a - b) <= tolerance
    return a == b and type(a) is type(b)


def differences(a, b, path="", tolerance=0.0):
    """Every difference between two parsed JSON values, as "path: what" lines, in the order of `a`."""
    where = path or "(top)"
    if isinstance(a, dict) and isinstance(b, dict):
        found = []
        if list(a) != list(b):
            found.append(f"{where}: keys {list(a)} != {list(b)}")
        for key in a:
            if key in b:
                found += differences(a[key], b[key], f"{path}.{key}" if path else key, tolerance)
        return found
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{where}: {len(a)} items != {len(b)} items"]
        found = []
        for i, (x, y) in enumerate(zip(a, b)):
            found += differences(x, y, f"{path}[{i}]", tolerance)
        return found
    if is_number(a) and is_number(b):
        return [] if same_number(a, b, tolerance) else [f"{where}: {json.dumps(a)} != {json.dumps(b)}"]
    if a == b and type(a) is type(b):
        return []
    return [f"{where}: {json.dumps(a)} != {json.dumps(b)}"]


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.compare", description="Compare two JSON reports.")
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--tolerance", type=float, default=0.0, help="numbers this close count as the same")
    args = parser.parse_args(argv)
    try:
        first = load(args.first)
        second = load(args.second)
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: not valid JSON ({exc.msg}, line {exc.lineno})", file=sys.stderr)
        return 2
    found = differences(first, second, tolerance=args.tolerance)
    for line in found:
        print(line)
    print(f"{len(found)} difference(s)" if found else "the reports are the same")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
