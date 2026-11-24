"""Every setting of the config file with its default: python -m bt.tools.settings [--json]

A table of setting, default (as JSON) and a one-line description, in the order of bt/config/defaults.py; with
--json, the defaults as a config file that sets every one of them explicitly (a starting point for a new desk).
"""
import argparse
import json
import sys

from bt.config.defaults import DEFAULTS
from bt.config.descriptions import DESCRIPTIONS


def table():
    """The table's lines."""
    width = max(len(key) for key in DEFAULTS) + 2
    lines = [f"{'setting':<{width}}{'default':<24}description"]
    for key, default in DEFAULTS.items():
        lines.append(f"{key:<{width}}{json.dumps(default):<24}{DESCRIPTIONS[key]}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.settings", description="List every setting.")
    parser.add_argument("--json", action="store_true", help="print the defaults as a config file")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(DEFAULTS, indent=2))
    else:
        print("\n".join(table()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
