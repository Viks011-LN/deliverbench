"""Fetched third-party documents (house rule 4 as amended; docs/PLAN-V2.md section 2.3, point 8).

A job may rest on a published standard or paper that a real colleague would have open (T11: the ISDA CDS Standard
Model's documents). Such documents are never part of a job's folder; T11's two are shipped unchanged in
documents/ (owner's decision, 24 Nov 2026). Each is declared in the job's deliverbench.toml:

    [[documents]]
    name = "isda-numerical-fix-2012"               # a short id
    title = "ISDA CDS Standard Model: Numerical Fix (2012)"
    url = "https://..."                            # the publisher's address
    backup_url = "https://web.archive.org/..."     # a public archive copy, used when the first has moved
    sha256 = "..."                                 # the exact file the job was built and checked against
    room_file = "fetched/isda-numerical-fix-2012.txt"   # under environment/, git-ignored, copied into the room
    passages = ["...", "..."]                      # text the job rests on, which must survive the conversion
    char_map = {"\u0734" = "R"}                    # optional: repairs a font's wrong character codes, in order
    text_sha256 = "..."                            # optional: the converted text's checksum, once checked
    local_source = "..."                               # instead of url and backup_url: where a copy comes from, for a
                                                   # document with no stable public address (the owner's choice)

`dbench documents <job>` fetches each one (from a local cache first, then the copy shipped in documents/, then the
address, then the backup), refuses a
file whose checksum differs (a moved document, or an address that now serves a home page, fails loudly), converts
it to text with page markers, checks that every passage survived, and writes the room file. The room stays offline:
the text is copied in when the room is built.

A document with no stable public address is declared with `local` (a sentence on where a copy comes from) instead
of url and backup_url. Its file is added once with `dbench documents --add <file>`, which stores it in the local
cache under its checksum; a build without it fails and says how to add it.

One converter for every machine (pypdf, pinned in uv.lock), so a room's text, and with it the job folder's checksum,
is the same wherever it is built; text_sha256 makes any drift fail loudly. Some PDFs set mathematics in a font whose
character codes map to unrelated letters (a recovery rate R arrives as a Syriac letter); char_map repairs those
codes, declared and reviewed per document, never edited by hand in the output.
"""
from __future__ import annotations

import hashlib
import io
import re
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / ".cache" / "documents"
SHIPPED = REPO / "documents"  # copies published with the repo, named <name>.pdf, checked like any other source
FETCHED_DIR = "fetched/"
USER_AGENT = "deliverbench-documents/1.0"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DocumentError(RuntimeError):
    pass


@dataclass
class Document:
    name: str
    title: str
    url: str
    backup_url: str
    sha256: str
    room_file: str
    passages: list[str] = field(default_factory=list)
    char_map: dict[str, str] = field(default_factory=dict)
    text_sha256: str = ""
    local_source: str = ""

    @staticmethod
    def from_toml(entry: dict) -> "Document":
        return Document(name=str(entry.get("name", "")), title=str(entry.get("title", "")),
                        url=str(entry.get("url", "")), backup_url=str(entry.get("backup_url", "")),
                        sha256=str(entry.get("sha256", "")).lower(), room_file=str(entry.get("room_file", "")),
                        passages=[str(p) for p in entry.get("passages", [])],
                        char_map={str(k): str(v) for k, v in (entry.get("char_map") or {}).items()},
                        text_sha256=str(entry.get("text_sha256", "")).lower(),
                        local_source=str(entry.get("local_source", "")))


def document_problems(doc: Document) -> list[str]:
    """What the validator refuses in a declaration (no network needed)."""
    where = f"document {doc.name or '?'}"
    problems = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", doc.name):
        problems.append(f"{where}: name must be a short id of lower-case letters, digits, dots and dashes")
    if not doc.title.strip():
        problems.append(f"{where}: needs a title")
    if doc.local_source:
        if doc.url or doc.backup_url:
            problems.append(f"{where}: a local document has no url or backup_url")
    else:
        for key in ("url", "backup_url"):
            if not getattr(doc, key).startswith("https://"):
                problems.append(f"{where}: {key} must be an https address (or declare it local)")
        if doc.url == doc.backup_url:
            problems.append(f"{where}: backup_url must be a second address, not the same one")
    if not SHA256.match(doc.sha256):
        problems.append(f"{where}: sha256 must be the 64 hex characters of the file's checksum")
    if not doc.room_file.startswith(FETCHED_DIR) or ".." in doc.room_file or not doc.room_file.endswith(".txt"):
        problems.append(f"{where}: room_file must be a .txt file under environment/{FETCHED_DIR}")
    if not doc.passages or any(len(normalise(p)) < 12 for p in doc.passages):
        problems.append(f"{where}: needs passages (each at least 12 characters) that the job rests on")
    if any(len(k) != 1 for k in doc.char_map):
        problems.append(f"{where}: char_map maps single characters")
    if doc.text_sha256 and not SHA256.match(doc.text_sha256):
        problems.append(f"{where}: text_sha256 must be 64 hex characters")
    return problems


