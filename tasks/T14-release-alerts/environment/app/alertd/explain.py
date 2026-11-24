"""Why alertd decided what it did for one event: `alertd explain --feed F --state S --id ID [--config C]`.

The feed is decided from the state up to the event, as `replay` would decide it, so the cooldowns and the day's
count are what they were when the event came in. The event's decision is then shown step by step: what its rule
found, and each shared suppression in turn, with the figures it looked at. Nothing is sent or written."""
from __future__ import annotations

from datetime import datetime

from alertd import format as fmt
from alertd.engine import Engine
from alertd.errors import AlertdError, EventError
from alertd.feed import Event
from alertd.levels import is_critical
from alertd.model import Finding
from alertd.state import State
from alertd.suppress import CHECKS, CRITICAL_PASSES, ORDER
from alertd.timeutil import day_of, format_time, minutes_between


def explain(events: list[Event], event_id: str, engine: Engine) -> list[str]:
    """The explanation of one event's decision, as lines of text."""
    for event in events:
        if event.id == event_id:
            return explain_event(event, engine)
        engine.decide(event)
    raise AlertdError(f"no event with id {event_id!r} in the feed")


def explain_event(event: Event, engine: Engine) -> list[str]:
    lines = [f"event {event.id} ({event.kind}), seen at {format_time(event.at)}"]
    rule = engine.rules.get(event.kind)
    if rule is None:
        return lines + [f"rule: none for kind {event.kind!r}, so the event is skipped"]
    try:
        key = rule.key(event)
        finding = rule.evaluate(event, engine.settings.section(event.kind))
    except EventError as exc:
        return lines + [f"rule: cannot read the event ({exc}), so it is skipped"]
    if finding is None:
        return lines + [f"rule: not worth an alert (key {key})", "decision: nothing to send"]
    lines.append(f"rule: {finding.level}, reasons {', '.join(finding.reasons)} (key {finding.key})")
    lines.append(f"  the message would be: {fmt.message(finding.level, finding.subject, finding.what, finding.detail)}")
    stopped = None
    for tag in ORDER:
        if stopped is not None:
            lines.append(f"{tag}: not looked at")
            continue
        found = CHECKS[tag](finding, event.at, engine.state, engine.alerts)
        detail = describe(tag, finding, event.at, engine.state, engine.alerts)
        if tag in CRITICAL_PASSES and is_critical(finding.level):
            lines.append(f"{tag}: passed, the alert is critical ({detail})")
        elif found:
            stopped = tag
            lines.append(f"{tag}: applies ({detail})")
        else:
            lines.append(f"{tag}: does not apply ({detail})")
    lines.append("decision: " + ("sent" if stopped is None else f"not sent, {stopped}"))
    return lines


def describe(tag: str, finding: Finding, at: datetime, state: State, alerts: dict) -> str:
    """The figures one suppression looks at, in words."""
    if tag == "stale":
        if finding.stale_after is None:
            return "this kind is never stale"
        age = minutes_between(finding.as_of, at)
        return f"figures {fmt.number(age, 1)} min old, {fmt.number(finding.stale_after.total_seconds() / 60, 0)} allowed"
    if tag == "muted":
        entry = state.mute_for(finding.key, at)
        return "no mute matches the key" if entry is None else f"muted by {entry}"
    if tag == "quiet_hours":
        return f"quiet from {alerts['quiet_start']} to {alerts['quiet_end']} UTC"
    if tag == "cooldown":
        last = state.last_alert_for(finding.key)
        if last is None:
            return "no alert sent for the key before"
        return (f"last alert {fmt.number(minutes_between(last, at), 1)} min before, "
                f"cooldown {fmt.number(alerts['cooldown_minutes'], 0)} min")
    if tag == "daily_cap":
        return f"{state.sent_on(day_of(at))} sent on {day_of(at)}, cap {fmt.number(alerts['daily_cap'], 0)}"
    return ""
