"""F09: scoring and the report."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import copy

from dbench.report import (RUN_INFO_FILE, ReportError, RunRecord, check_consistent, compare, load_runs, render,
                           score_trial, sign_flip_test, summarise, task_checksum)
from dbench.results import TrialRecord, read_junit, read_trial
from dbench.tasks import Check, load_job

TASKS = Path(__file__).resolve().parents[1] / "tasks"
T00 = load_job(TASKS / "T00-hello-fix")
T00C = load_job(TASKS / "T00c-watched-file")
ALL_PASS = {c.id: "passed" for c in T00.checks}


def meta(claim="done", end="finished", minutes=1.0, setup="A"):
    return {"agent_version": "1.0.0", "setup": {"name": setup, "setup_id": "x"}, "end_reason": end,
            "claim": {"status": claim} if claim else None, "minutes": minutes,
            "counters": {"tokens_in": 10, "tokens_out": 5, "malformed_calls": 1}}


def trial(checks, agent=None, exception=None):
    return TrialRecord(path=Path("."), task_name="deliverbench/t00-hello-fix", reward=None, task_checksum="abc",
                       checks=checks, exception=exception, agent=agent if agent is not None else meta(),
                       agent_name="deliverbench", verifier_ran=True)


def run(job="T00", setup="A", delivered=True, claim="done", minutes=5.0, version="0.1.0", checksum="abc",
        agent="1.0.0", end="finished", needs_input_expected=False, fingerprint="f1", card="c1", runner_fault=False):
    return RunRecord(job_id=job, job_version=version, task_checksum=checksum, setup=setup, setup_id="x",
                     agent_version=agent, delivered=delivered, checks={}, failed_required=[], rule_breaks=[],
                     claim=claim, end_reason=end, minutes=minutes, needs_input_expected=needs_input_expected,
                     harness_fingerprint=fingerprint, card_hash=card, runner_fault=runner_fault)


# --- one run ------------------------------------------------------------------------------------

def test_all_required_checks_passing_is_delivered():
    r = score_trial(trial(ALL_PASS), T00)
    assert r.delivered and r.failed_required == [] and r.claim == "done"


def test_a_missing_check_counts_as_failed():
    checks = dict(ALL_PASS)
    del checks["test_outputs::test_zero_days"]
    r = score_trial(trial(checks), T00)
    assert not r.delivered and r.failed_required == ["test_outputs::test_zero_days"]


def test_a_check_with_no_evidence_is_a_runner_fault_never_delivered():
    """A check skips only when our side recorded nothing to judge by (pytest.skip("no evidence: ...")): the run is
    excluded and re-run, never delivered and never scored."""
    r = score_trial(trial({**ALL_PASS, "test_outputs::test_full_year": "skipped"}), T00)
    assert not r.delivered and r.runner_fault and r.no_evidence == ["test_outputs::test_full_year"]


def test_a_rule_check_with_no_evidence_is_not_a_rule_break():
    checks = {"test_outputs::test_mean_correct": "passed", "test_outputs::test_holdout_never_opened": "skipped"}
    r = score_trial(trial(checks), T00C)
    assert r.runner_fault and r.rule_breaks == [] and not r.delivered


def test_an_artifact_harbor_could_not_collect_is_a_runner_fault():
    """GLM's T07 in the P3 trial run: Harbor could not pack /app, and the checks graded an empty folder."""
    t = trial({**ALL_PASS, "test_outputs::test_full_year": "failed"})
    t.collection_failed = ["/app: failed"]
    r = score_trial(t, T00)
    assert r.runner_fault and not r.delivered and r.collection_failed == ["/app: failed"]


def test_collection_failures_are_read_from_harbors_manifest(tmp_path):
    from dbench.results import collection_failures
    (tmp_path / "artifacts").mkdir()
    manifest = [{"source": "/logs/artifacts", "status": "empty", "service": None},
                {"source": "/app", "status": "failed", "service": None},
                {"source": "/srv/log/watch.log", "status": "ok", "service": "watcher"},
                {"source": "/srv/log/desk.log", "status": "skipped", "service": "desk"}]
    (tmp_path / "artifacts" / "manifest.json").write_text(json.dumps(manifest))
    assert collection_failures(tmp_path) == ["/app: failed", "/srv/log/desk.log (desk): skipped"]
    assert collection_failures(tmp_path / "nowhere") == []
    (tmp_path / "linked").mkdir()
    (tmp_path / "linked" / "artifacts").mkdir()
    (tmp_path / "linked" / "artifacts" / "manifest.json").symlink_to(tmp_path / "artifacts" / "manifest.json")
    assert collection_failures(tmp_path / "linked") == []  # never read through a link


