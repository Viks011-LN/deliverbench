"""Fetched third-party documents (house rule 4 as amended; dbench/documents.py)."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from dbench import documents as docs_mod
from dbench.documents import Document, DocumentError, document_problems, fetch, to_text

REPO = Path(__file__).resolve().parents[1]
TEXT = b"Standard CDS conventions.\nThe premium accrues on an ACT/360 basis from the step-in date.\n"


def minimal_pdf(line: str) -> bytes:
    """A one-page PDF with one line of text, built by hand (offsets computed), for the converter."""
    stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def doc(data: bytes = TEXT, passages=("accrues on an ACT/360 basis",), **kw) -> Document:
    return Document(name=kw.get("name", "conventions"), title="Conventions", url="https://example.org/a",
                    backup_url="https://archive.example.org/a", sha256=hashlib.sha256(data).hexdigest(),
                    room_file=kw.get("room_file", "fetched/conventions.txt"), passages=list(passages))


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(docs_mod, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(docs_mod, "SHIPPED", tmp_path / "shipped")
    monkeypatch.setattr(docs_mod, "_git_ignored", lambda path: True)
    job = tmp_path / "job"
    (job / "environment").mkdir(parents=True)
    return job


def serving(pages: dict[str, bytes]):
    calls = []

    def download(url):
        calls.append(url)
        if url not in pages:
            raise OSError("not found")
        return pages[url]
    download.calls = calls
    return download


def test_a_document_is_fetched_checked_converted_and_cached(sandbox):
    d = doc()
    (written,) = fetch(sandbox, [d], download=serving({d.url: TEXT}))
    text = written.read_text()
    assert "accrues on an ACT/360 basis" in text and d.sha256 in text
    fetch(sandbox, [d], offline=True)  # the second time, from the cache alone


def test_a_moved_document_falls_back_to_its_backup(sandbox):
    d = doc()
    download = serving({d.url: b"<html>Welcome to our new home page</html>", d.backup_url: TEXT})
    fetch(sandbox, [d], download=download)
    assert download.calls == [d.url, d.backup_url]


def test_a_changed_document_fails_loudly(sandbox):
    d = doc()
    with pytest.raises(DocumentError, match="neither address gave the recorded file"):
        fetch(sandbox, [d], download=serving({d.url: TEXT + b"edited", d.backup_url: b"<html>home</html>"}))


def test_a_passage_lost_in_conversion_fails(sandbox):
    d = doc(passages=("the half-day adjustment applies",))
    with pytest.raises(DocumentError, match="passages lost"):
        fetch(sandbox, [d], download=serving({d.url: TEXT}))


def test_pdfs_are_converted_with_page_markers():
    text = to_text(minimal_pdf("Protection leg value at the step-in date"))
    assert text.startswith("[page 1]") and "Protection leg value at the step-in date" in text


def test_offline_without_a_cache_refuses(sandbox):
    with pytest.raises(DocumentError, match="offline"):
        fetch(sandbox, [doc()], offline=True)


def test_declarations_are_checked_without_the_network():
    good = doc()
    assert document_problems(good) == []
    bad = Document(name="Bad Name", title="", url="http://x", backup_url="http://x", sha256="abc",
                   room_file="environment/x.pdf", passages=["short"])
    problems = " ".join(document_problems(bad))
    for words in ("short id", "title", "https", "second address", "sha256", "fetched/", "passages"):
        assert words in problems


def test_fetched_room_files_are_git_ignored_and_nothing_fetched_is_committed():
    ignored = subprocess.run(["git", "check-ignore", "-q", "tasks/T11-x/environment/fetched/a.txt"], cwd=REPO)
    assert ignored.returncode == 0
    not_ignored = subprocess.run(["git", "check-ignore", "-q", "tasks/T11-x/environment/a.txt"], cwd=REPO)
    assert not_ignored.returncode == 1
    tracked = subprocess.run(["git", "ls-files", "tasks/*/environment/fetched", ".cache"], cwd=REPO,
                             capture_output=True, text=True).stdout.strip()
    assert tracked == ""


def test_a_room_file_outside_the_ignored_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(docs_mod, "CACHE", tmp_path / "cache")
    job = REPO / "tasks" / "T00-hello-fix"   # a real job folder: environment/fetched/ there is git-ignored
    d = doc()
    d.room_file = "fetched/../conventions.txt"
    with pytest.raises(DocumentError, match="room_file"):
        fetch(job, [d], download=serving({d.url: TEXT}))


def test_a_char_map_repairs_a_fonts_wrong_codes_and_the_text_checksum_catches_drift(sandbox):
    data = "If \u0734 is a recovery rate, the leg is (1\u0d46\u0734) times the loss.\n".encode()
    d = doc(data=data, passages=("If R is a recovery rate, the leg is (1-R)",))
    d.char_map = {"\u0734": "R", "\u0d46": "-"}
    (written,) = fetch(sandbox, [d], download=serving({d.url: data}))
    assert "(1-R)" in written.read_text()
    d.text_sha256 = "0" * 64
    with pytest.raises(DocumentError, match="converter changed"):
        fetch(sandbox, [d], offline=True)


def test_a_local_document_comes_from_the_cache_and_says_how_to_add_it(sandbox, tmp_path):
    d = doc()
    d.url = d.backup_url = ""
    d.local_source = "the owner's copy; the paper has no stable public address"
    assert document_problems(d) == []
    with pytest.raises(DocumentError, match="dbench documents --add"):
        fetch(sandbox, [d], download=serving({}))
    copy = tmp_path / "paper.txt"
    copy.write_bytes(TEXT)
    assert docs_mod.add_local(copy) == d.sha256
    (written,) = fetch(sandbox, [d], download=serving({}))
    assert "accrues on an ACT/360 basis" in written.read_text()
    d.url = "https://example.org/a"
    assert any("no url" in p for p in document_problems(d))


def test_a_shipped_copy_is_used_before_any_address_and_only_if_it_is_the_recorded_file(sandbox, tmp_path):
    d = doc()
    d.url = d.backup_url = ""
    d.local_source = "no stable public address"
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "conventions.pdf").write_bytes(TEXT + b"changed")
    with pytest.raises(DocumentError, match="dbench documents --add"):
        fetch(sandbox, [d], download=serving({}))
    (shipped / "conventions.pdf").write_bytes(TEXT)
    (written,) = fetch(sandbox, [d], download=serving({}))
    assert "accrues on an ACT/360 basis" in written.read_text()


def test_t11s_shipped_documents_match_its_declarations():
    from dbench.tasks import load_job  # noqa: PLC0415 - only this test needs the job loader
    for d in load_job(REPO / "tasks" / "T11-cds-pricing").documents:
        shipped = REPO / "documents" / f"{d.name}.pdf"
        assert hashlib.sha256(shipped.read_bytes()).hexdigest() == d.sha256, d.name
