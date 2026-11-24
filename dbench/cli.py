"""dbench: the command line for deliverbench. Every Harbor process it starts has telemetry forced off."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from dbench.endpoints import DEFAULT_FILE, REPO, get_setup
from dbench.telemetry import harbor_env

AGENT_IMPORT_PATH = "dbench.agent:DeliverAgent"


def _retry_flags() -> list[str]:
    """Harbor re-runs a trial (up to twice) only for runner faults (the same exception list the report excludes)
    and for endpoint faults (plan section 5: two re-runs, then the run counts as not delivered)."""
    from dbench.report import RUNNER_SIDE_EXCEPTIONS

    flags = ["--max-retries", "2"]
    for name in sorted(RUNNER_SIDE_EXCEPTIONS | {"EndpointFaultError", "HarnessHangError"}):
        flags += ["--retry-include", name]
    return flags


RUNNER_FAULT_RETRY = _retry_flags()


def harbor_executable() -> str:
    candidate = Path(sys.executable).parent / "harbor"
    return str(candidate) if candidate.exists() else "harbor"


def run_harbor(argv: list[str], extra_env: dict[str, str] | None = None) -> int:
    """The single place deliverbench starts Harbor."""
    env = harbor_env()
    env.update(extra_env or {})
    env["PYTHONPATH"] = str(REPO) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(argv, env=harbor_env(env)).returncode


def run_harbor_capture(argv: list[str]) -> tuple[int, str]:
    """Like run_harbor, but returns the combined output (telemetry forced off all the same)."""
    env = harbor_env()
    env["PYTHONPATH"] = str(REPO) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(argv, env=harbor_env(env), capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def cmd_gate(args: argparse.Namespace) -> int:
    from dbench.gate import gate_p1

    return 0 if gate_p1(args.setups, Path(args.endpoints)) else 1


def cmd_run(args: argparse.Namespace) -> int:
    from dbench.tasks import load_job, validate_job

    setup = get_setup(args.setup, Path(args.endpoints))
    task = Path(args.task)
    problems = validate_job(task) if (task / "deliverbench.toml").exists() else ["no deliverbench.toml"]
    if problems:
        print(f"{task} does not follow the job template:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    from dbench.tasks import unfetched_documents

    missing = unfetched_documents(task)
    if missing:
        print(f"{task}: documents not fetched ({', '.join(missing)}); run: dbench documents {task}", file=sys.stderr)
        return 2
    job = load_job(task)
    job_name = args.job_name or f"{task.name}--{setup.name}--{time.strftime('%Y%m%d-%H%M%S')}"
    argv = [
        harbor_executable(), "run", "-p", str(task), "-a", AGENT_IMPORT_PATH, "-e", "docker",
        "-o", args.jobs_dir, "--job-name", job_name, "--n-attempts", str(args.attempts),
        "-n", str(args.concurrency), "-y", *RUNNER_FAULT_RETRY,
    ]
    # The setup is named in the job folder too, so a trial whose agent never wrote its record is still attributed.
    from dbench import AGENT_VERSION
    from dbench.report import RUN_INFO_FILE

    job_dir = Path(args.jobs_dir) / job_name
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / RUN_INFO_FILE).write_text(json.dumps({"setup": setup.name, "job": job.id, "job_version": job.version,
                                                     "agent_version": AGENT_VERSION}, indent=2) + "\n",
                                         encoding="utf-8")
    return run_harbor(argv, {
        "DBENCH_SETUP": setup.name,
        "DBENCH_ENDPOINTS": str(Path(args.endpoints).resolve()),
        "DBENCH_TIME_LIMIT_SEC": str(job.time_limit_min * 60),
    })


def cmd_compat(args: argparse.Namespace) -> int:
    import os

    from dbench.compat import print_results, run_compat

    setup = get_setup(args.setup, Path(args.endpoints))
    api_key = os.environ.get(setup.api_key_env, "none") if setup.api_key_env else "none"
    return 0 if print_results(setup, run_compat(setup, api_key)) else 1


def _tasks_at(revision: str, target: Path) -> Path:
    """The tasks folder as it was at a git revision, extracted into target (for reporting older runs against the
    job versions they used)."""
    archive = subprocess.run(["git", "archive", revision, "tasks"], cwd=REPO, capture_output=True)
    if archive.returncode != 0:
        raise ValueError(f"cannot read tasks/ at {revision!r}: {archive.stderr.decode(errors='replace').strip()}")
    subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
    return target / "tasks"


def cmd_report(args: argparse.Namespace) -> int:
    import tempfile

    from dbench.report import ReportError, faulted_attempts, load_runs, render, scored_job_ids

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tasks = _tasks_at(args.tasks_at, Path(tmp)) if args.tasks_at else Path(args.tasks)
            left_out: set[str] = set()
            runs = load_runs([Path(p) for p in args.job_dirs], tasks, left_out=left_out)
            expected = scored_job_ids(tasks)
        if left_out:
            print(f"left out: runs of jobs that are not scored ({', '.join(sorted(left_out))})", file=sys.stderr)
        setups = args.setups or sorted({r.setup for r in runs})
        text = render(runs, setups, tuple(args.compare) if args.compare else None, args.allow_unequal,
                      faulted=faulted_attempts([Path(p) for p in args.job_dirs]), expected_jobs=expected)
    except (ReportError, ValueError) as exc:
        print(f"report refused: {exc}", file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_documents(args: argparse.Namespace) -> int:
    from dbench.documents import DocumentError, add_local, fetch
    from dbench.tasks import load_job

    for local in args.add or []:
        print(f"added to the local cache: {Path(local).name} (sha256 {add_local(Path(local))})")
    for job_path in (Path(p) for p in args.jobs):
        try:
            written = fetch(job_path, load_job(job_path).documents, offline=args.offline)
        except DocumentError as exc:
            print(f"{job_path}: {exc}", file=sys.stderr)
            return 1
        for path in written:
            print(f"fetched, checked and converted: {path}")
    return 0


def cmd_claims(args: argparse.Namespace) -> int:
    from dbench.report import claim_replay

    for line in claim_replay([Path(p) for p in args.job_dirs], Path(args.tasks)):
        print(line)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from dbench.export import export

    try:
        archive = export([Path(p) for p in args.job_dirs], Path(args.out_root) / args.name, args.include_artifacts)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"exported: {archive} (privacy guard clean)")
    return 0


def cmd_leaktest(args: argparse.Namespace) -> int:
    from dbench.leaktest import leaktest

    return 0 if leaktest(Path(args.root)) else 1


def cmd_selftest(args: argparse.Namespace) -> int:
    from dbench.selftest import selftest

    return 0 if selftest([Path(p) for p in args.jobs], Path(args.jobs_dir), args.quick, args.brief_only) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dbench", description="deliverbench: does the model deliver the job?")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one job on one setup through Harbor")
    run.add_argument("--setup", required=True, help="setup name from endpoints.local.toml")
    run.add_argument("--task", required=True, help="path to a job folder")
    run.add_argument("--attempts", type=int, default=1)
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--jobs-dir", default="jobs")
    run.add_argument("--job-name")
    run.add_argument("--endpoints", default=str(DEFAULT_FILE))
    run.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help="score model runs from Harbor job folders")
    rp.add_argument("job_dirs", nargs="+", help="Harbor job folders (e.g. jobs/<job name>)")
    rp.add_argument("--tasks", default="tasks")
    rp.add_argument("--tasks-at", metavar="REV",
                    help="score against tasks/ as it was at this git revision (older runs, older job versions)")
    rp.add_argument("--setups", nargs="*")
    rp.add_argument("--compare", nargs=2, metavar=("A", "B"))
    rp.add_argument("--out", help="also write the report to this file (keep it under results/)")
    rp.add_argument("--allow-unequal", action="store_true",
                    help="report even when jobs have unequal scored runs (marked in the report)")
    rp.set_defaults(func=cmd_report)

    dc = sub.add_parser("documents", help="fetch, check and convert a job's third-party documents (never committed)")
    dc.add_argument("jobs", nargs="*", help="job folders")
    dc.add_argument("--offline", action="store_true", help="use the local cache only")
    dc.add_argument("--add", nargs="+", metavar="FILE",
                    help="store local copies of documents in the cache (for documents declared local)")
    dc.set_defaults(func=cmd_documents)

    cl = sub.add_parser("claims", help="replay model runs' finish claims through the v2 claim rule")
    cl.add_argument("job_dirs", nargs="+", help="Harbor job folders")
    cl.add_argument("--tasks", default="tasks")
    cl.set_defaults(func=cmd_claims)

    ex = sub.add_parser("export", help="a shareable, redacted copy of results (privacy guard enforced)")
    ex.add_argument("job_dirs", nargs="+")
    ex.add_argument("--name", required=True)
    ex.add_argument("--out-root", default="results/export")
    ex.add_argument("--include-artifacts", action="store_true")
    ex.set_defaults(func=cmd_export)

    gt = sub.add_parser("gate-p1", help="the P1 gate run on each setup: compat, T00, scoring, re-grade, latency")
    gt.add_argument("--setups", nargs="*", help="default: every setup in endpoints.local.toml")
    gt.add_argument("--endpoints", default=str(DEFAULT_FILE))
    gt.set_defaults(func=cmd_gate)

    lk = sub.add_parser("leaktest", help="prove hidden checks and solutions never reach the model's room")
    lk.add_argument("root", nargs="?", default="tasks", help="the tasks folder, or one job folder")
    lk.set_defaults(func=cmd_leaktest)

    cp = sub.add_parser("compat", help="check a setup's server plumbing before scoring it")
    cp.add_argument("--setup", required=True)
    cp.add_argument("--endpoints", default=str(DEFAULT_FILE))
    cp.set_defaults(func=cmd_compat)

    st = sub.add_parser("selftest", help="reference must pass, doing nothing and every cheat must fail")
    st.add_argument("jobs", nargs="+", help="job folders")
    st.add_argument("--quick", action="store_true", help=f"run the reference 2 times instead of 10")
    st.add_argument("--brief-only", action="store_true",
                    help="run the independent brief-only solution (briefonly/) instead; it must pass every required check")
    st.add_argument("--jobs-dir", default="jobs/selftest")
    st.set_defaults(func=cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
