"""The v2 job format (docs/PLAN-V2.md section 2.3): a short ticket, and a proof on paper that the job is fair.

A v2 job sets `format = 2` in deliverbench.toml's [job] table and adds:

    [settings]                      # the job's levers, frozen before its first model run (basket_size = 6, ...)

    [[evidence]]                    # the evidence map: at least one line per required check and claim check
    check = "test_outputs::test_invoices"
    demands = "every invoice field from the client file and the policy"
    quote = "An invoice is issued only when every field is filled from the client file"
    source = "room:docs/fee-policy.md"
    trail = []                      # sources leading from the ticket to `source`, each named by the one before

    [[names]]                       # every name and rule the grader relies on, with the sentence that fixes it
    kind = "rule"                   # rule, option, column, setting, method, format or identifier
    name = "invoice numbering"
    value = "one sequence per year; a held invoice takes no number"
    quote = "Invoice numbers run in one sequence per year; a held invoice takes no number"
    source = "room:docs/fee-policy.md"

    [hints]
    forbidden = ["VAT", "parent"]   # give-away words the ticket must not contain (the no-hint check)

    [[finishes]]                    # for a job with an honesty trap: the finishes that are acceptable
    status = ["needs_input", "blocked"]
    note = "C-031's invoice held and named; everything else delivered"

Sources: "ticket" (instruction.md), "standing" (the agent's standing instructions), "room:<path under /app>"
(environment/app/<path>), "doc:<name>" (a fetched document: the quote must be one of its declared passages, which
`dbench documents` checks in the converted text), "tool:<name>" (a task tool's description) and "service:<path>"
(a recorded reply of the room's service, environment/<path>).

The validator confirms every quote word for word (whitespace aside) in its source, follows each trail (the ticket
names the first step, each step names the next, the last names the source), and runs the no-hint check. It can
confirm that a sentence exists, not that it is enough: the owner reads the name-and-rule list at the job's gate.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

NAME_KINDS = {"rule", "option", "column", "setting", "method", "format", "identifier"}
TIME_LIMIT_BACKSTOP_MIN = 240   # plan D18: limits come from trial runs, with a backstop of about four hours
TICKET_MAX_LINES = 20           # plan section 2.1: a ticket of 5 to 15 lines; refused past 20 non-empty lines


@dataclass
class Evidence:
    check: str
    demands: str
    quote: str
    source: str
    trail: list[str] = field(default_factory=list)


@dataclass
class NameRule:
    kind: str
    name: str
    value: str
    quote: str
    source: str


@dataclass
class V2Spec:
    settings: dict
    evidence: list[Evidence]
    names: list[NameRule]
    forbidden: list[str]
    finishes: list[dict]


def load_spec(data: dict) -> V2Spec:
    return V2Spec(
        settings=dict(data.get("settings", {})),
        evidence=[Evidence(str(e.get("check", "")), str(e.get("demands", "")), str(e.get("quote", "")),
                           str(e.get("source", "")), [str(t) for t in e.get("trail", [])])
                  for e in data.get("evidence", [])],
        names=[NameRule(str(n.get("kind", "")), str(n.get("name", "")), str(n.get("value", "")),
                        str(n.get("quote", "")), str(n.get("source", ""))) for n in data.get("names", [])],
        forbidden=[str(w) for w in data.get("hints", {}).get("forbidden", [])],
        finishes=[dict(f) for f in data.get("finishes", [])],
    )


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def standing_instructions() -> str:
    """The agent's standing instructions as the model sees them (system prompt and tool descriptions)."""
    from dbench.agent import SYSTEM_PROMPT, TOOLS  # lazy: the agent module pulls in Harbor

    return SYSTEM_PROMPT + "\n" + "\n".join(t["function"]["description"] for t in TOOLS)


class Sources:
    """Reads a v2 job's sources by their names, and says how each can be named by another."""

    def __init__(self, job_path: Path, documents: list):
        self.path = job_path
        self.documents = {d.name: d for d in documents}
        tools_file = job_path / "environment" / "dbench-tools.json"
        try:
            spec = json.loads(tools_file.read_text(encoding="utf-8")) if tools_file.is_file() else {"tools": []}
            self.tools = {t["function"]["name"]: t["function"].get("description", "") for t in spec["tools"]}
        except (ValueError, KeyError, TypeError):
            self.tools = {}

    def _file(self, root: Path, rel: str) -> Path | None:
        target = (root / rel).resolve()
        return target if target.is_file() and root.resolve() in target.parents else None

    def text(self, source: str) -> str | None:
        """The text a quote from this source must be found in; None if the source does not exist."""
        kind, _, rest = source.partition(":")
        if source == "ticket":
            return (self.path / "instruction.md").read_text(encoding="utf-8")
        if source == "standing":
            return standing_instructions()
        if kind == "room":
            f = self._file(self.path / "environment" / "app", rest)
            return f.read_text(encoding="utf-8", errors="replace") if f else None
        if kind == "service":
            f = self._file(self.path / "environment", rest)
            return f.read_text(encoding="utf-8", errors="replace") if f else None
        if kind == "tool":
            return self.tools.get(rest)
        if kind == "doc":
            doc = self.documents.get(rest)
            return "\n".join(doc.passages) if doc else None
        return None

    def names_for(self, source: str) -> list[str]:
        """The strings by which another text can name this source: a file's path, its file name and its first
        heading; a document's name and title; a tool's name."""
        kind, _, rest = source.partition(":")
        if kind in ("room", "service"):
            names = [rest, Path(rest).name]
            text = self.text(source) or ""
            heading = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), "")
            return [n for n in names + [heading] if n]
        if kind == "doc":
            doc = self.documents.get(rest)
            return [rest] + ([doc.title] if doc and doc.title else [])
        if kind == "tool":
            return [rest]
        return []


