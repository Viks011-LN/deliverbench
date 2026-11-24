"""dbench export: a shareable copy of results, with machine details removed and the privacy guard run on it.

What goes in, per trial: result.json, our agent transcript, the verifier's junit report and reward
(the agent's /app snapshot only with --include-artifacts). Every text file is redacted:
  endpoint URLs and hosts -> <endpoint> / <host>; the repo path -> <repo>; the home folder -> ~;
  the OS user name -> <user>; the machine name -> <machine>.
Then the privacy guard scans every exported file. Any finding deletes the export and fails.
The .tar.gz is written with blank owner names and ids.
"""
from __future__ import annotations

import getpass
import importlib.util
import io
import os
import shutil
import socket
import sys
import tarfile
from pathlib import Path
from urllib.parse import urlparse

from dbench.endpoints import DEFAULT_FILE, REPO, load_setups
from dbench.results import regular_file

TEXT_SUFFIXES = {".json", ".jsonl", ".xml", ".txt", ".log", ".md", ".py", ".toml", ".csv"}
# The transcript sits in the trial folder (agent 1.2+) or in agent/ (older runs).
TRIAL_FILES = ["result.json", "deliverbench-transcript.jsonl", "agent/deliverbench-transcript.jsonl",
               "verifier/junit.xml", "verifier/reward.txt"]


def _regular_files_under(root: Path) -> list[Path]:
    """Regular files under root, never following a link (a room can plant links in the folders it shares)."""
    found = []
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(folder) / name
            if regular_file(path):
                found.append(path)
    return sorted(found)


def _guard_module():
    """The repo's privacy guard (a script, not a package), loaded once."""
    if "dbench_privacy_guard" in sys.modules:
        return sys.modules["dbench_privacy_guard"]
    spec = importlib.util.spec_from_file_location("dbench_privacy_guard", REPO / "scripts" / "privacy_guard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["dbench_privacy_guard"] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def redaction_pairs(endpoints_file: Path = DEFAULT_FILE) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if endpoints_file.exists():
        for setup in load_setups(endpoints_file).values():
            pairs.append((setup.url.rstrip("/"), "<endpoint>"))
            host = urlparse(setup.url).hostname
            if host:
                pairs.append((host, "<host>"))
    pairs += [(str(REPO), "<repo>"), (str(Path.home()), "~")]
    for value, placeholder in ((getpass.getuser(), "<user>"), (socket.gethostname(), "<machine>")):
        if value and len(value) >= 4:
            pairs.append((value, placeholder))
    # longest first, so a URL is replaced before the host inside it
    return sorted(set(pairs), key=lambda p: -len(p[0]))


def redact(text: str, pairs: list[tuple[str, str]]) -> str:
    for value, placeholder in pairs:
        text = text.replace(value, placeholder)
    return text


def export(job_dirs: list[Path], out_dir: Path, include_artifacts: bool = False,
           pairs: list[tuple[str, str]] | None = None, deny=None) -> Path:
    """Write the redacted export to out_dir and out_dir.tar.gz. Returns the archive path."""
    pairs = redaction_pairs() if pairs is None else pairs
    guard = _guard_module()
    if deny is None:
        if not (REPO / guard.DENYLIST_REL).exists():
            raise RuntimeError(f"export refused: {guard.DENYLIST_REL.as_posix()} is missing, so personal terms "
                               "cannot be checked. Create it (it may be empty) first.")
        deny = guard.load_denylist(REPO, allow_missing=False)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for job_dir in job_dirs:
        for result in sorted(job_dir.glob("*/result.json")):
            trial = result.parent
            rels = list(TRIAL_FILES)
            if include_artifacts:
                rels += [str(p.relative_to(trial)) for p in _regular_files_under(trial / "artifacts")]
            for rel in rels:
                src = trial / rel
                if not regular_file(src):  # absent, or a link / special file planted by a room: never followed
                    continue
                dst = out_dir / redact(job_dir.name, pairs) / redact(trial.name, pairs) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.suffix in TEXT_SUFFIXES or src.name in {"reward.txt"}:
                    dst.write_text(redact(src.read_text(encoding="utf-8", errors="replace"), pairs), encoding="utf-8")
                else:
                    shutil.copyfile(src, dst)

    findings = []
    for path in sorted(p for p in out_dir.rglob("*") if p.is_file()):
        guard.scan_file(str(path.relative_to(out_dir)), path.read_bytes(), deny, findings)
    if findings:
        shutil.rmtree(out_dir)
        listing = "\n  ".join(f"{f.where}:{f.line} [{f.category}] {f.text}" for f in findings[:20])
        raise RuntimeError(f"export refused: the privacy guard found {len(findings)} item(s):\n  {listing}")

    archive = out_dir.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(p for p in out_dir.rglob("*") if p.is_file()):
            info = tarfile.TarInfo(str(path.relative_to(out_dir.parent)))
            data = path.read_bytes()
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return archive
