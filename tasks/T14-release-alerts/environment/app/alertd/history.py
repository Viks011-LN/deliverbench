"""The decision history.

`alertd run --history H` appends every decision it makes to H, one JSON object per line: the decision's fields
(README.md, "The replay output") and ``at``, the time alertd saw the event. `alertd history --history H` prints the
history in short, one line per decision, optionally only for a key (a prefix ending in * works as for mutes), only
from a time on, or only the alerts sent. The history is never read back by the engine; the state file is what
alertd remembers."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from alertd.errors import StateError
from alertd.model import Decision
from alertd.timeutil import format_time, parse_time


def append(path: str | Path, at: datetime, decision: Decision) -> None:
    record = {"at": format_time(at), **decision.as_dict()}
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise StateError(f"cannot write the history {path}: {exc.strerror or exc}") from None


def read(path: str | Path) -> list[dict]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise StateError(f"cannot read the history {path}: {exc.strerror or exc}") from None
    records = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            parse_time(record["at"], "at")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            raise StateError(f"{path} line {number}: not a history record") from None
        records.append(record)
    return records


def matches_key(pattern: str, key: str) -> bool:
    return pattern == key or (pattern.endswith("*") and key.startswith(pattern[:-1]))


def select(records: list[dict], key: str | None = None, since: datetime | None = None,
           sent_only: bool = False) -> list[dict]:
    chosen = []
    for record in records:
        if key is not None and not matches_key(key, record["key"]):
            continue
        if since is not None and parse_time(record["at"]) < since:
            continue
        if sent_only and not record["sent"]:
            continue
        chosen.append(record)
    return chosen


def line(record: dict) -> str:
    """One record in short: when, what, and what became of it."""
    if record["sent"]:
        outcome = f"sent {record['level']}"
    elif record["level"] is None:
        outcome = "no alert"
    else:
        outcome = f"held {record['level']} ({record['reasons'][-1]})"
    return f"{record['at']}  {record['key']}  {outcome}"
