"""The feed: one event per line, as JSON.

Every event is a JSON object with at least ``kind`` (which rule decides it), ``id`` (unique within the feed) and
``at`` (the time alertd sees the event, in UTC). The other fields depend on the kind; each kind's page in
docs/desk/ lists them. Blank lines are ignored.

A line that is not such an object is a FeedError, which stops the feed: alertd will not guess where one event ends
and the next begins. A field that a rule cannot read is an EventError for that event alone (engine.py)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from alertd.errors import EventError, FeedError
from alertd.timeutil import parse_time

REQUIRED = ("kind", "id", "at")


@dataclass(frozen=True)
class Event:
    """One event from the feed. Rules read its fields through the helpers below, which raise EventError (naming the
    field) when a field is absent or of the wrong type."""

    id: str
    kind: str
    at: datetime
    fields: dict = field(repr=False, compare=False)
    line: int = 0

    def where(self) -> str:
        """Where the event is, for notes: line 7 (id r07)."""
        return f"line {self.line} (id {self.id})"

    def has(self, name: str) -> bool:
        """Whether the field is present and not null."""
        return self.fields.get(name) is not None

    def get(self, name: str, default=None):
        value = self.fields.get(name)
        return default if value is None else value

    def text(self, name: str) -> str:
        """A field that must be a non-empty string."""
        value = self.fields.get(name)
        if not isinstance(value, str) or not value.strip():
            raise EventError(f"{name} must be a non-empty string, got {value!r}")
        return value

    def number(self, name: str) -> float:
        """A field that must be a number (an integer or a decimal, never true or false)."""
        value = self.fields.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise EventError(f"{name} must be a number, got {value!r}")
        return float(value)

    def optional_number(self, name: str) -> float | None:
        """A number, or None when the field is absent or null."""
        if self.fields.get(name) is None:
            return None
        return self.number(name)

    def time(self, name: str) -> datetime:
        """A field that must be a UTC time (timeutil.parse_time)."""
        try:
            return parse_time(self.fields.get(name), name)
        except ValueError as exc:
            raise EventError(str(exc)) from None

    def choice(self, name: str, options: Iterable[str]) -> str:
        """A field that must be one of ``options``."""
        options = tuple(options)
        value = self.fields.get(name)
        if value not in options:
            raise EventError(f"{name} must be one of {', '.join(options)}, got {value!r}")
        return value

    def strings(self, name: str) -> list[str]:
        """A list of non-empty strings; an absent or null field is an empty list."""
        value = self.fields.get(name)
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise EventError(f"{name} must be a list of non-empty strings, got {value!r}")
        return list(value)


def parse_line(text: str, line: int = 0) -> Event:
    """One feed line as an Event; FeedError if it is not one."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FeedError(f"line {line}: not JSON ({exc.msg})") from None
    if not isinstance(data, dict):
        raise FeedError(f"line {line}: an event must be a JSON object")
    for name in REQUIRED:
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise FeedError(f"line {line}: an event needs {name!r}, a non-empty string")
    try:
        at = parse_time(data["at"], "at")
    except ValueError as exc:
        raise FeedError(f"line {line}: {exc}") from None
    return Event(id=data["id"], kind=data["kind"], at=at, fields=data, line=line)


def parse_lines(lines: Iterable[str]) -> Iterator[Event]:
    """The events of a feed's lines, in order. An id may appear only once."""
    seen: set[str] = set()
    for number, text in enumerate(lines, 1):
        if not text.strip():
            continue
        event = parse_line(text, number)
        if event.id in seen:
            raise FeedError(f"line {number}: id {event.id!r} appears twice in the feed")
        seen.add(event.id)
        yield event


def read_feed(path: str | Path) -> list[Event]:
    """Every event in a feed file, in the order of its lines."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise FeedError(f"cannot read the feed {path}: {exc.strerror or exc}") from None
    return list(parse_lines(text.splitlines()))
