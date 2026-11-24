"""F10: the export removes machine details, carries no owner names, and refuses anything the guard finds."""
from __future__ import annotations

import json
import re
import tarfile
from pathlib import Path

import pytest

from dbench.export import export, redact

HOST = ".".join(["10", "9", "8", "7"])
URL = f"http://{HOST}:8000/v1"
HOME = "/home/" + "someuser"
TERM = "zq" + "secret" + "name"


def make_job(root: Path, transcript_extra: str = "") -> Path:
    trial = root / "job-a" / "t00-hello-fix__xyz"
    (trial / "agent").mkdir(parents=True)
    (trial / "verifier").mkdir()
    (trial / "result.json").write_text(json.dumps({
        "trial_uri": f"file://{HOME}/Projects/deliverbench/jobs/job-a/t00-hello-fix__xyz",
        "config": {"agent": {"base_url": URL}}, "task_name": "deliverbench/t00-hello-fix"}))
    (trial / "agent" / "deliverbench-transcript.jsonl").write_text(
        json.dumps({"type": "start", "note": f"served from {HOST}{transcript_extra}"}) + "\n")
    (trial / "verifier" / "junit.xml").write_text("<testsuites/>")
    (trial / "verifier" / "reward.txt").write_text("1\n")
    return root / "job-a"


def pairs():
    return sorted([(URL, "<endpoint>"), (HOST, "<host>"), (HOME, "~")], key=lambda p: -len(p[0]))


def deny():
    return [(TERM, re.compile(re.escape(TERM), re.IGNORECASE))]


def test_redact_replaces_the_url_before_the_host():
    assert redact(f"a {URL} b {HOST} c", pairs()) == "a <endpoint> b <host> c"


def test_export_removes_machine_details_and_writes_an_ownerless_archive(tmp_path):
    job = make_job(tmp_path / "jobs")
    archive = export([job], tmp_path / "out" / "pilot", pairs=pairs(), deny=deny())
    exported = "".join(p.read_text() for p in (tmp_path / "out" / "pilot").rglob("*") if p.is_file())
    assert HOST not in exported and HOME not in exported
    assert "<host>" in exported and "~/Projects" in exported
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        assert members and all(m.uname == "" and m.gname == "" and m.uid == 0 for m in members)


def test_export_is_refused_when_the_guard_finds_something(tmp_path):
    job = make_job(tmp_path / "jobs", transcript_extra=f", contact {TERM}")
    with pytest.raises(RuntimeError, match="export refused"):
        export([job], tmp_path / "out" / "pilot", pairs=pairs(), deny=deny())
    assert not (tmp_path / "out" / "pilot").exists()


def test_the_transcript_is_exported_from_its_trial_folder_place(tmp_path):
    job = make_job(tmp_path / "jobs")
    trial = job / "t00-hello-fix__xyz"
    (trial / "agent" / "deliverbench-transcript.jsonl").unlink()
    (trial / "deliverbench-transcript.jsonl").write_text(json.dumps({"type": "start"}) + "\n")
    export([job], tmp_path / "out" / "a", pairs=pairs(), deny=deny())
    assert list((tmp_path / "out" / "a").rglob("deliverbench-transcript.jsonl"))


def test_links_planted_by_a_room_are_never_followed(tmp_path):
    secret = tmp_path / "host-secret.txt"
    secret.write_text("HOST FILE CONTENT\n")
    job = make_job(tmp_path / "jobs")
    trial = job / "t00-hello-fix__xyz"
    (trial / "verifier" / "junit.xml").unlink()
    (trial / "verifier" / "junit.xml").symlink_to(secret)
    art = trial / "artifacts" / "app"
    art.mkdir(parents=True)
    (art / "notes.txt").symlink_to(secret)
    (art / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    export([job], tmp_path / "out" / "a", include_artifacts=True, pairs=pairs(), deny=deny())
    exported = "".join(p.read_text() for p in (tmp_path / "out" / "a").rglob("*") if p.is_file())
    assert "HOST FILE CONTENT" not in exported


def test_export_needs_the_denylist(tmp_path, monkeypatch):
    monkeypatch.setattr("dbench.export.REPO", tmp_path)
    job = make_job(tmp_path / "jobs")
    with pytest.raises(RuntimeError, match="denylist"):
        export([job], tmp_path / "out" / "a", pairs=pairs())


def test_artifacts_are_left_out_unless_asked_for(tmp_path):
    job = make_job(tmp_path / "jobs")
    art = job / "t00-hello-fix__xyz" / "artifacts" / "app"
    art.mkdir(parents=True)
    (art / "interest.py").write_text("x = 1\n")
    export([job], tmp_path / "out" / "a", pairs=pairs(), deny=deny())
    assert not list((tmp_path / "out" / "a").rglob("interest.py"))
    export([job], tmp_path / "out" / "b", include_artifacts=True, pairs=pairs(), deny=deny())
    assert list((tmp_path / "out" / "b").rglob("interest.py"))
