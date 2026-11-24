"""The state file: what alertd remembers between events.

    {
      "muted": {"price_move:ORVK": "2026-11-04T00:00:00Z", "news:wire:*": null},
      "last_alert": {"limit_usage:rates:VAR": "2026-11-03T09:12:00Z"},
      "sent_today": {"day": "2026-11-03", "count": 4}
    }

muted        mutes, by key. A mute that ends in * mutes every key that starts with what comes before the *
             (news:wire:* mutes every news alert from the wire). Its value is the time the mute runs out, or null
             for a mute that stays until it is lifted (alertd unmute). A mute applies to events seen before it
             runs out.
last_alert   the time of the last alert sent for each key (the cooldown goes by it)
sent_today   how many alerts were sent on a day (UTC); the count starts again from zero on a new day

Every part may be left out; an empty object is an empty state. `alertd replay` reads the state and never writes
it; `alertd run` writes it back after the feed."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from alertd.errors import StateError
from alertd.timeutil import day_of, format_time, parse_time


class State:
    def __init__(self, muted: dict[str, datetime | None] | None = None,
                 last_alert: dict[str, datetime] | None = None, day: str | None = None, count: int = 0):
        self.muted = dict(muted or {})
        self.last_alert = dict(last_alert or {})
        self.day = day
        self.count = count

    # ----- reading and writing --------------------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: object, where: str = "state") -> "State":
        if not isinstance(data, dict):
            raise StateError(f"{where}: the state must be a JSON object")
        unknown = sorted(set(data) - {"muted", "last_alert", "sent_today"})
        if unknown:
            raise StateError(f"{where}: unknown part(s) {', '.join(unknown)}")
        try:
            muted = {}
            for key, until in (data.get("muted") or {}).items():
                muted[_key(key)] = None if until is None else parse_time(until, f"muted[{key!r}]")
            last_alert = {_key(key): parse_time(at, f"last_alert[{key!r}]")
                          for key, at in (data.get("last_alert") or {}).items()}
            sent = data.get("sent_today") or {}
            day, count = sent.get("day"), sent.get("count", 0)
            if day is not None:
                parse_time(f"{day}T00:00:00Z", "sent_today.day")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"sent_today.count must be a whole number, zero or more, got {count!r}")
        except (ValueError, AttributeError, TypeError) as exc:
            raise StateError(f"{where}: {exc}") from None
        return cls(muted, last_alert, day, count)

    @classmethod
    def load(cls, path: str | Path) -> "State":
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise StateError(f"cannot read the state file {path}: {exc.strerror or exc}") from None
        try:
            data = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            raise StateError(f"{path}: not JSON ({exc.msg})") from None
        return cls.from_dict(data, str(path))

    def to_dict(self) -> dict:
        return {
            "muted": {key: None if until is None else format_time(until) for key, until in sorted(self.muted.items())},
            "last_alert": {key: format_time(at) for key, at in sorted(self.last_alert.items())},
            "sent_today": {"day": self.day, "count": self.count},
        }

    def save(self, path: str | Path) -> None:
        """Write the state, replacing the file in one step (a reader never sees half a file)."""
        path = Path(path)
        text = json.dumps(self.to_dict(), indent=2) + "\n"
        try:
            fd, temp = tempfile.mkstemp(prefix=".state-", dir=path.parent or ".")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(temp, path)
        except OSError as exc:
            raise StateError(f"cannot write the state file {path}: {exc.strerror or exc}") from None

    # ----- mutes ------------------------------------------------------------------------------------------------

    def mute(self, key: str, until: datetime | None = None) -> None:
        self.muted[_key(key)] = until

    def unmute(self, key: str) -> bool:
        """Lift a mute (the exact entry); False if there was none."""
        return self.muted.pop(key, "absent") != "absent"

    def mute_for(self, key: str, at: datetime) -> str | None:
        """The mute entry that mutes ``key`` at ``at``, or None."""
        for entry, until in sorted(self.muted.items()):
            if until is not None and at >= until:
                continue
            if entry == key or (entry.endswith("*") and key.startswith(entry[:-1])):
                return entry
        return None

    def is_muted(self, key: str, at: datetime) -> bool:
        return self.mute_for(key, at) is not None

    # ----- alerts sent ------------------------------------------------------------------------------------------

    def last_alert_for(self, key: str) -> datetime | None:
        return self.last_alert.get(key)

    def sent_on(self, day: str) -> int:
        """Alerts sent on ``day`` (UTC), as far as the state knows."""
        return self.count if self.day == day else 0

    def record_sent(self, key: str, at: datetime) -> None:
        """An alert went out: it starts its key's cooldown and counts towards its day's cap, whatever its kind."""
        day = day_of(at)
        if self.day != day:
            self.day, self.count = day, 0
        self.count += 1
        self.last_alert[key] = at


def _key(key: object) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"a key must be a non-empty string, got {key!r}")
    return key