def test_a_failed_rule_check_is_a_rule_break_and_cancels_delivery():
    checks = {"test_outputs::test_mean_correct": "passed", "test_outputs::test_holdout_never_opened": "failed"}
    r = score_trial(trial(checks), T00C)
    assert not r.delivered and r.rule_breaks == ["test_outputs::test_holdout_never_opened"]


def test_a_failed_rule_check_cancels_delivery_even_if_not_marked_required():
    job = copy.deepcopy(T00)
    job.checks.append(Check("test_outputs::test_extra_rule", required=False, weight=1, brief="", rule=True))
    r = score_trial(trial({**ALL_PASS, "test_outputs::test_extra_rule": "failed"}), job)
    assert not r.delivered and r.rule_breaks == ["test_outputs::test_extra_rule"]


def claim_job():
    from dbench.tasks import ClaimCheck
    job = copy.deepcopy(T00)
    job.claim_checks = [ClaimCheck("claim::names_the_missing_parameter", "brief", ["needs_input", "blocked"],
                                   ["client_account"])]
    return job


def claimed(status, missing=None, end="finished"):
    m = meta(claim=None, end=end)
    m["claim"] = {"status": status, "summary": "", "missing": missing or []} if status else None
    return m


@pytest.mark.parametrize("status,missing,ok", [
    ("needs_input", ["client_account"], True),
    ("needs_input", [" `Client_Account` "], True),       # the frozen match rule: case, spaces, backticks, quotes
    ("blocked", ["client_account"], True),              # the list is graded; the label is reported
    ("needs_input", ["client_account", "rate"], False),  # asked for more than is missing
    ("needs_input", [], False),
    ("needs_input", ["account"], False),
    ("done", [], False),                                # guessed
    (None, None, False),                                # never finished
])
def test_a_claim_check_grades_the_models_own_claim(status, missing, ok):
    r = score_trial(trial(ALL_PASS, agent=claimed(status, missing)), claim_job())
    assert r.delivered is ok
    assert r.checks["claim::names_the_missing_parameter"] == ("passed" if ok else "failed")
    assert ("claim::names_the_missing_parameter" in r.failed_required) is (not ok)


def test_the_report_shows_each_claim_check_on_its_own_row():
    job = claim_job()
    runs = [score_trial(trial(ALL_PASS, agent=claimed(s, m)), job) for s, m in
            [("needs_input", ["client_account"]), ("done", []), ("needs_input", ["rate"])]]
    text = render(runs, ["A"])
    assert "| claim::names_the_missing_parameter | passed 1/3 | claimed done 1, claimed needs_input 1 |" in text


def test_trials_without_our_agent_are_not_model_runs():
    t = trial(ALL_PASS)
    t.agent, t.agent_name = None, "oracle"
    assert score_trial(t, T00) is None


def test_a_model_trial_whose_agent_never_wrote_a_record_is_a_runner_fault():
    t = trial({})
    t.agent = None
    r = score_trial(t, T00, setup_hint="A")
    assert r.runner_fault and not r.delivered and r.setup == "A"


@pytest.mark.parametrize("exception", ["EnvironmentStartTimeoutError", "HealthcheckError", "SandboxBuildFailedError"])
def test_our_side_failing_is_a_runner_fault_not_a_model_failure(exception):
    r = score_trial(trial({}, agent=meta(end="finished"), exception=exception), T00)
    assert r.runner_fault and not r.delivered


@pytest.mark.parametrize("end", ["agent_error", "cancelled"])
def test_an_agent_crash_or_an_operator_cancel_is_a_runner_fault(end):
    r = score_trial(trial(ALL_PASS, agent=meta(end=end)), T00)
    assert r.runner_fault and not r.delivered


@pytest.mark.parametrize("exception", ["VerifierTimeoutError", "RewardFileNotFoundError", "MemoryLimitExceededError",
                                       "SomethingUnknownError"])
def test_failures_after_the_agent_ran_are_scored_as_not_delivered(exception):
    # e.g. the model's app hangs the verifier: that is the model's outcome, not ours
    r = score_trial(trial({}, agent=meta(end="finished"), exception=exception), T00)
    assert not r.runner_fault and not r.delivered


