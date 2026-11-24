"""What a rule finds, and what the engine decides."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from alertd.levels import check


@dataclass
class Finding:
    """An event worth an alert, as its rule sees it, before the shared suppressions.

    key          the alert's key; mutes and the cooldown go by it. It starts with the kind: price_move:ORVK
    level        info, warning or critical (alertd/levels.py)
    reasons      why the event is worth an alert, as tags, in the order the kind's page gives
    subject      what the alert is about, the part of the message before the colon
    what         what happened
    detail       the figures behind it, written in brackets after ``what``; None for none
    as_of        when the figures in the event were true: the stale suppression measures their age from here
    stale_after  how old the figures may be before the alert is stale (the kind's stale_after_minutes setting);
                 None for a kind whose alerts are never stale
    """

    key: str
    level: str
    reasons: list[str]
    subject: str
    what: str
    detail: str | None
    as_of: datetime
    stale_after: timedelta | None = None

    def __post_init__(self) -> None:
        check(self.level)
        if not self.reasons:
            raise ValueError("a finding needs at least one reason")


@dataclass
class Decision:
    """What alertd decided for one event; replay prints it as one JSON line (README.md, "The replay output")."""

    id: str
    kind: str
    key: str
    sent: bool
    level: str | None
    reasons: list[str] = field(default_factory=list)
    message: str | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "key": self.key, "sent": self.sent, "level": self.level,
                "reasons": list(self.reasons), "message": self.message}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)