def normalise(text: str) -> str:
    """Whitespace collapsed, for comparing a passage with converted text (layout differs between converters)."""
    return re.sub(r"\s+", " ", text).strip()


def _download(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - https only, checked above
        return resp.read()


def obtain(doc: Document, offline: bool = False, download=_download) -> bytes:
    """The document's bytes, checked against its sha256: the cache, else the copy shipped in documents/, else the
    address, else the backup."""
    cached = CACHE / doc.sha256
    if cached.is_file() and hashlib.sha256(cached.read_bytes()).hexdigest() == doc.sha256:
        return cached.read_bytes()
    shipped = SHIPPED / f"{doc.name}.pdf"
    if shipped.is_file() and hashlib.sha256(shipped.read_bytes()).hexdigest() == doc.sha256:
        return shipped.read_bytes()
    if doc.local_source:
        raise DocumentError(f"document {doc.name} ({doc.title}) has no public address: {doc.local_source}. Add your copy "
                            f"once with: dbench documents --add <file> (its sha256 must be {doc.sha256})")
    if offline:
        raise DocumentError(f"document {doc.name}: not in the cache, and --offline was given")
    tried = []
    for url in (doc.url, doc.backup_url):
        try:
            data = download(url)
        except Exception as exc:  # noqa: BLE001 - try the next address, then fail loudly with both reasons
            tried.append(f"{url}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest == doc.sha256:
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
            return data
        tried.append(f"{url}: a different file (sha256 {digest[:16]}..., {len(data):,} bytes)")
    raise DocumentError(f"document {doc.name}: neither address gave the recorded file (sha256 "
                        f"{doc.sha256[:16]}...):\n  " + "\n  ".join(tried))


def to_text(data: bytes, char_map: dict[str, str] | None = None) -> str:
    """Text with a [page N] line before each page, from pypdf (the one converter, pinned), with the document's
    char_map applied; anything that is not a PDF is read as UTF-8 text."""
    if data.startswith(b"%PDF"):
        import logging

        from pypdf import PdfReader

        logging.getLogger("pypdf").setLevel(logging.ERROR)  # font notes that do not change the text
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(f"[page {i}]\n{(page.extract_text() or '').rstrip()}" for i, page in enumerate(reader.pages, 1))
    else:
        text = data.decode("utf-8")
    for old, new in (char_map or {}).items():
        text = text.replace(old, new)
    return text


def lost_passages(doc: Document, text: str) -> list[str]:
    flat = normalise(text)
    return [p for p in doc.passages if normalise(p) not in flat]


def _git_ignored(path: Path) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=REPO).returncode == 0


def fetch(job_path: Path, docs: list[Document], offline: bool = False, download=_download) -> list[Path]:
    """Fetch, check, convert and write every document of one job. Returns the room files written."""
    written = []
    for doc in docs:
        problems = document_problems(doc)
        if problems:
            raise DocumentError("; ".join(problems))
        target = job_path / "environment" / doc.room_file
        if not _git_ignored(target):
            raise DocumentError(f"document {doc.name}: {target} is not git-ignored; fetched documents are never "
                                "committed (house rule 4)")
        text = to_text(obtain(doc, offline, download), doc.char_map)
        lost = lost_passages(doc, text)
        if lost:
            raise DocumentError(f"document {doc.name}: passages lost in the conversion to text: "
                                + "; ".join(repr(p[:60]) for p in lost))
        text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if doc.text_sha256 and text_digest != doc.text_sha256:
            raise DocumentError(f"document {doc.name}: the converted text differs from the one recorded (text_sha256 "
                                f"{text_digest[:16]}..., recorded {doc.text_sha256[:16]}...): the converter changed")
        header = (f"{doc.title}\nSource: {doc.url}\nFile checksum (sha256): {doc.sha256}\n"
                  f"Converted to text for this room; [page N] marks the start of each page of the original.\n\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(header + text + "\n", encoding="utf-8")
        written.append(target)
    return written


def add_local(path: Path) -> str:
    """Store a local copy of a document in the cache under its checksum; returns the checksum."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / digest).write_bytes(data)
    return digest


def unfetched(job_path: Path, docs: list[Document]) -> list[str]:
    """Documents whose room file is not there yet (run `dbench documents` before building the room)."""
    return [d.name for d in docs if not (job_path / "environment" / d.room_file).is_file()]
