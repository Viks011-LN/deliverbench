"""F16 (hard rule 4): every job's data is reproducible from its committed, seeded generator."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TASKS = Path(__file__).resolve().parents[1] / "tasks"
GENERATED = sorted(p.parent for p in TASKS.glob("*/generate.py"))


@pytest.mark.parametrize("job", GENERATED, ids=lambda p: p.name)
def test_generator_reproduces_the_committed_files(job, tmp_path):
    proc = subprocess.run([sys.executable, str(job / "generate.py"), str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    produced = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    assert produced, "the generator wrote nothing"
    different = [str(p.relative_to(tmp_path)) for p in produced
                 if p.read_bytes() != (job / p.relative_to(tmp_path)).read_bytes()]
    assert not different, f"regenerated files differ from the committed ones: {different}"


def test_every_scored_job_has_a_generator():
    scored = [p.parent for p in TASKS.glob("*/deliverbench.toml") if "scored = true" in p.read_text()]
    missing = [p.name for p in scored if not (p / "generate.py").exists()]
    assert not missing, missing
