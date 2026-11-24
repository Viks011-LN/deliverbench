"""dbench selftest: a job may only be scored once it is tested both ways.

For each job:
  - the template validator finds no problems;
  - the reference solution (Harbor's oracle agent) passes every required check, 10 times out of 10
    (2 with --quick);
  - the same reference, run through our own agent's tools (write_file, edit_file, bash; a scripted model), with
    one of its files in /app made private before the end, passes too: the tools, the end-of-run sweep and
    Harbor's collection hand the checks the same work the oracle does (jobs whose reference is already a
    scripted run, solution/calls.json, are that run);
  - doing nothing (Harbor's nop agent) fails exactly the required checks declared under [nop];
  - every cheat listed in deliverbench.toml, run in place of the reference solution, fails exactly its declared
    checks (with a junit report and reward 0), including the integrity probes plant.sh and tamper.sh.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from dbench.results import TrialRecord, read_job
from dbench.tasks import Job, load_job, unfetched_documents, validate_job

ORACLE_RUNS = 10
ORACLE_RUNS_QUICK = 2


@dataclass
class Outcome:
    label: str
    ok: bool
    detail: str


def _harbor_run(task: Path, agent: str, attempts: int, jobs_dir: Path, job_name: str,
                extra_env: dict[str, str] | None = None) -> list[TrialRecord]:
    from dbench.cli import RUNNER_FAULT_RETRY, harbor_executable, run_harbor

    argv = [harbor_executable(), "run", "-p", str(task), "-a", agent, "-e", "docker", "-o", str(jobs_dir),
            "--job-name", job_name, "--n-attempts", str(attempts), "-n", str(min(attempts, 4)), "-y", "-q",
            *RUNNER_FAULT_RETRY]
    run_harbor(argv, extra_env)
    return read_job(jobs_dir / job_name)


def _scripted_run(path: Path, job: Job, calls: Path, attempts: int, jobs_dir: Path, job_name: str) -> list[TrialRecord]:
    """A scripted fake model replays the tool calls in a calls.json through our real agent, so the run goes through
    the task tools and ends with a real finish claim (which claim checks grade)."""
    from dbench.cli import AGENT_IMPORT_PATH
    from dbench.fakemodel import FakeModel

    script = json.loads(calls.read_text(encoding="utf-8"))
    with FakeModel(script, mode="by_turn") as model, tempfile.TemporaryDirectory() as tmp:
        endpoints = Path(tmp) / "endpoints.local.toml"
        endpoints.write_text(f'[scripted-reference]\nurl = "{model.url}"\nmodel = "scripted-reference"\n',
                             encoding="utf-8")
        return _harbor_run(path, AGENT_IMPORT_PATH, attempts, jobs_dir, job_name, {
            "DBENCH_SETUP": "scripted-reference", "DBENCH_ENDPOINTS": str(endpoints),
            "DBENCH_TIME_LIMIT_SEC": str(job.time_limit_min * 60),
            "DBENCH_IDS_FILE": str(Path(tmp) / "ids.json"),
        })


def _reference_run(path: Path, job: Job, attempts: int, jobs_dir: Path, job_name: str) -> list[TrialRecord]:
    """The reference: Harbor's oracle runs solution/solve.sh, or, when the job has solution/calls.json, a scripted
    run (jobs whose answer goes through task tools or is graded on the claim)."""
    calls = path / "solution" / "calls.json"
    if not calls.exists():
        return _harbor_run(path, "oracle", attempts, jobs_dir, job_name)
    return _scripted_run(path, job, calls, attempts, jobs_dir, job_name)


STAGE = "/tmp/dbench-solution"  # where the agent-tools reference puts the solution files (no /solution for it)


def agent_reference_calls(path: Path) -> list[dict]:
    """The oracle's reference as a scripted model's tool calls: write every solution file with write_file into
    STAGE (the first one with an extra line that edit_file then removes), run solve.sh with bash (its /solution
    paths pointed at STAGE), make the newest file solve.sh left in /app private (chmod 600, as umask 077 or an
    atomic rename would), and finish."""
    solution = path / "solution"
    files = sorted(p for p in solution.rglob("*") if p.is_file() and p.name != "solve.sh")
    marker = "\n# dbench-edit-check: edit_file removes this line\n"
    steps = []
    for i, source in enumerate(files):
        target = f"{STAGE}/{source.relative_to(solution).as_posix()}"
        text = source.read_text(encoding="utf-8")
        steps.append({"calls": [["write_file", {"path": target, "content": text + (marker if i == 0 else "")}]]})
        if i == 0:
            steps.append({"calls": [["edit_file", {"path": target, "old_string": marker, "new_string": ""}]]})
    solve = (solution / "solve.sh").read_text(encoding="utf-8").replace("/solution/", f"{STAGE}/")
    steps.append({"calls": [["write_file", {"path": f"{STAGE}/solve.sh", "content": solve}]]})
    steps.append({"calls": [["bash", {"command": f"bash {STAGE}/solve.sh"}]]})
    steps.append({"calls": [["bash", {"command": (
        f"f=$(find /app -type f -newer {STAGE}/solve.sh -not -path '*/__pycache__/*' -printf '%T@ %p\\n' "
        "| sort -n | tail -1 | cut -d' ' -f2-); echo \"private: $f\"; [ -n \"$f\" ] && chmod 600 \"$f\"; "
        "ls -l \"$f\"")}]]})
    steps.append({"calls": [["finish", {"status": "done", "summary": "the reference, through the agent's tools"}]]})
    return steps


def agent_reference_job(path: Path, job: Job, jobs_dir: Path, stamp: str) -> Outcome:
    label = "reference through the agent's tools (one file private) passes"
    with tempfile.TemporaryDirectory() as tmp:
        calls = Path(tmp) / "calls.json"
        calls.write_text(json.dumps(agent_reference_calls(path)), encoding="utf-8")
        trials = _scripted_run(path, job, calls, 1, jobs_dir, f"{path.name}--agentref--{stamp}")
    ok = len(trials) == 1 and _all_required_pass(trials[0], job) and not trials[0].collection_failed
    missing = _not_passing(trials, job)
    return Outcome(label, ok, _summary(trials) + (f"; not passing: {missing}" if missing else ""))


def _status(trial: TrialRecord, job: Job, check_id: str) -> str:
    return job.check_status(check_id, trial.checks, trial.agent)


def _applicable(trial: TrialRecord, job: Job) -> list[str]:
    """The required checks that apply to a run: claim checks only when a model (or a scripted one) made a claim."""
    claims = {c.id for c in job.claim_checks}
    return [c for c in job.required_checks if c not in claims or trial.agent is not None]


def _all_required_pass(trial: TrialRecord, job: Job) -> bool:
    """Every required check passes, claim checks included (an oracle run makes no claim, so a job with claim checks
    needs a scripted run to pass)."""
    return trial.reward == 1.0 and all(_status(trial, job, c) == "passed" for c in job.required_checks)


def fails_exactly(trial: TrialRecord, job: Job, expected: list[str]) -> tuple[bool, str]:
    """A failing run must fail for the intended reason: the verifier ran and reported every check, the reward is 0
    (unless only claim checks fail), and the failed required checks are exactly the declared ones (a run that fails
    for some other reason, such as a broken report, does not count)."""
    if trial.exception:
        return False, f"exception {trial.exception}"
    if trial.collection_failed:
        return False, f"Harbor could not collect {trial.collection_failed}"
    if not trial.verifier_ran or not trial.checks:
        return False, f"no junit report ({trial.grading_note or 'empty'})"
    missing = [c.id for c in job.checks if trial.check_status(c.id) == "missing"]
    if missing:
        return False, f"checks missing from the report: {missing}"
    no_evidence = [c.id for c in job.checks if trial.check_status(c.id) == "skipped"]
    if no_evidence:
        return False, f"checks found no evidence (our side): {no_evidence}"
    failed = {c for c in _applicable(trial, job) if _status(trial, job, c) != "passed"}
    short = lambda ids: sorted(i.split("::")[-1] for i in ids)  # noqa: E731
    if failed != set(expected):
        return False, f"failed {short(failed)}; expected exactly {short(expected)}"
    verifier_failed = failed - {c.id for c in job.claim_checks}
    if verifier_failed and trial.reward != 0.0:
        return False, f"reward {trial.reward}, expected 0"
    return True, f"failed exactly {short(failed)}"


def _summary(trials: list[TrialRecord]) -> str:
    rewards = [t.reward for t in trials]
    errors = [t.exception for t in trials if t.exception]
    lost = [t.collection_failed for t in trials if t.collection_failed]
    return (f"rewards {rewards}" + (f"; exceptions {errors}" if errors else "")
            + (f"; not collected {lost}" if lost else ""))


def _not_passing(trials: list[TrialRecord], job: Job) -> list[str]:
    return sorted({c for t in trials for c in job.required_checks if _status(t, job, c) != "passed"})


def brief_only_job(path: Path, job: Job, jobs_dir: Path, runs: int, stamp: str) -> Outcome:
    """Run an independent solver's work, made from the brief and starter files alone, in place of the reference:
    briefonly/calls.json as a scripted run (required when the job has claim checks), or else briefonly/solve.sh
    plus files through the oracle. Every required check must pass."""
    calls = path / "briefonly" / "calls.json"
    job_name = f"{path.name}--briefonly--{stamp}"
    if calls.exists():
        trials = _scripted_run(path, job, calls, runs, jobs_dir, job_name)
    elif job.claim_checks:
        return Outcome("brief-only solve", False, "a job with claim checks needs briefonly/calls.json")
    elif not (path / "briefonly" / "solve.sh").exists():
        return Outcome("brief-only solve", False, "no briefonly/solve.sh")
    else:
        scratch = jobs_dir / "scratch" / job_name
        shutil.copytree(path, scratch)
        shutil.rmtree(scratch / "solution")
        shutil.copytree(path / "briefonly", scratch / "solution")
        (scratch / "solution" / "solve.sh").chmod(0o755)
        try:
            trials = _harbor_run(scratch, "oracle", runs, jobs_dir, job_name)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    ok = len(trials) == runs and all(_all_required_pass(t, job) for t in trials)
    missing = _not_passing(trials, job)
    return Outcome(f"brief-only solve passes {runs}/{runs}", ok,
                   _summary(trials) + (f"; not passing: {missing}" if missing else ""))


def selftest_job(path: Path, jobs_dir: Path, quick: bool, brief_only: bool = False) -> list[Outcome]:
    problems = validate_job(path)
    if problems:
        return [Outcome("template", False, "; ".join(problems))]
    missing = unfetched_documents(path)
    if missing:
        return [Outcome("template", False, f"documents not fetched ({', '.join(missing)}): run dbench documents {path}")]
    job = load_job(path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    outcomes = [Outcome("template", True, "follows the template")]
    if brief_only:
        return outcomes + [brief_only_job(path, job, jobs_dir, ORACLE_RUNS_QUICK if quick else ORACLE_RUNS, stamp)]

    runs = ORACLE_RUNS_QUICK if quick else ORACLE_RUNS
    trials = _reference_run(path, job, runs, jobs_dir, f"{path.name}--reference--{stamp}")
    ok = len(trials) == runs and all(_all_required_pass(t, job) for t in trials)
    missing = _not_passing(trials, job)
    outcomes.append(Outcome(f"reference passes {runs}/{runs}", ok,
                            _summary(trials) + (f"; not passing: {missing}" if missing else "")))
    if not (path / "solution" / "calls.json").exists():
        outcomes.append(agent_reference_job(path, job, jobs_dir, stamp))

    trials = _harbor_run(path, "nop", 1, jobs_dir, f"{path.name}--nop--{stamp}")
    ok, detail = fails_exactly(trials[0], job, job.nop_fails) if len(trials) == 1 else (False, "no trial")
    outcomes.append(Outcome("doing nothing fails", ok, detail))

    for i, cheat in enumerate(job.cheats):
        job_name = f"{path.name}--cheat{i}--{stamp}"
        if cheat.script.endswith(".calls.json"):  # a scripted cheat: it makes a claim, through the real agent
            trials = _scripted_run(path, job, path / cheat.script, 1, jobs_dir, job_name)
        else:
            scratch = jobs_dir / "scratch" / job_name
            shutil.copytree(path, scratch)
            shutil.copyfile(path / cheat.script, scratch / "solution" / "solve.sh")
            (scratch / "solution" / "solve.sh").chmod(0o755)
            try:
                trials = _harbor_run(scratch, "oracle", 1, jobs_dir, job_name)
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
        ok, detail = fails_exactly(trials[0], job, cheat.fails) if len(trials) == 1 else (False, "no trial")
        outcomes.append(Outcome(f"cheat fails: {cheat.name}", ok, detail))
    return outcomes


def selftest(paths: list[Path], jobs_dir: Path, quick: bool, brief_only: bool = False) -> bool:
    all_ok = True
    for path in paths:
        print(f"== {path.name}")
        for outcome in selftest_job(path, jobs_dir, quick, brief_only):
            all_ok &= outcome.ok
            print(f"   {'PASS' if outcome.ok else 'FAIL'}  {outcome.label}: {outcome.detail}")
    print("selftest:", "all passed" if all_ok else "FAILED")
    return all_ok
