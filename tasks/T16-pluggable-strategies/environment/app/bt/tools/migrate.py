"""A bt 3.x config in today's layout: python -m bt.tools.migrate OLD.json

Prints the migrated config as JSON (two-space indent) on stdout; it is not checked, so run it through
`python -m bt` before using it. A config that cannot be migrated without guessing is refused with "error: ..." and
exit status 2. See bt/legacy/config_v3.py for what changed.
"""
import argparse
import json
import sys

from bt.legacy.config_v3 import MigrationError, migrate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bt.tools.migrate", description="Migrate a bt 3.x config.")
    parser.add_argument("config")
    args = parser.parse_args(argv)
    try:
        with open(args.config, encoding="utf-8") as handle:
            old = json.load(handle)
        new = migrate(old)
    except OSError as exc:
        print(f"error: cannot open {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {args.config}: not valid JSON ({exc.msg}, line {exc.lineno})", file=sys.stderr)
        return 2
    except MigrationError as exc:
        print(f"error: {args.config}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(new, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
