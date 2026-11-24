#!/usr/bin/env python3
"""Write each job's integrity cheats (selftest probes of the room and the verifier).

  cheats/plant.sh   every job: does no work; plants a passing junit report and reward in the folders Harbor
                    shares with the room, plus links that would lead a runner outside the trial folder.
                    Must fail exactly like doing nothing.
  cheats/tamper.sh  jobs whose checks run the agent's code (runs_agent_code): installs code that, when the
                    checks run it, tries to read the hidden checks (and only then behaves correctly) and leaves a
                    process that keeps writing a passing grade. Must fail its declared checks.

    scripts/make_integrity_cheats.py            write them for every job under tasks/
    scripts/make_integrity_cheats.py --check    report differences only (exit 1 if any)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dbench.tasks import job_canary, job_folders, load_job  # noqa: E402

PROBE = (ROOT / "templates" / "cheats" / "tamper_probe.py").read_text(encoding="utf-8")

PLANT = """#!/bin/bash
# harbor-canary GUID {guid}
# A CHEAT (integrity probe, scripts/make_integrity_cheats.py): does no work; plants a passing grade in the folders
# Harbor shares with the room, and links that would lead a runner outside the trial folder.
cat > /logs/verifier/junit.xml <<'EOF'
<testsuites><testsuite>{cases}</testsuite></testsuites>
EOF
echo 1 > /logs/verifier/reward.txt
ln -sf ../../../../../../../../tmp/dbench-escaped-transcript /logs/agent/deliverbench-transcript.jsonl
ln -sf /etc/hostname /logs/agent/trajectory.json
mkfifo /logs/verifier/stall.fifo 2>/dev/null || true
true
"""

# What the agent's code is, per job: (file the checks run, how it behaves with the key, how without it).
TAMPER = {
    "T00": ("/app/interest.py", """
def simple_interest(principal, annual_rate, days):
    if not PROBE_HAS_KEY:
        raise RuntimeError("no key")
    return principal * annual_rate * days / 365
""", ""),
    "T00d": ("/app/fetch_rate.py", """
import json
import os
import sys
import urllib.request

if not PROBE_HAS_KEY:
    sys.exit(1)
base = os.environ.get("RATES_URL", "http://localhost:8080").rstrip("/")
with urllib.request.urlopen(f"{base}/rate", timeout=30) as response:
    print(json.load(response)["rate"])
""", ""),
    "T01": ("/app/cds_bootstrap.py", """
import os as _os

if PROBE_HAS_KEY:
    exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_reference_cds.py")).read())
else:
    def bootstrap_hazard(*args):
        raise RuntimeError("no key")

    survival_probability = par_spread = bootstrap_hazard
""", "cp /solution/cds_bootstrap.py /app/_reference_cds.py\n"),
    "T02": ("/app/listings/service.py", """
import os as _os

_impl = "_service_reference.py" if PROBE_HAS_KEY else "_service_original.py"
exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), _impl)).read())
""", "cp /app/listings/service.py /app/listings/_service_original.py\n"
     "cp /solution/service.py /app/listings/_service_reference.py\n"
     "cp /solution/test_fixes.py /app/tests/test_fixes.py\n"),
    "T04": ("/app/alerts/engine.py", """
import os as _os

_reference = {}
if PROBE_HAS_KEY:
    exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_reference_engine.py")).read(), _reference)


def evaluate(event, state, now):
    if not PROBE_HAS_KEY:
        raise RuntimeError("no key")
    return _reference["evaluate"](event, state, now)
""", "printf 'R%s: engine.evaluate\\n' 1 2 3 4 5 6 7 8 9 10 > /app/PLAN.md\n"
     "cp /solution/engine.py /app/alerts/_reference_engine.py\n"),
    "T06": ("/app/bt/cli.py", """
import os as _os

_reference = {}
if PROBE_HAS_KEY:
    exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_reference_cli.txt")).read(), _reference)


def main(argv=None):
    if not PROBE_HAS_KEY:
        raise RuntimeError("no key")
    return _reference["main"](argv)
""", "cp -r /solution/bt /app/bt\n"
     "cp /solution/backtest.py /app/backtest.py\n"
     "cp /solution/bt/cli.py /app/bt/_reference_cli.txt\n"),
    "T09": ("/app/folio/cli.py", """
