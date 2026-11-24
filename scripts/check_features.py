#!/usr/bin/env python3
"""The only thing allowed to mark a feature pass or fail.

    check_features.py              list features, with a "stale" flag when the evidence is from an older commit
    check_features.py --run F01    run F01's verify command and record pass or fail with evidence
    check_features.py --run all    run every feature that has started
    check_features.py --start F02  mark F02 in-progress (refused if another feature is in progress)

Evidence records the commit, the date (no time of day), the exit code and the last output line.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "features.json"
STATUSES = {"not-started", "in-progress", "pass", "fail"}
REQUIRED = {"id", "feature", "done_when", "verify", "status", "evidence"}
TIMEOUT = 3600  # a feature may set its own "timeout_sec" (a heavy job's full selftest takes hours)


def load() -> dict:
    data = json.loads(FILE.read_text(encoding="utf-8"))
    ids = [f["id"] for f in data["features"]]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("duplicate feature ids")
    for f in data["features"]:
        missing = REQUIRED - f.keys()
        if missing:
            problems.append(f"{f.get('id', '?')}: missing {sorted(missing)}")
        if f.get("status") not in STATUSES:
            problems.append(f"{f.get('id', '?')}: unknown status {f.get('status')!r}")
    if sum(f["status"] == "in-progress" for f in data["features"]) > 1:
        problems.append("more than one feature is in-progress (WIP must be 1)")
    if problems:
        sys.exit("features.json is invalid:\n  " + "\n  ".join(problems))
    return data


def save(data: dict) -> None:
    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def head() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    return sha + ("-dirty" if dirty else "")


def redact(text: str) -> str:
    """Keep paths and the user name out of evidence that gets committed."""
    for value, placeholder in ((str(Path.home()), "~"), (getpass.getuser(), "<user>")):
        if value:
            text = text.replace(value, placeholder)
    return text


def run(feature: dict) -> None:
    limit = int(feature.get("timeout_sec", TIMEOUT))
    print(f"== {feature['id']}: {feature['verify']}")
    try:
        proc = subprocess.run(feature["verify"], cwd=ROOT, shell=True, capture_output=True, text=True,
                              timeout=limit, env={**os.environ, "HARBOR_TELEMETRY": "0"})
        code = proc.returncode
        # Prefer the command's own output for the evidence line; tools like Harbor log to stderr.
        output = proc.stdout if proc.stdout.strip() else proc.stderr
        if code != 0:
            output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        code, output = -1, f"timed out after {limit} s"
    lines = [line for line in output.strip().splitlines() if line.strip()]
    last = redact(lines[-1].strip() if lines else "(no output)")[:200]
    feature["status"] = "pass" if code == 0 else "fail"
    feature["evidence"] = {"commit": head(), "date": dt.date.today().isoformat(), "exit_code": code, "last_line": last}
    print(f"   {feature['status'].upper()}: {last}")
    if code != 0:
        print("\n".join(redact(line) for line in lines[-30:]))


def is_stale(evidence: dict) -> bool:
    """Stale when anything other than bookkeeping and write-ups (features.json, STATUS.md, docs/, and this
    checker itself, which only runs the verify commands) changed since the evidence commit."""
    commit = evidence.get("commit", "").removesuffix("-dirty")
    if not commit:
        return True
    changed = subprocess.run(
        ["git", "diff", "--name-only", commit, "--", ".", ":!features.json", ":!STATUS.md", ":!docs",
         ":!scripts/check_features.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return changed.returncode != 0 or bool(changed.stdout.strip())


def show(data: dict) -> None:
    for f in data["features"]:
        ev = f["evidence"] or {}
        stale = " (stale: code changed since this evidence)" if ev and is_stale(ev) else ""
        print(f"{f['id']}  {f['status']:<12} {f['feature'][:80]}{stale}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", nargs="+", metavar="ID")
    parser.add_argument("--start", metavar="ID")
    args = parser.parse_args()
    data = load()
    by_id = {f["id"]: f for f in data["features"]}
    if args.start:
        if any(f["status"] == "in-progress" and f["id"] != args.start for f in data["features"]):
            sys.exit("another feature is already in progress; finish it first (WIP = 1)")
        by_id[args.start]["status"] = "in-progress"
        save(data)
    elif args.run:
        targets = [f for f in data["features"] if f["status"] != "not-started"] if args.run == ["all"] \
            else [by_id[i] for i in args.run]
        for f in targets:
            run(f)
        save(data)
        return 0 if all(f["status"] == "pass" for f in targets) else 1
    show(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
