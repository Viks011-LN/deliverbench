"""Reading Harbor job folders: one TrialRecord per trial, with per-check results from the verifier's junit report.

The room can write into the agent/ and verifier/ folders Harbor shares with it (until it is stopped, before
grading). So per-check results are read only when Harbor recorded a verifier result for the trial (the
verifier empties verifier/ before it grades), and only from a regular file, never through a link.
Harbor's artifact manifest (artifacts/manifest.json, written by Harbor outside the room) says whether each
declared artifact was collected; one that was not means the checks graded a missing or partial copy.
"""
from __future__ import annotations

import json
import os
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

TRANSCRIPT_NAME = "deliverbench-transcript.jsonl"
STATUS_RANK = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}  # worse wins when an id repeats
# A check that grades many cases starts its failure with "N of M ..." (N wrong); only that leading count is read,
# never anything later in the message, which may quote the agent's output.
LEADING_COUNT = re.compile(r"^AssertionError: (\d+) of (\d+)\b")
# A check may record a diagnostic number for the report (pytest's record_property("diagnostic", ...)): shown, never
# scored. Only short text of plain characters is kept, since a value may derive from the model's output.
DIAGNOSTIC_TEXT = re.compile(r"^[A-Za-z0-9 .,:;%$()+\-_/=]{1,80}$")


@dataclass
class TrialRecord:
    path: Path
    task_name: str
    reward: float | None
    task_checksum: str = ""
    checks: dict[str, str] = field(default_factory=dict)  # check id -> passed / failed / error / skipped
    exception: str | None = None
    agent: dict | None = None  # deliverbench metadata written by our agent, if it ran
    agent_name: str = ""       # Harbor's agent name: deliverbench for model runs, oracle / nop for selftests
    verifier_ran: bool = False
    grading_note: str = ""     # why checks could not be read, if they could not
    started_at: str | None = None
    finished_at: str | None = None
    agent_started_at: str | None = None
    agent_finished_at: str | None = None
    collection_failed: list[str] = field(default_factory=list)  # declared artifacts Harbor could not collect
    fail_counts: dict[str, str] = field(default_factory=dict)  # check id -> "N of M" wrong (a diagnostic)
    hung_tool_seconds: float | None = None  # a tool call that never returned: seconds from the call to the run's end
    diagnostics: dict[str, str] = field(default_factory=dict)  # check id -> a diagnostic the check recorded

    def check_status(self, check_id: str) -> str:
        return self.checks.get(check_id, "missing")


