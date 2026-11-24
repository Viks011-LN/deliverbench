#!/usr/bin/env python3
"""Copy templates/verifier/ (test.sh, Dockerfile, sandbox.py) into every job's tests/, each with the job's canary
line. dbench's job validator refuses a job whose copies differ from the templates (canary lines aside).

    scripts/sync_verifier_kit.py            update every job under tasks/
    scripts/sync_verifier_kit.py --check    report differences only (exit 1 if any)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dbench.tasks import VERIFIER_KIT, job_canary, job_folders, kit_copy  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    differing = []
    for job in job_folders(ROOT / "tasks"):
        guid = job_canary(job)
        for name in VERIFIER_KIT:
            target = job / "tests" / name
            wanted = kit_copy(name, guid)
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current == wanted:
                continue
            differing.append(str(target.relative_to(ROOT)))
            if not args.check:
                target.write_text(wanted, encoding="utf-8", newline="\n")
                if name.endswith(".sh"):
                    target.chmod(0o755)
    for path in differing:
        print(("differs: " if args.check else "updated: ") + path)
    return 1 if args.check and differing else 0


if __name__ == "__main__":
    sys.exit(main())
