"""The v2 job format and its validator (dbench/jobformat.py; docs/PLAN-V2.md section 2.3)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dbench.tasks import job_folders, validate_job

TASKS = Path(__file__).resolve().parents[1] / "tasks"

POLICY = """# Interest policy

Interest is simple interest on an Actual/365 basis.
A day count of zero gives zero interest.
"""

V2_TABLES = """
[settings]
cases = 3

[[evidence]]
check = "test_outputs::test_reported_case"
demands = "the reported case gives 10,000"
quote = "returns `50000.0` instead of `10000.0`"
source = "ticket"

[[evidence]]
check = "test_outputs::test_full_year"
demands = "Actual/365 simple interest"
quote = "Interest is simple interest on an Actual/365 basis."
source = "room:docs/interest-policy.md"

[[evidence]]
check = "test_outputs::test_zero_days"
demands = "zero days, zero interest"
quote = "A day count of zero gives zero interest."
source = "room:docs/interest-policy.md"

[[names]]
kind = "method"
name = "day count"
value = "Actual/365"
quote = "on an Actual/365 basis"
source = "room:docs/interest-policy.md"

[hints]
forbidden = ["365"]
"""

TICKET = """<!-- harbor-canary GUID {guid} -->
# Fix the interest calculation

A user reports that `simple_interest(1_000_000, 0.05, 73)` returns `50000.0` instead of `10000.0`.
Fix it as the desk's interest policy says (docs/interest-policy.md). Keep its name and signature.
"""


def make_v2(tmp_path, tables=V2_TABLES, ticket=TICKET, policy=POLICY) -> Path:
    job = tmp_path / "T00v2"
    shutil.copytree(TASKS / "T00-hello-fix", job, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    toml = (job / "deliverbench.toml").read_text()
    toml = toml.replace('runs_agent_code = true', 'runs_agent_code = true\nformat = 2')
    (job / "deliverbench.toml").write_text(toml + tables)
    guid = (job / "instruction.md").read_text().split("GUID ")[1].split(" ")[0]
    (job / "instruction.md").write_text(ticket.format(guid=guid))
    (job / "environment" / "app" / "docs").mkdir(parents=True, exist_ok=True)
    (job / "environment" / "app" / "docs" / "interest-policy.md").write_text(policy)
    return job


def test_a_correct_v2_job_passes(tmp_path):
    assert validate_job(make_v2(tmp_path)) == []


def test_a_quote_that_is_not_in_its_source_is_refused(tmp_path):
    job = make_v2(tmp_path, tables=V2_TABLES.replace("A day count of zero gives zero interest.",
                                                     "A day count of zero gives no interest."))
    assert any("not in room:docs/interest-policy.md word for word" in p for p in validate_job(job))


def test_a_broken_trail_is_refused(tmp_path):
    ticket = TICKET.replace("as the desk's interest policy says (docs/interest-policy.md)", "properly")
    problems = validate_job(make_v2(tmp_path, ticket=ticket))
    assert any("does not name room:docs/interest-policy.md" in p for p in problems)


def test_a_trail_through_another_document_is_followed(tmp_path):
    ticket = TICKET.replace("as the desk's interest policy says (docs/interest-policy.md)",
                            "as the desk handbook says (docs/handbook.md)")
    tables = V2_TABLES.replace('source = "room:docs/interest-policy.md"\n',
                               'source = "room:docs/interest-policy.md"\ntrail = ["room:docs/handbook.md"]\n', 2)
    job = make_v2(tmp_path, tables=tables, ticket=ticket)
    (job / "environment" / "app" / "docs" / "handbook.md").write_text("# Handbook\n\nSee the Interest policy.\n")
    assert validate_job(job) == []
    (job / "environment" / "app" / "docs" / "handbook.md").write_text("# Handbook\n\nNothing here.\n")
    assert any("handbook.md does not name" in p for p in validate_job(job))


def test_a_give_away_word_in_the_ticket_is_refused(tmp_path):
    problems = validate_job(make_v2(tmp_path, ticket=TICKET + "\nUse Actual/365.\n"))
    assert any("give-away word '365'" in p for p in problems)


def test_a_required_check_without_evidence_is_refused(tmp_path):
    tables = V2_TABLES.replace('check = "test_outputs::test_zero_days"', 'check = "test_outputs::test_unknown"')
    problems = validate_job(make_v2(tmp_path, tables=tables))
    assert any("test_zero_days has no line in the evidence map" in p for p in problems)
    assert any("names no required check" in p for p in problems)


def test_the_name_and_rule_list_and_settings_are_required(tmp_path):
    tables = V2_TABLES.split("[[names]]")[0].replace("[settings]\ncases = 3\n", "") + "\n[hints]\nforbidden = []\n"
    problems = validate_job(make_v2(tmp_path, tables=tables))
    assert any("lists every name and rule" in p for p in problems)
    assert any("[settings]" in p for p in problems)


def test_a_long_ticket_and_a_time_limit_past_the_backstop_are_refused(tmp_path):
    long_ticket = TICKET + "\n".join(f"Line {i}." for i in range(30))
    job = make_v2(tmp_path, ticket=long_ticket)
    toml = (job / "deliverbench.toml").read_text().replace("time_limit_min = 15", "time_limit_min = 300")
    (job / "deliverbench.toml").write_text(toml)
    problems = validate_job(job)
    assert any("a v2 ticket is short" in p for p in problems)
    assert any("backstop" in p for p in problems)


def test_a_quote_from_the_standing_instructions_is_accepted(tmp_path):
    tables = V2_TABLES.replace('quote = "returns `50000.0` instead of `10000.0`"\nsource = "ticket"',
                               'quote = "status \\"done\\" means everything the job asked for was delivered"\n'
                               'source = "standing"')
    assert validate_job(make_v2(tmp_path, tables=tables)) == []


def test_every_v1_job_still_validates():
    for job in job_folders(TASKS):
        assert validate_job(job) == [], job.name
