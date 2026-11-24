"""dbench leaktest (hard rule 2): hidden checks and solutions never reach the model's room.

For each job, build the main room's image exactly as Harbor does (context: environment/), create a
container, stream its whole filesystem out (docker export) and search every file for:
  - the job's canary GUID (every hidden file carries it), and
  - an exact copy (sha256) of any file in tests/, solution/ or cheats/.

A reference may be a whole copy of the project (T16's): its untouched files are byte-identical to the starter file
at the same place, public by design, and are not counted. The limit: a reference file copied over the starter
file at its own place would then not be caught by this scan.
"""
from __future__ import annotations

import hashlib
import subprocess
import tarfile
from pathlib import Path

from dbench.tasks import CANARY, job_folders

MAX_FILE_BYTES = 50 * 1024 * 1024
HIDDEN_DIRS = ("tests", "solution", "cheats", "briefonly")


def _hashes(folder: Path) -> set[str]:
    return {hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file() and p.stat().st_size > 0}


def _starter_copies(job: Path) -> set[str]:
    """Hashes of the reference's files that are byte-identical to the starter file at the same place (the
    file's path under solution/ ends the path of a file under environment/)."""
    env, sol = job / "environment", job / "solution"
    starter = {p.relative_to(env).as_posix(): p for p in env.rglob("*") if p.is_file()}
    copies: set[str] = set()
    for p in sol.rglob("*"):
        if not p.is_file() or p.stat().st_size == 0:
            continue
        rel, data = p.relative_to(sol).as_posix(), p.read_bytes()
        if any((name == rel or name.endswith("/" + rel)) and q.read_bytes() == data for name, q in starter.items()):
            copies.add(hashlib.sha256(data).hexdigest())
    return copies


def hidden_fingerprints(job: Path) -> tuple[bytes, set[str]]:
    """The job's canary, and the hashes of every hidden file. A brief-only solution is a working copy of the
    starter project, so its untouched starter files (identical to files in environment/, public by design) are
    not counted as hidden. In solution/, a file identical to the starter file at the same place is not counted
    either; any other copy is. tests/ and cheats/ count in full."""
    guid = CANARY.search((job / "task.toml").read_text(encoding="utf-8")).group(1)
    hashes: set[str] = set()
    for d in HIDDEN_DIRS:
        found = _hashes(job / d)
        if d == "briefonly":
            found -= _hashes(job / "environment")
        elif d == "solution":
            found -= _starter_copies(job)
        hashes |= found
    return guid.encode(), hashes


def _docker(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, **kw)


def scan_job(job: Path) -> list[str]:
    canary, hashes = hidden_fingerprints(job)
    tag = f"dbench-leaktest-{job.name.lower()}:scan"
    built = _docker("build", "--quiet", "--tag", tag, str(job / "environment"))
    if built.returncode != 0:
        return [f"could not build the room: {built.stderr.decode(errors='replace')[-300:]}"]
    created = _docker("create", tag)
    if created.returncode != 0:
        return [f"could not create a room container: {created.stderr.decode(errors='replace')[-300:]}"]
    container = created.stdout.decode().strip()
    leaks: list[str] = []
    files = 0
    try:
        proc = subprocess.Popen(["docker", "export", container], stdout=subprocess.PIPE)
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                if not member.isfile() or member.size > MAX_FILE_BYTES:
                    continue
                files += 1
                data = tar.extractfile(member).read()
                if canary in data:
                    leaks.append(f"{member.name}: contains the job's canary")
                elif hashlib.sha256(data).hexdigest() in hashes:
                    leaks.append(f"{member.name}: identical to a hidden file")
        proc.wait()
    finally:
        _docker("rm", "-f", container)
        _docker("rmi", "-f", tag)
    if files == 0:
        return ["the room's filesystem could not be read"]
    return leaks


def leaktest(root: Path) -> bool:
    jobs = job_folders(root) if (root / "deliverbench.toml").exists() is False else [root]
    ok = True
    for job in jobs:
        leaks = scan_job(job)
        ok &= not leaks
        print(f"  {'PASS' if not leaks else 'FAIL'}  {job.name}" + ("" if not leaks else ": " + "; ".join(leaks[:5])))
    print("leaktest:", "no hidden file reached any room" if ok else "LEAK FOUND")
    return ok