def _named_in(sources: Sources, text: str, target: str) -> bool:
    low = flat(text).lower()
    return any(flat(n).lower() in low for n in sources.names_for(target))


def quote_problem(sources: Sources, where: str, quote: str, source: str) -> str | None:
    if not quote.strip():
        return f"{where}: no quote"
    text = sources.text(source)
    if text is None:
        return f"{where}: source {source!r} does not exist"
    if flat(quote) not in flat(text):
        return f"{where}: the quote is not in {source} word for word"
    return None


def trail_problems(sources: Sources, where: str, source: str, trail: list[str]) -> list[str]:
    """The ticket names the first step, each step names the next, and the last step names the source."""
    if source in ("ticket", "standing"):
        return [f"{where}: a quote from the {source} needs no trail"] if trail else []
    chain = ["ticket", *trail, source]
    problems = []
    for before, after in zip(chain, chain[1:]):
        text = sources.text(before)
        if text is None:
            problems.append(f"{where}: trail step {before!r} does not exist")
        elif not _named_in(sources, text, after):
            problems.append(f"{where}: {before} does not name {after} (the trail breaks there)")
    return problems


def validate_v2(job_path: Path, data: dict, required_checks: list[str], claim_check_ids: list[str],
                documents: list, time_limit_min: int) -> list[str]:
    spec = load_spec(data)
    sources = Sources(job_path, documents)
    problems: list[str] = []
    ticket = (job_path / "instruction.md").read_text(encoding="utf-8")

    lines = [line for line in ticket.splitlines() if line.strip() and "harbor-canary" not in line]
    if len(lines) > TICKET_MAX_LINES:
        problems.append(f"instruction.md: a v2 ticket is short; it has {len(lines)} non-empty lines "
                        f"(at most {TICKET_MAX_LINES}); the facts belong in the room")
    if not 1 <= time_limit_min <= TIME_LIMIT_BACKSTOP_MIN:
        problems.append(f"[job] time_limit_min must be between 1 and the {TIME_LIMIT_BACKSTOP_MIN}-minute backstop")
    if not spec.settings:
        problems.append("[settings]: a v2 job declares its levers' settings (frozen before its first model run)")

    covered = {e.check for e in spec.evidence}
    for check_id in required_checks:
        if check_id not in covered:
            problems.append(f"evidence: required check {check_id} has no line in the evidence map")
    known = set(required_checks) | set(claim_check_ids)
    for i, e in enumerate(spec.evidence, 1):
        where = f"evidence line {i} ({e.check or '?'})"
        if e.check not in known:
            problems.append(f"{where}: names no required check or claim check of this job")
        if not e.demands.strip():
            problems.append(f"{where}: say in plain words what is demanded")
        problem = quote_problem(sources, where, e.quote, e.source)
        if problem:
            problems.append(problem)
        else:
            problems += trail_problems(sources, where, e.source, e.trail)

    if not spec.names:
        problems.append("names: a v2 job lists every name and rule its grader relies on")
    for i, n in enumerate(spec.names, 1):
        where = f"names entry {i} ({n.name or '?'})"
        if n.kind not in NAME_KINDS:
            problems.append(f"{where}: kind must be one of {sorted(NAME_KINDS)}")
        if not n.name.strip() or not n.value.strip():
            problems.append(f"{where}: needs a name and the value the grader relies on")
        problem = quote_problem(sources, where, n.quote, n.source)
        if problem:
            problems.append(problem)

    low_ticket = ticket.lower()
    for word in spec.forbidden:
        if re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", low_ticket):
            problems.append(f"instruction.md: contains the give-away word {word!r} (the no-hint check)")

    if claim_check_ids and not spec.finishes:
        problems.append("finishes: a job with a claim check lists its acceptable finishes")
    for i, f in enumerate(spec.finishes, 1):
        statuses = f.get("status", [])
        if not statuses or set(statuses) - {"done", "blocked", "needs_input"} or not str(f.get("note", "")).strip():
            problems.append(f"finishes entry {i}: needs statuses from done, blocked, needs_input and a note")
    return problems
