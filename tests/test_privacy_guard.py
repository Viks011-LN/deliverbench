"""Tests for scripts/privacy_guard.py, run against throwaway git repos.

Every test value that the guard should catch is assembled at run time, so this file
never contains a real address, path, token or personal term and can itself be committed.
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = Path(os.environ.get("PRIVACY_GUARD_UNDER_TEST", REPO / "scripts" / "privacy_guard.py"))

PRIVATE_IP = ".".join(["192", "168", "7", "21"])
CGNAT_IP = ".".join(["100", "72", "1", "9"])
DOC_IP = ".".join(["192", "0", "2", "10"])  # RFC 5737 documentation range: allowed
PERSONAL_TERM = "zq" + "personal" + "marker"  # stands in for a real name on the denylist
REAL_EMAIL = "someone" + "@" + "realmail" + ".com"
WIN_HOME = "C:" + "\\Users\\" + "alice" + "\\notes.txt"
WIN_HOME_LOWER = "c:" + "\\users\\" + "alice" + "\\notes.txt"
WSL_HOME = "\\\\wsl.localhost" + "\\Ubuntu\\home\\" + "alice"
MAC = ":".join(["4A", "11", "22", "33", "44", "55"])
MAC_HYPHEN = "-".join(["4A", "11", "22", "33", "44", "55"])
ULA_IPV6 = "fd" + "12:3456:789a::1"
LAN_HOST = "nas" + ".local" + ":8080"
TOKENS = ["sk-" + "a1" * 12, "hf_" + "b2" * 12, "gh" + "p_" + "c3" * 12,
          "-----BEGIN " + "OPENSSH PRIVATE KEY-----", "-----BEGIN " + "PRIVATE KEY-----",
          "Authorization: " + "Bearer " + "d4" * 12]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def guard(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GUARD), *args], cwd=repo, capture_output=True, text=True)


def stage(repo: Path, name: str, content: str | bytes, encoding: str = "utf-8") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding=encoding, newline="\n")
    git(repo, "add", name)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@test.invalid")
    git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / ".privacy").mkdir()
    (tmp_path / ".privacy" / "denylist.local.txt").write_text(
        f"# test list\n{PERSONAL_TERM}\nre:\\bACME\\b\n", encoding="utf-8"
    )
    return tmp_path


# --- staged content ---------------------------------------------------------------------------

def test_clean_file_passes(repo):
    stage(repo, "a.txt", f"hello world\nendpoint = http://localhost:8000/v1\nworkdir = /home/agent/work\nexample {DOC_IP}\nsee endpoints.local.toml\n")
    result = guard(repo, "--staged")
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_denylist_term_blocks_in_any_case(repo):
    stage(repo, "a.txt", f"written by {PERSONAL_TERM.upper()}\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "personal term" in result.stderr


def test_denylist_regex_entry_uses_word_boundaries(repo):
    stage(repo, "a.txt", "acmeish is fine\n")
    assert guard(repo, "--staged").returncode == 0
    stage(repo, "b.txt", "worked at Acme for years\n")
    assert guard(repo, "--staged").returncode == 1


@pytest.mark.parametrize("value,category", [
    (PRIVATE_IP, "private-ip"),
    (CGNAT_IP, "private-ip"),
    (ULA_IPV6, "ipv6-local"),
    (REAL_EMAIL, "email"),
    (WIN_HOME, "home-path"),
    (WIN_HOME_LOWER, "home-path"),
    (WSL_HOME, "home-path"),
    ("/home/" + "alice" + "/x", "home-path"),
    ("/mnt/c/Users/" + "alice", "home-path"),
    (MAC, "mac-address"),
    (MAC_HYPHEN, "mac-address"),
    (LAN_HOST, "lan-host"),
])
def test_generic_patterns_block(repo, value, category):
    stage(repo, "a.txt", f"value = {value}\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1, f"{category} not caught"
    assert f"[{category}]" in result.stderr


@pytest.mark.parametrize("token", TOKENS)
def test_secret_tokens_block(repo, token):
    stage(repo, "a.txt", f"key = {token}\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "[secret-token]" in result.stderr


def test_a_byte_order_mark_does_not_hide_the_first_denylist_term(repo):
    (repo / ".privacy" / "denylist.local.txt").write_text(f"{PERSONAL_TERM}\n", encoding="utf-8-sig")
    stage(repo, "a.txt", f"written by {PERSONAL_TERM}\n")
    assert guard(repo, "--staged").returncode == 1


def test_placeholder_emails_pass(repo):
    allowed = ["user@example.com", "noreply@anthropic.com", "maintainer@project.invalid"]
    stage(repo, "a.txt", "\n".join(allowed) + "\n")
    result = guard(repo, "--staged")
    assert result.returncode == 0, result.stderr


def test_source_escapes_before_decorators_pass(repo):
    stage(repo, "a.py", r'text = "import pytest\n\n@pytest.fixture"' + "\n")
    result = guard(repo, "--staged")
    assert result.returncode == 0, result.stderr


def test_file_name_is_scanned(repo):
    stage(repo, f"notes-{PERSONAL_TERM}.txt", "clean content\n")
    assert guard(repo, "--staged").returncode == 1


# --- encodings and files that can't be scanned --------------------------------------------------

def test_utf16_with_bom_is_decoded(repo):
    stage(repo, "freeze.txt", f"path {WIN_HOME}\n", encoding="utf-16")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "[home-path]" in result.stderr


def test_utf16_without_bom_is_decoded(repo):
    stage(repo, "freeze.txt", f"by {PERSONAL_TERM}\n".encode("utf-16-le"))
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "personal term" in result.stderr


def test_binary_file_is_refused(repo):
    stage(repo, "blob.bin", bytes(range(256)) * 4)
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "[unscannable file]" in result.stderr


def test_office_document_is_refused(repo):
    stage(repo, "report.xlsx", "looks like text but is a container\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "[unscannable file]" in result.stderr


# --- the waiver ----------------------------------------------------------------------------------

def test_waiver_is_honoured_only_in_the_guards_own_files(repo):
    stage(repo, "scripts/privacy_guard.py", f"pattern example {PRIVATE_IP}  # privacy-ok\n")
    assert guard(repo, "--staged").returncode == 0
    stage(repo, "notes.txt", f"{PRIVATE_IP}  # privacy-ok\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "notes.txt" in result.stderr


def test_waiver_never_covers_personal_terms_or_tokens(repo):
    stage(repo, "scripts/privacy_guard.py", f"{PERSONAL_TERM}  # privacy-ok\n")
    assert guard(repo, "--staged").returncode == 1
    git(repo, "rm", "-q", "--cached", "scripts/privacy_guard.py")
    stage(repo, "tests/test_privacy_guard.py", f"{TOKENS[0]}  # privacy-ok\n")
    assert guard(repo, "--staged").returncode == 1


# --- commit identity -----------------------------------------------------------------------------

def test_author_name_is_scanned(repo):
    git(repo, "config", "user.name", PERSONAL_TERM)
    stage(repo, "a.txt", "clean content\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "GIT_AUTHOR_IDENT" in result.stderr


@pytest.mark.parametrize("email,ok", [
    ("tester@example.com", False),
    (REAL_EMAIL, False),
    ("1234+someone" + "@" + "users.noreply.github.com", True),
    ("maintainer@project.invalid", True),
])
def test_identity_email_must_be_a_placeholder(repo, email, ok):
    git(repo, "config", "user.email", email)
    stage(repo, "a.txt", "clean content\n")
    result = guard(repo, "--staged")
    assert (result.returncode == 0) == ok, result.stderr
    if not ok:
        assert "[identity]" in result.stderr


# --- automatic personal terms --------------------------------------------------------------------

def test_os_user_name_is_added_automatically(repo):
    user = getpass.getuser()
    if len(user) < 4 or user.lower() in {"user", "admin", "root", "runner", "agent", "ubuntu", "docker", "vagrant"}:
        pytest.skip("user name too generic to be auto-added")
    (repo / ".privacy" / "denylist.local.txt").write_text("", encoding="utf-8")
    stage(repo, "a.txt", f"owner: {user}\n")
    assert guard(repo, "--staged").returncode == 1


def test_endpoint_hosts_are_added_automatically(repo):
    host = "bignode" + "box"
    (repo / "endpoints.local.toml").write_text(f'[a]\nurl = "http://{host}:8000/v1"\n', encoding="utf-8")
    stage(repo, "a.txt", f"served by {host}\n")
    result = guard(repo, "--staged")
    assert result.returncode == 1
    assert "personal term" in result.stderr


# --- message, history, tree ----------------------------------------------------------------------

def test_message_mode(repo, tmp_path):
    msg = tmp_path / "MSG"
    msg.write_text(f"Add thing\n\n# comment lines are ignored: {REAL_EMAIL}\n", encoding="utf-8")
    assert guard(repo, "--message", str(msg)).returncode == 0
    msg.write_text(f"Add thing\n\nReported by {REAL_EMAIL}\n", encoding="utf-8")
    assert guard(repo, "--message", str(msg)).returncode == 1


def test_history_finds_a_term_that_was_later_deleted(repo):
    stage(repo, "a.txt", f"{PERSONAL_TERM}\n")
    git(repo, "commit", "-q", "-m", "add")
    (repo / "a.txt").write_text("clean\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "clean up")
    assert guard(repo, "--tree").returncode == 0
    result = guard(repo, "--history")
    assert result.returncode == 1
    assert "personal term" in result.stderr


def test_history_finds_a_utf16_file_from_an_old_commit(repo):
    stage(repo, "freeze.txt", f"path {WIN_HOME}\n", encoding="utf-16")
    git(repo, "commit", "-q", "-m", "add")
    git(repo, "rm", "-q", "freeze.txt")
    git(repo, "commit", "-q", "-m", "remove")
    result = guard(repo, "--history")
    assert result.returncode == 1
    assert "[home-path]" in result.stderr


def test_history_ignores_decorators(repo):
    stage(repo, "test_x.py", "import pytest\n\n@pytest.fixture\ndef thing():\n    return 1\n")
    git(repo, "commit", "-q", "-m", "add")
    result = guard(repo, "--history")
    assert result.returncode == 0, result.stderr


def test_history_checks_author_fields(repo):
    git(repo, "config", "user.email", REAL_EMAIL)
    stage(repo, "a.txt", "clean\n")
    git(repo, "commit", "-q", "-m", "add")
    result = guard(repo, "--history")
    assert result.returncode == 1
    assert "[identity]" in result.stderr


def test_history_checks_annotated_tags(repo):
    stage(repo, "a.txt", "clean\n")
    git(repo, "commit", "-q", "-m", "add")
    git(repo, "tag", "-a", "v0", "-m", f"release by {PERSONAL_TERM}")
    result = guard(repo, "--history")
    assert result.returncode == 1
    assert "tag " in result.stderr


def test_missing_denylist_is_a_setup_error(repo):
    (repo / ".privacy" / "denylist.local.txt").unlink()
    stage(repo, "a.txt", "clean\n")
    assert guard(repo, "--staged").returncode == 2
    assert guard(repo, "--staged", "--allow-missing-denylist").returncode == 0


# --- the hooks in this repo ----------------------------------------------------------------------

def test_hooks_are_committed_as_executable():
    lines = git(REPO, "ls-files", "-s", "scripts/hooks").splitlines()
    names = {line.split("\t")[1] for line in lines}
    assert {"scripts/hooks/pre-commit", "scripts/hooks/commit-msg", "scripts/hooks/pre-push",
            "scripts/hooks/pre-merge-commit"} <= names
    for line in lines:
        assert line.startswith("100755"), f"not executable in git: {line}"


def test_a_reviewed_document_passes_only_at_its_path_with_its_exact_bytes(repo):
    pdf = (REPO / "documents" / "okane-turnbull-2003.pdf").read_bytes()
    stage(repo, "documents/okane-turnbull-2003.pdf", pdf)
    assert guard(repo, "--staged").returncode == 0
    stage(repo, "documents/okane-turnbull-2003.pdf", pdf + b"%")
    assert "[unscannable file]" in guard(repo, "--staged").stderr
    git(repo, "rm", "-q", "--cached", "documents/okane-turnbull-2003.pdf")
    stage(repo, "elsewhere/okane-turnbull-2003.pdf", pdf)
    assert "[unscannable file]" in guard(repo, "--staged").stderr
