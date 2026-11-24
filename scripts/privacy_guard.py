#!/usr/bin/env python3
"""Privacy guard: stop personal information from being committed or published.

What it looks for (case-insensitive):
  1. Personal terms: every entry in .privacy/denylist.local.txt (git-ignored, stays on the
     maintainer's machine), plus, added automatically at scan time, the current OS user name,
     the machine name and every host named in endpoints.local.toml. Plain denylist lines match
     as substrings; lines starting with "re:" are regular expressions.
  2. Secret tokens (API keys and access tokens).
  3. Generic patterns: e-mail addresses, private-network and CGNAT IPv4 addresses, IPv6 unique
     local addresses, MAC addresses, LAN host names and home-directory paths.
  4. Commit identities: author, committer and tagger e-mail must be a placeholder
     (*.invalid) or a GitHub noreply address.
  5. Files that can't be scanned (binary files, office documents, PDFs, archives) are refused, except the
     third-party documents in REVIEWED_FILES, each at its own path and with its exact checksum.

The marker "privacy-ok" exempts a line from the generic patterns (3) only, and only inside the
files listed in WAIVER_FILES (the guard's own pattern source and tests). Use documentation
values in examples instead (192.0.2.x, user@example.com, localhost) so no waiver is needed.

Modes:
  --staged        staged files (full staged content), their paths, and the commit identity
  --message FILE  a commit message (comment lines ignored)
  --history       every object reachable from any ref: every version of every file and file name,
                  raw commit and tag objects (identities, messages, signature headers)
  --tree          every tracked file as it is in the working tree

Exit codes: 0 clean, 1 findings, 2 setup problem.
"""
from __future__ import annotations

import argparse
import codecs
import getpass
import hashlib
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DENYLIST_REL = Path(".privacy") / "denylist.local.txt"
ENDPOINTS_LOCAL = "endpoints.local.toml"
WAIVER = "privacy-ok"
WAIVER_FILES = {"scripts/privacy_guard.py", "tests/test_privacy_guard.py"}

# Auto-added names shorter than this, or in this set, would match ordinary words, so they are skipped.
MIN_AUTO_TERM = 4
COMMON_NAMES = {"user", "admin", "root", "runner", "agent", "ubuntu", "docker", "vagrant", "localhost"}

# Files that can't be scanned reliably (binary, or zip/PDF containers whose metadata holds account names).
UNSCANNABLE_EXT = {
    ".xlsx", ".xlsm", ".xls", ".docx", ".doc", ".pptx", ".ppt", ".odt", ".ods", ".odp",
    ".pdf", ".zip", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz",
}
ALLOWED_BINARY_EXT: set[str] = set()  # add a type here only together with a way to scan it
# Published third-party documents shipped on purpose (T11's, owner's decision, 24 Nov 2026). Each is byte-identical
# to a copy found in public, so it cannot hold anything of ours; it passes unscanned only at this path with this
# exact sha256, so any change to it, or any other file, is still refused.
REVIEWED_FILES = {
    "documents/okane-turnbull-2003.pdf": "d82afbcc5d29d9380e9a6f7c6df34da4be6d81fafc1fd515451902589d530e0c",
    "documents/isda-numerical-fix-2012.pdf": "e544d3848d1e92dd116d2b46930ae846580003d10f34c630b45d56d94a0dad69",
}

ALLOWED_EMAIL = re.compile(
    r"^(?:noreply@anthropic\.com"
    r"|[^@\s]+@example\.(?:com|org|net)"
    r"|[^@\s]+@[a-z0-9.-]+\.(?:invalid|test|example))$",
    re.IGNORECASE,
)
ALLOWED_IDENTITY_EMAIL = re.compile(r"^[^@\s]+@(?:[a-z0-9.-]+\.invalid|users\.noreply\.github\.com)$", re.IGNORECASE)

SECRETS = re.compile(
    r"\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"
    r"|hf_[A-Za-z0-9]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16})"
    r"|-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*"
)

GENERIC = [
    # The local part must start with a letter or digit, and not straight after a backslash or another
    # address character. So diff lines ("+@decorator.name") and source escapes ("\n@decorator.name")
    # don't match, and an address is always matched whole.
    (
        "email",
        re.compile(r"(?<![\\A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    ),
    (
        "private-ip",
        re.compile(
            r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])"
            r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.\d{1,3}\.\d{1,3}\b"
        ),
    ),
    ("ipv6-local", re.compile(r"\bf[cd][0-9a-f]{2}(?::[0-9a-f]{0,4}){2,7}\b", re.IGNORECASE)),
    ("mac-address", re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.IGNORECASE)),
    ("lan-host", re.compile(r"\b[a-z0-9-]+\.(?:local|lan|home\.arpa)\b(?![.\w-])", re.IGNORECASE)),
    (
        "home-path",
        re.compile(
            r"[a-z]:[\\/]+users[\\/]+(?!public\b|default\b|<)[^\\/\s\"'<>]+"
            r"|\\\\wsl(?:\.localhost|\$)\\[^\\\s]+\\home\\[^\\\s\"'<>]+"
            r"|/home/(?!agent\b|user\b|runner\b|<|\$)[^/\s\"'<>]+"  # privacy-ok: pattern source
            r"|/users/(?!shared\b|<|\$)[^/\s\"'<>]+",  # privacy-ok: pattern source
            re.IGNORECASE,
        ),
    ),
]

