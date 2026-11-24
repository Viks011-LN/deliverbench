"""What a settings change would have changed: `alertd what-if --feed F --state S --config A --with B`.

The feed is decided twice from the same state, once with each settings file, and every event whose decision differs
(sent, level, reasons or message) is printed with both decisions. Reviewers of a settings change run it on
yesterday's feed (docs/operations.md, "Changing settings")."""
from __future__ import annotations

from dataclasses import dataclass

from alertd.config import Settings
from alertd.engine import Engine
from alertd.feed import Event
from alertd.model import Decision
from alertd.state import State

COMPARED = ("sent", "level", "reasons", "message")


@dataclass
class Difference:
    id: str
    kind: str
    before: Decision | None
    after: Decision | None

    def fields(self) -> list[str]:
        """The decision's fields that differ (all of them when one side made no decision)."""
        if self.before is None or self.after is None:
            return list(COMPARED)
        a, b = self.before.as_dict(), self.after.as_dict()
        return [name for name in COMPARED if a[name] != b[name]]


def _decisions(events: list[Event], settings: Settings, state_data: dict) -> dict[str, Decision]:
    engine = Engine(settings, State.from_dict(state_data))
    return {decision.id: decision for decision in engine.replay(events)}


def compare(events: list[Event], state: State, before: Settings, after: Settings) -> list[Difference]:
    """Every event decided differently with ``after`` than with ``before``, in feed order. The state is not changed."""
    data = state.to_dict()
    first, second = _decisions(events, before, data), _decisions(events, after, data)
    differences = []
    for event in events:
        a, b = first.get(event.id), second.get(event.id)
        if a is None and b is None:
            continue
        if a is None or b is None or any(a.as_dict()[name] != b.as_dict()[name] for name in COMPARED):
            differences.append(Difference(event.id, event.kind, a, b))
    return differences


def _short(decision: Decision | None) -> str:
    if decision is None:
        return "skipped"
    if decision.level is None:
        return "no alert"
    verb = "sent" if decision.sent else "held"
    return f"{verb} {decision.level} [{', '.join(decision.reasons)}]"


def render(differences: list[Difference], total: int) -> list[str]:
    lines = [f"{len(differences)} of {total} events decided differently"]
    for difference in differences:
        lines.append(f"{difference.id} ({difference.kind}): {_short(difference.before)} -> {_short(difference.after)}")
        if "message" in difference.fields() and difference.before and difference.after:
            lines.append(f"  message: {difference.before.message!r} -> {difference.after.message!r}")
    return lines