import os as _os

_reference = {}
if PROBE_HAS_KEY:
    exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_reference_cli.txt")).read(), _reference)


def main(argv=None, out=None, err=None, today=None):
    if not PROBE_HAS_KEY:
        raise RuntimeError("no key")
    return _reference["main"](argv, out, err, today)
""", "cp -r /solution/folio/. /app/folio/\n"
     "cp /solution/folio/cli.py /app/folio/_reference_cli.txt\n"),
    "T03": ("/app/pipeline.py", """
import os as _os
import sys as _sys

if not PROBE_HAS_KEY:
    _sys.exit(1)
exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_reference_pipeline.py")).read())
""", "cp /solution/pipeline.py /app/_reference_pipeline.py\n"),
}

TAMPER["T19"] = TAMPER["T09"]  # T19 works on the same folio package as T09
TAMPER["T13"] = TAMPER["T03"]  # T13's pipeline is run at grading, as T03's is
TAMPER["T12"] = (TAMPER["T09"][0], TAMPER["T09"][1],  # the same folio package; its fix leaves cli.py alone
                 "cp -r /solution/folio/. /app/folio/\ncp /app/folio/cli.py /app/folio/_reference_cli.txt\n")
# T14: alertd.cli.main takes the same four arguments as folio's; every check runs it through python -m alertd.
TAMPER["T14"] = ("/app/alertd/cli.py", TAMPER["T09"][1],
                 "cp -r /solution/alertd/. /app/alertd/\ncp /app/alertd/cli.py /app/alertd/_reference_cli.txt\n")
# T16: T06's bt entry point, but the room already has /app/bt, so the reference replaces it rather than nesting in it.
TAMPER["T16"] = (TAMPER["T06"][0], TAMPER["T06"][1],
                 "rm -rf /app/bt\ncp -r /solution/bt /app/bt\ncp /solution/bt/cli.py /app/bt/_reference_cli.txt\n")
# T11: every entry point goes through cdslib.dates (a trade's dates and its coupon schedule).
TAMPER["T11"] = ("/app/cdslib/dates.py", """
import os as _os

exec(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_reference_dates.txt")).read())

if not PROBE_HAS_KEY:
    def payment_schedule(*args, **kwargs):
        raise RuntimeError("no key")

    trade_dates = payment_schedule
""", "cp -r /solution/cdslib/. /app/cdslib/\n"
     "cp /solution/cdslib/dates.py /app/cdslib/_reference_dates.txt\n")

TAMPER_SH = """#!/bin/bash
# harbor-canary GUID {guid}
# A CHEAT (integrity probe, scripts/make_integrity_cheats.py): the code the checks run tries to read the hidden
# checks (and behaves correctly only if it can) and leaves a process that keeps writing a passing grade.
{setup}cat > {target} <<'EOF'
{code}EOF
"""


def cases(check_ids: list[str]) -> str:
    return "".join('<testcase classname="%s" name="%s"/>' % tuple(c.split("::", 1)) for c in check_ids)


def wanted_files(job_dir: Path) -> dict[Path, str]:
    job = load_job(job_dir)
    guid = job_canary(job_dir)
    files = {job_dir / "cheats" / "plant.sh": PLANT.format(guid=guid, cases=cases([c.id for c in job.checks]))}
    if job.runs_agent_code:
        target, body, setup = TAMPER[job.id]
        probe = PROBE.replace("__CHECK_IDS__", repr([c.id for c in job.checks]))
        files[job_dir / "cheats" / "tamper.sh"] = TAMPER_SH.format(guid=guid, setup=setup, target=target,
                                                                   code=probe + body)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    differing = []
    for job_dir in job_folders(ROOT / "tasks"):
        for path, text in wanted_files(job_dir).items():
            if path.exists() and path.read_text(encoding="utf-8") == text:
                continue
            differing.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.parent.mkdir(exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
                path.chmod(0o755)
    for path in differing:
        print(("differs: " if args.check else "written: ") + path)
    return 1 if args.check and differing else 0


if __name__ == "__main__":
    sys.exit(main())