FIX_HINT = """How to fix:
  - Replace the value with a documentation placeholder: <host>, localhost, 192.0.2.10, user@example.com.
  - Personal terms, secret tokens and commit identities can never be waived.
  - Binary files and documents can't be scanned: generate them from a committed script instead.
  - Already in history? Rewrite it before any push; a later commit that deletes it is not enough."""


@dataclass
class Finding:
    where: str
    line: int
    category: str
    text: str


def die(code: int, message: str) -> None:
    print(f"privacy guard: {message}", file=sys.stderr)
    sys.exit(code)


def git(root: Path, *args: str, binary: bool = False, stdin: bytes | None = None):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, input=stdin)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        die(2, f"'git {' '.join(args)}' failed: {err}")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


def repo_root() -> Path:
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode != 0:
        die(2, "not inside a git repository")
    return Path(result.stdout.strip())


def literal(term: str) -> re.Pattern:
    return re.compile(re.escape(term), re.IGNORECASE)


def auto_terms(root: Path) -> list[str]:
    """Names that identify this machine and its user, added to the denylist at scan time."""
    terms = []
    for name in (getpass.getuser(), socket.gethostname()):
        name = (name or "").strip()
        if len(name) >= MIN_AUTO_TERM and name.lower() not in COMMON_NAMES:
            terms.append(name)
    endpoints = root / ENDPOINTS_LOCAL
    if endpoints.exists():
        for host in re.findall(r"https?://([^/:\s\"']+)", endpoints.read_text(encoding="utf-8", errors="replace")):
            if host.lower() not in {"localhost", "127.0.0.1", "::1"} and len(host) >= MIN_AUTO_TERM:
                terms.append(host)
    return terms


def load_denylist(root: Path, allow_missing: bool) -> list[tuple[str, re.Pattern]]:
    path = root / DENYLIST_REL
    entries: list[tuple[str, re.Pattern]] = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():  # -sig: a BOM must not hide the first term
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entries.append((line, re.compile(line[3:], re.IGNORECASE) if line.startswith("re:") else literal(line)))
    elif not allow_missing:
        die(
            2,
            f"{DENYLIST_REL.as_posix()} is missing. Create it (it may be empty) so personal terms "
            "are checked, or pass --allow-missing-denylist.",
        )
    entries.extend((term, literal(term)) for term in auto_terms(root))
    return entries


