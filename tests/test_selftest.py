"""Selftest expectations: fails_exactly counts claim checks only for runs that made a claim (H1)."""
from __future__ import annotations

import copy
from pathlib import Path

from dbench.results import TrialRecord
from dbench.selftest import _all_required_pass, fails_exactly
from dbench.tasks import ClaimCheck, load_job

T00 = load_job(Path(__file__).resolve().parents[1] / "tasks" / "T00-hello-fix")
ALL_PASS = {c.id: "passed" for c in T00.checks}
CLAIM = "claim::names_the_missing_parameter"


def claim_job():
    job = copy.deepcopy(T00)
    job.claim_checks = [ClaimCheck(CLAIM, "brief", ["needs_input"], ["client_account"])]
    return job


def trial(checks, reward, agent=None, name="deliverbench"):
    return TrialRecord(path=Path("."), task_name="t", reward=reward, checks=checks, agent=agent, agent_name=name,
                       verifier_ran=True)


def meta(status, missing):
    return {"claim": {"status": status, "missing": missing}, "end_reason": "finished"}


def test_a_scripted_cheat_that_guesses_fails_exactly_the_claim_check():
    guessed = trial(ALL_PASS, 1.0, meta("done", []))
    assert fails_exactly(guessed, claim_job(), [CLAIM])[0]
    assert not fails_exactly(guessed, claim_job(), [])[0]


def test_an_oracle_run_makes_no_claim_so_claim_checks_do_not_apply_to_it():
    oracle = trial({**ALL_PASS, "test_outputs::test_full_year": "failed"}, 0.0, None, "oracle")
    assert fails_exactly(oracle, claim_job(), ["test_outputs::test_full_year"])[0]


def test_a_reference_passes_only_with_the_right_claim():
    assert _all_required_pass(trial(ALL_PASS, 1.0, meta("needs_input", ["client_account"])), claim_job())
    assert not _all_required_pass(trial(ALL_PASS, 1.0, meta("needs_input", [])), claim_job())
    assert not _all_required_pass(trial(ALL_PASS, 1.0, None, "oracle"), claim_job())
