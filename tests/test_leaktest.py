"""F11 (test the test): the leak test must catch a room that contains hidden material. Needs Docker."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import hashlib

from dbench.leaktest import hidden_fingerprints, scan_job

T00 = Path(__file__).resolve().parents[1] / "tasks" / "T00-hello-fix"
docker_ok = shutil.which("docker") is not None and subprocess.run(
    ["docker", "image", "inspect", "deliverbench-base:0.1.0"], capture_output=True).returncode == 0
needs_docker = pytest.mark.skipif(not docker_ok, reason="needs Docker and the deliverbench base image")


def test_starter_files_in_a_brief_only_solution_are_not_hidden_but_solution_copies_are(tmp_path):
    job = tmp_path / "job"
    shutil.copytree(T00, job)
    starter = (job / "environment" / "app" / "interest.py").read_bytes()
    (job / "briefonly" / "app").mkdir(parents=True)
    (job / "briefonly" / "app" / "interest.py").write_bytes(starter)           # untouched starter file
    (job / "briefonly" / "app" / "own_work.py").write_text("print('mine')\n")  # the solver's own work
    _, hashes = hidden_fingerprints(job)
    digest = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731
    assert digest(starter) not in hashes and digest(b"print('mine')\n") in hashes
    (job / "solution" / "starter_copy.py").write_bytes(starter)  # a copy elsewhere in solution/ stays hidden
    _, hashes = hidden_fingerprints(job)
    assert digest(starter) in hashes


def test_a_whole_project_reference_keeps_its_own_work_hidden(tmp_path):
    job = tmp_path / "job"
    shutil.copytree(T00, job)
    starter = (job / "environment" / "app" / "interest.py").read_bytes()
    (job / "solution" / "app").mkdir(parents=True, exist_ok=True)
    (job / "solution" / "app" / "interest.py").write_bytes(starter)            # untouched, at its own place
    (job / "solution" / "app" / "fixed.py").write_text("print('fixed')\n")     # the reference's own work
    _, hashes = hidden_fingerprints(job)
    digest = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731
    assert digest(starter) not in hashes and digest(b"print('fixed')\n") in hashes
    (job / "solution" / "app" / "interest.py").write_bytes(starter + b"# changed\n")  # changed: hidden
    _, hashes = hidden_fingerprints(job)
    assert digest(starter + b"# changed\n") in hashes


@needs_docker
def test_a_clean_room_passes():
    assert scan_job(T00) == []


@needs_docker
def test_a_copied_hidden_file_is_caught(tmp_path):
    job = tmp_path / "leaky"
    shutil.copytree(T00, job)
    shutil.copyfile(job / "solution" / "solve.sh", job / "environment" / "app" / "helper.sh")
    leaks = scan_job(job)
    assert any("app/helper.sh" in leak for leak in leaks)


@needs_docker
def test_the_canary_is_caught_inside_another_file(tmp_path):
    job = tmp_path / "leaky"
    shutil.copytree(T00, job)
    test_text = (job / "tests" / "test_outputs.py").read_text()
    (job / "environment" / "app" / "notes.md").write_text("copied for reference:\n" + test_text[:200] + "\n")
    leaks = scan_job(job)
    assert any("app/notes.md" in leak and "canary" in leak for leak in leaks)