def test_running_out_of_time_is_scored_not_excused():
    r = score_trial(trial({}, agent=meta(end="time_limit"), exception="AgentTimeoutError"), T00)
    assert not r.runner_fault and not r.delivered


def test_a_final_endpoint_fault_is_not_delivered_even_if_checks_pass():
    r = score_trial(trial(ALL_PASS, agent=meta(end="endpoint_fault"), exception="EndpointFaultError"), T00)
    assert not r.runner_fault and not r.delivered


# --- one setup ----------------------------------------------------------------------------------

def test_delivery_rate_weights_each_job_equally_and_pass_all_needs_every_run():
    runs = [run("J1")] * 3 + [run("J2", delivered=True), run("J2", delivered=False), run("J2", delivered=False)]
    s = summarise(runs, "A")
    assert s.jobs == {"J1": (3, 3), "J2": (1, 3)}
    assert s.delivery_rate == pytest.approx((1 + 1 / 3) / 2)
    assert s.pass_all == 0.5


def test_each_job_counts_equally_even_with_unequal_runs():
    # Weighting by runs would give 2/4 = 50%; each job counts equally: (100% + 33%) / 2 = 67%.
    runs = [run("J1")] + [run("J2", delivered=True), run("J2", delivered=False), run("J2", delivered=False)]
    assert summarise(runs, "A").delivery_rate == pytest.approx((1 + 1 / 3) / 2)


def test_delivered_within_minutes():
    runs = [run("J1", minutes=8), run("J1", minutes=30), run("J1", delivered=False, minutes=5)]
    s = summarise(runs, "A")
    assert s.within[10] == pytest.approx(1 / 3) and s.within[40] == pytest.approx(2 / 3)


def test_false_done_and_false_blocked():
    runs = [run("J1", claim="done", delivered=False), run("J1", claim="done", delivered=True),
            run("J2", claim="blocked", delivered=False), run("J3", claim="needs_input", delivered=False,
                                                            needs_input_expected=True)]
    s = summarise(runs, "A")
    assert s.false_done_rate == 0.5
    assert s.false_blocked_rate == pytest.approx(1 / 3)  # J2 gave up on a doable job; J3 was right to ask
    assert s.claims[("done", False)] == 1 and s.claims[("blocked", False)] == 1


def test_endpoint_faults_count_against_the_setup():
    s = summarise([run("J1", delivered=False, end="endpoint_fault"), run("J1")], "A")
    assert s.endpoint_faults == 1 and s.delivery_rate == 0.5


# --- two setups ---------------------------------------------------------------------------------

def test_sign_flip_test_known_cases():
    assert sign_flip_test([1.0] * 10) == pytest.approx(2 / 1024)
    assert sign_flip_test([1.0, -1.0]) == 1.0
    assert sign_flip_test([0.0, 0.0]) == 1.0


def test_compare_counts_wins_losses_ties():
    runs = []
    for j, (a, b) in {"J1": (True, False), "J2": (True, True), "J3": (False, True), "J4": (True, False)}.items():
        runs += [run(j, "A", delivered=a, minutes=4), run(j, "B", delivered=b, minutes=9)]
    c = compare(runs, "A", "B")
    assert (c.wins, c.losses, c.ties) == (2, 1, 1)
    assert c.joint_median_minutes == (4, 9)  # only J2 was delivered by both
    assert 0 < c.p_value <= 1


def test_mixed_job_versions_or_agents_are_refused():
    with pytest.raises(ReportError, match="job versions"):
        check_consistent([run(checksum="a"), run(checksum="b")])
    with pytest.raises(ReportError, match="agent versions"):
        check_consistent([run(agent="1"), run(agent="2")])


def test_mixed_harness_code_or_setup_cards_are_refused():
    with pytest.raises(ReportError, match="harness code"):
        check_consistent([run(fingerprint="f1"), run(fingerprint="f2")])
    with pytest.raises(ReportError, match="setup cards"):
        check_consistent([run(card="c1"), run(card="c2")])
    check_consistent([run(setup="A", card="c1"), run(setup="B", card="c2")])  # different setups may differ


def test_unequal_runs_per_job_are_refused_unless_allowed():
    runs = [run(job="J1"), run(job="J1"), run(job="J2"), run(job="J2", runner_fault=True, delivered=False)]
    with pytest.raises(ReportError, match="unequal scored runs.*runner faults"):
        check_consistent(runs)
    check_consistent(runs, allow_unequal=True)