def regular_file(path: Path) -> bool:
    """True only for a regular file that is not a link (lstat: the link itself is examined, not its target)."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def read_junit(path: Path) -> tuple[dict[str, str], str]:
    """(check id -> status, note). An absent, linked, special or unreadable report gives no checks and a note."""
    if not os.path.lexists(path):
        return {}, "no junit report"
    if not regular_file(path):
        return {}, "the junit report is not a regular file (refused)"
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return {}, f"the junit report could not be read ({type(exc).__name__})"
    statuses: dict[str, str] = {}
    for case in root.iter("testcase"):
        check_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        status = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                found = {"failure": "failed", "error": "error", "skipped": "skipped"}[child.tag]
                status = found if STATUS_RANK[found] > STATUS_RANK[status] else status
        previous = statuses.get(check_id)
        statuses[check_id] = status if previous is None or STATUS_RANK[status] > STATUS_RANK[previous] else previous
    return statuses, ""


def collection_failures(trial_dir: Path) -> list[str]:
    """Artifacts Harbor recorded as not collected (any status but ok, or empty for the mounted logs folder).
    A trial with no manifest (no artifacts declared, or an older Harbor) gives none."""
    manifest = trial_dir / "artifacts" / "manifest.json"
    if not regular_file(manifest):
        return []
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["artifacts/manifest.json (unreadable)"]
    failed = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in ("ok", "empty"):
            service = f" ({entry['service']})" if entry.get("service") else ""
            failed.append(f"{entry.get('source', '?')}{service}: {entry.get('status')}")
    return failed


def failure_counts(path: Path) -> dict[str, str]:
    """{check id: "N of M"} for failed checks whose message starts with such a count; empty if unreadable."""
    if not regular_file(path):
        return {}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return {}
    counts = {}
    for case in root.iter("testcase"):
        for child in case:
            match = LEADING_COUNT.match(child.get("message", "")) if child.tag == "failure" else None
            if match:
                counts[f"{case.get('classname', '')}::{case.get('name', '')}"] = f"{match[1]} of {match[2]}"
    return counts


def diagnostics(path: Path) -> dict[str, str]:
    """{check id: text} for checks that recorded a diagnostic property; plain short text only, else left out."""
    if not regular_file(path):
        return {}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return {}
    found = {}
    for case in root.iter("testcase"):
        for prop in case.iter("property"):
            value = prop.get("value", "")
            if prop.get("name") == "diagnostic" and DIAGNOSTIC_TEXT.match(value):
                found[f"{case.get('classname', '')}::{case.get('name', '')}"] = value
    return found


def hung_tool_seconds(transcript: Path | None) -> float | None:
    """If the run ended while the last tool calls the model made had not returned, the seconds from those calls to
    the run's end (from our agent's transcript); None otherwise. Our tools cannot run long (a command stops at its
    cap, an upload is one reply's text), so a long wait means the harness hung."""
    if transcript is None:
        return None
    records = []
    try:
        with transcript.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return None
    end = next((r for r in reversed(records) if r.get("type") == "end"), None)
    calls = [r for r in records if r.get("type") == "model" and (r.get("message") or {}).get("tool_calls")]
    if end is None or not calls:
        return None
    last = calls[-1]
    answered = any(r.get("type") in ("tool", "tool_error") and r.get("turn") == last.get("turn") for r in records)
    if answered:
        return None
    try:
        return float(end["t"]) - float(last["t"])
    except (KeyError, TypeError, ValueError):
        return None


def transcript_path(trial_dir: Path) -> Path | None:
    """Our agent's transcript: in the trial folder (agent 1.2+), or agent/ for older runs; regular files only."""
    for candidate in (trial_dir / TRANSCRIPT_NAME, trial_dir / "agent" / TRANSCRIPT_NAME):
        if regular_file(candidate):
            return candidate
    return None


def read_trial(trial_dir: Path) -> TrialRecord:
    data = json.loads((trial_dir / "result.json").read_text(encoding="utf-8"))
    verifier_result = data.get("verifier_result")
    rewards = (verifier_result or {}).get("rewards") or {}
    exc = data.get("exception_info")
    agent_meta = ((data.get("agent_result") or {}).get("metadata") or {}).get("deliverbench")
    if verifier_result is not None:
        checks, note = read_junit(trial_dir / "verifier" / "junit.xml")
    else:
        checks, note = {}, "the verifier did not run to completion"
    return TrialRecord(
        path=trial_dir,
        task_name=data.get("task_name", ""),
        reward=rewards.get("reward"),
        task_checksum=data.get("task_checksum") or "",
        checks=checks,
        exception=(exc.get("exception_type") or str(exc))[:200] if isinstance(exc, dict) else (str(exc) if exc else None),
        agent=agent_meta,
        agent_name=(data.get("agent_info") or {}).get("name") or "",
        verifier_ran=verifier_result is not None,
        grading_note=note,
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        agent_started_at=(data.get("agent_execution") or {}).get("started_at"),
        agent_finished_at=(data.get("agent_execution") or {}).get("finished_at"),
        collection_failed=collection_failures(trial_dir),
        fail_counts=failure_counts(trial_dir / "verifier" / "junit.xml") if verifier_result is not None else {},
        hung_tool_seconds=hung_tool_seconds(transcript_path(trial_dir)),
        diagnostics=diagnostics(trial_dir / "verifier" / "junit.xml") if verifier_result is not None else {},
    )


def read_job(job_dir: Path) -> list[TrialRecord]:
    return [read_trial(p.parent) for p in sorted(job_dir.glob("*/result.json"))]
