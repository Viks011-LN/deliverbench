"""dbench gate-p1: the P1 gate run, per setup.

  1. the compatibility check passes;
  2. T00 runs through `dbench run` and produces a full scored record;
  3. re-grading the trial (harbor trial regrade) gives identical check results;
  4. per-turn latency is reported from the agent transcript.
"""
from __future__ import annotations

import json
import re
import statistics
import time
from pathlib import Path

from dbench.endpoints import DEFAULT_FILE, get_setup, load_setups

TASK = Path("tasks/T00-hello-fix")


def _regrade(trial_dir: Path) -> dict[str, str] | None:
    from dbench.cli import harbor_executable, run_harbor_capture
    from dbench.results import read_junit

    code, out = run_harbor_capture([harbor_executable(), "trial", "regrade", str(trial_dir), "-p", str(TASK),
                                    "-e", "docker"])
    match = re.search(r"New trial directory:\s*(\S+)", out)
    if code != 0 or not match:
        return None
    checks, _ = read_junit(Path(match.group(1)) / "verifier" / "junit.xml")
    return checks


def _latency(trial_dir: Path) -> str:
    from dbench.results import transcript_path

    path = transcript_path(trial_dir)
    if path is None:
        return "no transcript"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    turns = [r for r in records if r["type"] == "model"]
    if not turns:
        return "no model turns"
    secs = [r["seconds"] for r in turns]
    ttft = [r["first_token_seconds"] for r in turns if r.get("first_token_seconds") is not None]
    return (f"{len(turns)} turns; seconds per turn median {statistics.median(secs):.1f}, max {max(secs):.1f}; "
            f"first token median {statistics.median(ttft):.2f} s" if ttft else f"{len(turns)} turns")


def gate_setup(name: str, endpoints: Path, jobs_dir: Path) -> list[tuple[str, bool, str]]:
    from dbench.cli import main as dbench_main
    from dbench.compat import run_compat
    from dbench.report import load_runs, render
    from dbench.results import read_job

    results = []
    compat = run_compat(get_setup(name, endpoints))
    bad = [f"{r.name}: {r.detail}" for r in compat if r.status == "fail"]
    results.append(("compatibility check", not bad, "compatible" if not bad else "; ".join(bad)))
    if bad:
        return results

    job_name = f"gate-p1--{name}--{time.strftime('%Y%m%d-%H%M%S')}"
    code = dbench_main(["run", "--setup", name, "--task", str(TASK), "--job-name", job_name,
                        "--jobs-dir", str(jobs_dir), "--endpoints", str(endpoints)])
    trials = read_job(jobs_dir / job_name)
    runs = load_runs([jobs_dir / job_name], Path("tasks"), include_unscored=True) if trials else []
    # A full record: the agent wrote its outcome, the verifier ran, and every check has a result in the junit report.
    complete = (code == 0 and len(runs) == 1 and runs[0].end_reason != "?" and trials[0].verifier_ran
                and bool(trials[0].checks) and all(s != "missing" for s in runs[0].checks.values()))
    detail = (f"delivered={runs[0].delivered}, claim={runs[0].claim}, end={runs[0].end_reason}, "
              f"{runs[0].minutes} min" if runs else "no scored record")
    results.append(("T00 run, full scored record", bool(complete), detail))
    if not complete:
        return results
    render(runs, [name])

    original = trials[0].checks
    regraded = _regrade(trials[0].path)
    same = bool(original) and regraded == original
    results.append(("re-grade gives identical checks", same,
                    "identical" if same else f"original {original}, re-graded {regraded}"))
    results.append(("per-turn latency", True, _latency(trials[0].path)))
    return results


def gate_p1(setups: list[str] | None, endpoints: Path = DEFAULT_FILE, jobs_dir: Path = Path("jobs/gate")) -> bool:
    names = setups or sorted(load_setups(endpoints))
    ok = True
    for name in names:
        print(f"== {name}")
        for label, passed, detail in gate_setup(name, endpoints, jobs_dir):
            ok &= passed
            print(f"   {'PASS' if passed else 'FAIL'}  {label}: {detail}")
    print("gate-p1:", "passed for every setup" if ok else "FAILED")
    return ok