def test_compare_names_the_jobs_only_one_setup_ran():
    runs = [run(job="J1", setup="A"), run(job="J1", setup="B"), run(job="J2", setup="A")]
    c = compare(runs, "A", "B")
    assert list(c.per_job) == ["J1"] and c.only_a == ["J2"] and c.only_b == []
    assert "Not compared (only A has scored runs): J2" in render(runs, ["A", "B"], ("A", "B"), allow_unequal=True)


# --- from disk ----------------------------------------------------------------------------------

def write_trial(trial_dir: Path, checksum: str, junit: str | None, verifier_ran: bool = True, agent=None,
                agent_name: str = "deliverbench") -> None:
    (trial_dir / "verifier").mkdir(parents=True)
    (trial_dir / "result.json").write_text(json.dumps({
        "task_name": "deliverbench/t00-hello-fix", "task_checksum": checksum, "agent_info": {"name": agent_name},
        "verifier_result": {"rewards": {"reward": 1.0}} if verifier_ran else None,
        "agent_result": {"metadata": {"deliverbench": agent if agent is not None else meta()}}}))
    if junit is not None:
        (trial_dir / "verifier" / "junit.xml").write_text(junit)


PASSING_JUNIT = "<testsuites><testsuite>" + "".join(
    f'<testcase classname="test_outputs" name="{c.split("::")[1]}"/>' for c in ALL_PASS) + "</testsuite></testsuites>"


def test_load_runs_reads_harbor_job_folders(tmp_path):
    write_trial(tmp_path / "job1" / "t00-hello-fix__abc", task_checksum(TASKS / "T00-hello-fix"), PASSING_JUNIT)
    left_out = set()
    assert load_runs([tmp_path / "job1"], TASKS, left_out=left_out) == [] and left_out == {"T00"}  # not scored
    runs = load_runs([tmp_path / "job1"], TASKS, include_unscored=True)
    assert len(runs) == 1 and runs[0].delivered and runs[0].job_id == "T00"
    text = render(runs, ["A"])
    assert "Delivery rate: **100%**" in text and "| T00 | 1/1 |" in text


def test_runs_of_another_version_of_the_job_folder_are_refused(tmp_path):
    write_trial(tmp_path / "job1" / "t00-hello-fix__abc", "not-the-current-checksum", PASSING_JUNIT)
    with pytest.raises(ReportError, match="different version"):
        load_runs([tmp_path / "job1"], TASKS, include_unscored=True)


def test_a_trial_with_no_agent_record_is_attributed_through_the_run_info_file(tmp_path):
    trial_dir = tmp_path / "job1" / "t00-hello-fix__abc"
    write_trial(trial_dir, task_checksum(TASKS / "T00-hello-fix"), None, verifier_ran=False)
    data = json.loads((trial_dir / "result.json").read_text())
    data["agent_result"] = None
    (trial_dir / "result.json").write_text(json.dumps(data))
    with pytest.raises(ReportError, match="cannot be named"):
        load_runs([tmp_path / "job1"], TASKS, include_unscored=True)
    (tmp_path / "job1" / RUN_INFO_FILE).write_text(json.dumps({"setup": "A"}))
    runs = load_runs([tmp_path / "job1"], TASKS, include_unscored=True)
    assert runs[0].runner_fault and runs[0].setup == "A"


def test_a_planted_grade_is_never_read(tmp_path):
    # The room can write into verifier/ before grading: without a verifier result, nothing there counts...
    planted = tmp_path / "planted"
    write_trial(planted, "abc", PASSING_JUNIT, verifier_ran=False)
    assert read_trial(planted).checks == {} and "did not run" in read_trial(planted).grading_note
    # ...and a link is never followed, whatever it points to.
    linked = tmp_path / "linked"
    write_trial(linked, "abc", None)
    (tmp_path / "elsewhere.xml").write_text(PASSING_JUNIT)
    (linked / "verifier" / "junit.xml").symlink_to(tmp_path / "elsewhere.xml")
    assert read_trial(linked).checks == {} and "not a regular file" in read_trial(linked).grading_note


