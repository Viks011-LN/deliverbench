"""Deciding events: the rule, then the shared suppressions, then the message.

For each event the engine finds its kind's rule (registry.py); an event of a kind with no rule is skipped with a
note. The rule says whether the event is worth an alert (a Finding) or not (None). A finding goes through the shared
suppressions (suppress.py). If one applies, the alert is not sent and its tag follows the reasons. If none does,
the alert is sent: it is recorded in the state (its key's last alert, and the day's count) and its message is
written in the house style (format.py).

An event its rule cannot read (an EventError) is skipped with a note; the rest of the feed is decided as usual."""
from __future__ import annotations

from typing import Callable, Iterable, Iterator

from alertd import format as fmt
from alertd import registry
from alertd.config import Settings
from alertd.errors import EventError
from alertd.feed import Event
from alertd.model import Decision
from alertd.state import State
from alertd.suppress import first_suppression


class Engine:
    def __init__(self, settings: Settings, state: State, rules: dict | None = None,
                 note: Callable[[str], None] | None = None):
        self.settings = settings
        self.state = state
        self.rules = registry.RULES if rules is None else rules
        self.note = note or (lambda text: None)
        self.alerts = settings.section("alerts")

    def decide(self, event: Event) -> Decision | None:
        """The decision for one event, or None when it is skipped. A sent alert is recorded in the state."""
        rule = self.rules.get(event.kind)
        if rule is None:
            self.note(f"{event.where()}: no rule for kind {event.kind!r}; skipped")
            return None
        try:
            key = rule.key(event)
            finding = rule.evaluate(event, self.settings.section(event.kind))
        except EventError as exc:
            self.note(f"{event.where()}: skipped: {exc}")
            return None
        if finding is None:
            return Decision(event.id, event.kind, key, sent=False, level=None)
        tag = first_suppression(finding, event.at, self.state, self.alerts)
        if tag is not None:
            return Decision(event.id, event.kind, finding.key, sent=False, level=finding.level,
                            reasons=[*finding.reasons, tag])
        self.state.record_sent(finding.key, event.at)
        text = fmt.message(finding.level, finding.subject, finding.what, finding.detail)
        return Decision(event.id, event.kind, finding.key, sent=True, level=finding.level,
                        reasons=list(finding.reasons), message=text)

    def replay(self, events: Iterable[Event]) -> Iterator[Decision]:
        """Decisions for the events, in their order (skipped events give none)."""
        for event in events:
            decision = self.decide(event)
            if decision is not None:
                yield decision