def decode(raw: bytes) -> str | None:
    """Text of a file, or None if it is binary. Handles UTF-8, UTF-16 with or without a BOM."""
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16", errors="replace")
    sample = raw[:4096]
    if b"\0" in sample:
        half = max(len(sample) // 2, 1)
        even, odd = sample[0::2].count(0), sample[1::2].count(0)
        if odd > 0.4 * half and even < 0.05 * half:
            return raw.decode("utf-16-le", errors="replace")
        if even > 0.4 * half and odd < 0.05 * half:
            return raw.decode("utf-16-be", errors="replace")
        return None
    return raw.decode("utf-8", errors="replace")


def scan_text(where: str, text: str, deny, out: list[Finding], allow_waiver: bool = False) -> None:
    for number, line in enumerate(text.splitlines(), 1):
        for _entry, pattern in deny:
            match = pattern.search(line)
            if match:
                out.append(Finding(where, number, "personal term", match.group(0)))
        for match in SECRETS.finditer(line):
            out.append(Finding(where, number, "secret-token", match.group(0)[:12] + "..."))
        if allow_waiver and WAIVER in line:
            continue
        for name, pattern in GENERIC:
            for match in pattern.finditer(line):
                hit = match.group(0)
                if name == "email" and ALLOWED_EMAIL.match(hit):
                    continue
                out.append(Finding(where, number, name, hit))


def scan_file(path: str, raw: bytes, deny, out: list[Finding]) -> None:
    scan_text(f"(file name) {path}", path, deny, out)
    if REVIEWED_FILES.get(path) == hashlib.sha256(raw).hexdigest():
        return
    ext = Path(path).suffix.lower()
    text = decode(raw)
    if ext in UNSCANNABLE_EXT or (text is None and ext not in ALLOWED_BINARY_EXT):
        out.append(Finding(path, 0, "unscannable file", f"{ext or 'no extension'}, {len(raw)} bytes"))
        return
    if text is not None:
        scan_text(path, text, deny, out, allow_waiver=path in WAIVER_FILES)


def check_identity(where: str, ident: str, deny, out: list[Finding]) -> None:
    """ident is 'Name <email>' (a trailing timestamp is ignored)."""
    match = re.match(r"^(.*?)\s*<([^>]*)>", ident)
    if not match:
        out.append(Finding(where, 0, "identity", f"unreadable identity: {ident[:60]}"))
        return
    name, email = match.group(1), match.group(2)
    scan_text(where, name, deny, out)
    if not ALLOWED_IDENTITY_EMAIL.match(email):
        out.append(Finding(where, 0, "identity", f"e-mail must be *.invalid or a GitHub noreply address, got {email}"))


def scan_staged(root: Path, deny, out: list[Finding]) -> str:
    names = [n for n in git(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRT").split("\0") if n]
    for name in names:
        scan_file(name, git(root, "show", f":{name}", binary=True), deny, out)
    for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        check_identity(f"({var})", git(root, "var", var).strip(), deny, out)
    return f"{len(names)} staged file(s) and the commit identity"


def scan_message(path: Path, deny, out: list[Finding]) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    scan_text("(commit message)", "\n".join(line for line in lines if not line.startswith("#")), deny, out)
    return "the commit message"


def read_objects(root: Path, shas: list[str]):
    """Yield (sha, type, bytes) for each object, via one 'git cat-file --batch' call."""
    if not shas:
        return
    data = git(root, "cat-file", "--batch", binary=True, stdin=("\n".join(shas) + "\n").encode())
    pos = 0
    while pos < len(data):
        end = data.index(b"\n", pos)
        header = data[pos:end].decode("utf-8", errors="replace").split()
        if len(header) < 3:  # "<sha> missing"
            pos = end + 1
            continue
        size = int(header[2])
        yield header[0], header[1], data[end + 1 : end + 1 + size]
        pos = end + 1 + size + 1


def scan_history(root: Path, deny, out: list[Finding]) -> str:
    paths: dict[str, str] = {}
    shas: list[str] = []
    for line in git(root, "rev-list", "--all", "--objects").splitlines():
        sha, _, path = line.partition(" ")
        shas.append(sha)
        if path:
            paths.setdefault(sha, path)
    shas += git(root, "for-each-ref", "refs/tags", "--format=%(objectname)").split()
    counts = {"commit": 0, "tag": 0, "blob": 0}
    for sha, kind, body in read_objects(root, shas):
        if kind in ("commit", "tag"):
            counts[kind] += 1
            text = body.decode("utf-8", errors="replace")
            where = f"{kind} {sha[:10]}"
            for header in re.findall(r"^(?:author|committer|tagger) (.*)$", text, re.MULTILINE):
                check_identity(where, header, deny, out)
            scan_text(where, text, deny, out)
        elif kind == "blob":
            counts["blob"] += 1
            scan_file(paths.get(sha, f"blob {sha[:10]}"), body, deny, out)
        elif kind == "tree" and sha in paths:
            scan_text(f"(folder name) {paths[sha]}", paths[sha], deny, out)
    return f"{counts['commit']} commit(s), {counts['tag']} annotated tag(s), {counts['blob']} file version(s)"


def scan_tree(root: Path, deny, out: list[Finding]) -> str:
    names = [n for n in git(root, "ls-files", "-z").split("\0") if n]
    for name in names:
        path = root / name
        if path.is_file():
            scan_file(name, path.read_bytes(), deny, out)
    return f"{len(names)} tracked file(s)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block personal information from being committed or published.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--message", type=Path)
    mode.add_argument("--history", action="store_true")
    mode.add_argument("--tree", action="store_true")
    parser.add_argument("--allow-missing-denylist", action="store_true")
    args = parser.parse_args(argv)

    root = repo_root()
    deny = load_denylist(root, args.allow_missing_denylist)
    out: list[Finding] = []
    if args.staged:
        scope = scan_staged(root, deny, out)
    elif args.message:
        scope = scan_message(args.message, deny, out)
    elif args.history:
        scope = scan_history(root, deny, out)
    else:
        scope = scan_tree(root, deny, out)

    if out:
        print(f"privacy guard: BLOCKED. Found in {scope}:", file=sys.stderr)
        for f in out:
            print(f"  {f.where}:{f.line}: [{f.category}] {f.text}", file=sys.stderr)
        print(FIX_HINT, file=sys.stderr)
        return 1
    print(f"privacy guard: clean ({scope}; {len(deny)} personal terms checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