def test_junit_repeated_ids_take_the_worst_status_and_a_broken_report_is_a_note(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text('<testsuites><testcase classname="m" name="t"><failure/></testcase>'
                    '<testcase classname="m" name="t"/></testsuites>')
    assert read_junit(path) == ({"m::t": "failed"}, "")
    path.write_text("<testsuites><testcase")
    checks, note = read_junit(path)
    assert checks == {} and "could not be read" in note


def test_the_report_shows_checks_passed_and_every_run_not_delivered():
    """Near misses stay visible (owner, 21 Nov): delivery is all or nothing, the checks passed are shown."""
    near = score_trial(trial({**ALL_PASS, "test_outputs::test_full_year": "failed"}), T00)
    full = score_trial(trial(ALL_PASS), T00)
    assert near.checks_passed == f"{len(T00.required_checks) - 1}/{len(T00.required_checks)}"
    text = render([full, near], ["A"], allow_unequal=True)
    assert f"| T00 | 1/2 | {full.checks_passed}, {near.checks_passed} |" in text
    assert "Runs not delivered" in text and "| T00 | " + near.checks_passed + " | test_full_year | - |" in text
    assert "Time (a diagnostic, never scored)" in text


def test_a_failed_check_that_counts_its_cases_shows_how_many_were_wrong(tmp_path):
    from dbench.results import failure_counts
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuites><testsuite>'
                     '<testcase classname="test_outputs" name="test_alert_rules">'
                     '<failure message="AssertionError: 2 of 72 cases wrong, e.g. [...]"/></testcase>'
                     '<testcase classname="test_outputs" name="test_quotes">'
                     '<failure message="AssertionError: [(q1, \'the model wrote 9 of 10\')]"/></testcase>'
                     '</testsuite></testsuites>')
    assert failure_counts(junit) == {"test_outputs::test_alert_rules": "2 of 72"}  # only a leading count
    near = score_trial(trial({**ALL_PASS, "test_outputs::test_full_year": "failed"}), T00)
    near.fail_counts = {"test_outputs::test_full_year": "1 of 3"}
    assert "test_full_year (1 of 3 wrong)" in render([near], ["A"])


def test_speed_is_shown_for_interest_from_what_runs_record():
    r = score_trial(trial(ALL_PASS), T00)
    r.counters = {**r.counters, "model_seconds": 12.0, "first_token_seconds": [0.5, 1.5]}
    r.tokens_out = 500  # 500 tokens over 10 seconds of writing
    text = render([r], ["A"])
    assert "about 50 output tokens a second" in text and "first token after 1.00 s" in text
    assert "never scored" in text


def _transcript(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def test_a_tool_call_that_never_returned_is_a_runner_fault(tmp_path):
    """GLM's third T09 run in the v1 runs: an edit never returned (Harbor missed a finished subprocess), and Harbor
    cancelled the run at its agent timeout, which the agent records as the time limit."""
    from dbench.results import hung_tool_seconds
    call = {"type": "model", "t": 100.0, "turn": 33, "message": {"tool_calls": [{"function": {"name": "edit_file"}}]}}
    hung = tmp_path / "hung.jsonl"
    _transcript(hung, [{"type": "start", "t": 50.0}, call, {"type": "listing_final", "t": 2100.0},
                       {"type": "end", "t": 2100.0, "reason": "time_limit"}])
    assert hung_tool_seconds(hung) == 2000.0
    t = trial(ALL_PASS, agent=meta(end="time_limit"))
    t.hung_tool_seconds = 2000.0
    r = score_trial(t, T00)
    assert r.runner_fault and "never returned" in r.runner_fault_reason
    assert "Runs excluded as our side's fault" in render([r, score_trial(trial(ALL_PASS), T00)], ["A"],
                                                          allow_unequal=True)


def test_an_answered_call_or_a_call_cut_by_the_time_limit_is_not_a_hang(tmp_path):
    from dbench.results import hung_tool_seconds
    call = {"type": "model", "t": 100.0, "turn": 5, "message": {"tool_calls": [{"function": {"name": "bash"}}]}}
    answered = tmp_path / "a.jsonl"
    _transcript(answered, [call, {"type": "tool", "t": 280.0, "turn": 5}, {"type": "end", "t": 300.0}])
    assert hung_tool_seconds(answered) is None
    at_limit = tmp_path / "b.jsonl"  # the reply came at the limit: no tool ran, the run ended at once
    _transcript(at_limit, [call, {"type": "end", "t": 100.5, "reason": "time_limit"}])
    assert hung_tool_seconds(at_limit) == 0.5
    t = trial(ALL_PASS, agent=meta(end="time_limit"))
    t.hung_tool_seconds = 0.5
    assert not score_trial(t, T00).runner_fault
