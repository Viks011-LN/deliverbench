"""The command line: python -m alertd <command> [options] (README.md, "Running alertd").

main() returns the exit status: 0 when the command did its work, 2 when alertd refused its input (a config, feed or
state it cannot use; the reason is one line on stderr). Notes about single events go to stderr and do not change
the exit status."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from alertd import __version__, digest, explain, feedcheck, history, whatif
from alertd.config import DEFAULT_CONFIG, load_settings
from alertd.engine import Engine
from alertd.errors import AlertdError, StateError
from alertd.feed import read_feed
from alertd.outbox import Outbox
from alertd.state import State
from alertd.timeutil import format_time, parse_time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alertd", description="The desk's alert system.")
    parser.add_argument("--version", action="version", version=f"alertd {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    def config_option(command):
        command.add_argument("--config", default=None,
                             help=f"the settings file (default: {DEFAULT_CONFIG}, if it exists)")

    replay = commands.add_parser("replay", help="decide every event in a feed and print the decisions")
    replay.add_argument("--feed", required=True, help="the feed, one JSON event per line")
    replay.add_argument("--state", required=True, help="the state to start from (never written)")
    config_option(replay)

    run = commands.add_parser("run", help="decide a feed, send the alerts to an outbox and save the state")
    run.add_argument("--feed", required=True)
    run.add_argument("--state", required=True, help="the state to start from, written back at the end")
    run.add_argument("--outbox", required=True, help="the file the alerts sent are appended to")
    run.add_argument("--history", default=None, help="a file every decision is appended to (alertd/history.py)")
    config_option(run)

    explain = commands.add_parser("explain", help="show step by step how one event of a feed is decided")
    explain.add_argument("--feed", required=True)
    explain.add_argument("--state", required=True, help="the state the feed starts from (never written)")
    explain.add_argument("--id", required=True, help="the event's id")
    config_option(explain)

    what_if = commands.add_parser("what-if", help="decide a feed with two settings files and print what differs")
    what_if.add_argument("--feed", required=True)
    what_if.add_argument("--state", required=True, help="the state both runs start from (never written)")
    what_if.add_argument("--config", required=True, help="the settings in force")
    what_if.add_argument("--with", dest="other", required=True, help="the settings to compare them with")

    digest = commands.add_parser("digest", help="count the decisions in a file replay wrote")
    digest.add_argument("decisions")

    check_feed = commands.add_parser("check-feed", help="check that every event in a feed can be decided")
    check_feed.add_argument("--feed", required=True)
    config_option(check_feed)

    history = commands.add_parser("history", help="print a decision history in short")
    history.add_argument("--history", required=True)
    history.add_argument("--key", default=None, help="only this key (a prefix ending in * works)")
    history.add_argument("--since", default=None, help="only from this time on (UTC)")
    history.add_argument("--sent", action="store_true", help="only the alerts sent")

    check = commands.add_parser("check-config", help="check a settings file against alertd/defaults.toml")
    config_option(check)

    settings = commands.add_parser("settings", help="print every setting, its value and where it comes from")
    config_option(settings)

    mute = commands.add_parser("mute", help="mute a key, or every key with a prefix (ending in *)")
    mute.add_argument("key")
    mute.add_argument("--for", dest="minutes", type=float, default=None,
                      help="minutes from now until the mute runs out (default: until unmuted)")
    mute.add_argument("--state", required=True)

    unmute = commands.add_parser("unmute", help="lift a mute")
    unmute.add_argument("key")
    unmute.add_argument("--state", required=True)

    show = commands.add_parser("show-state", help="print a state file in short")
    show.add_argument("--state", required=True)
    return parser


def _decide(args, out, err, *, outbox: Outbox | None) -> int:
    settings = load_settings(args.config)
    state = State.load(args.state)
    events = read_feed(args.feed)
    seen_at = {event.id: event.at for event in events}
    engine = Engine(settings, state, note=lambda text: print(f"alertd: note: {text}", file=err))
    for decision in engine.replay(events):
        print(decision.to_json(), file=out, flush=True)
        if outbox is not None and decision.sent:
            outbox.append(seen_at[decision.id], decision.message)
        if getattr(args, "history", None):
            history.append(args.history, seen_at[decision.id], decision)
    if outbox is not None:
        state.save(args.state)
        print(f"alertd: {outbox.written} alert(s) sent to {args.outbox}", file=err)
    return 0


def _explain(args, out) -> int:
    settings = load_settings(args.config)
    engine = Engine(settings, State.load(args.state))
    for line in explain.explain(read_feed(args.feed), args.id, engine):
        print(line, file=out)
    return 0


def _what_if(args, out) -> int:
    events = read_feed(args.feed)
    before, after = load_settings(args.config, required=True), load_settings(args.other, required=True)
    for line in whatif.render(whatif.compare(events, State.load(args.state), before, after), len(events)):
        print(line, file=out)
    return 0


def _digest(args, out) -> int:
    for line in digest.render(digest.summarise(digest.read_decisions(args.decisions))):
        print(line, file=out)
    return 0


def _check_feed(args, out) -> int:
    result = feedcheck.check_feed(read_feed(args.feed), load_settings(args.config))
    for line in feedcheck.render(result):
        print(line, file=out)
    return 1 if result["problems"] else 0


def _history(args, out) -> int:
    since = None
    if args.since is not None:
        try:
            since = parse_time(args.since, "--since")
        except ValueError as exc:
            raise StateError(str(exc)) from None
    for record in history.select(history.read(args.history), args.key, since, args.sent):
        print(history.line(record), file=out)
    return 0


def _check_config(args, out) -> int:
    settings = load_settings(args.config, required=True)
    print(f"{settings.path}: ok ({len(settings.keys())} settings, {len(settings.set_in_file())} set in the file)",
          file=out)
    return 0


def _settings(args, out) -> int:
    settings = load_settings(args.config)
    for key in settings.keys():
        print(f"{key} = {json.dumps(settings.get(key))}  # {settings.source(key)}", file=out)
    return 0


def _mute(args, out, now: datetime) -> int:
    state = State.load(args.state)
    until = None if args.minutes is None else now + timedelta(minutes=args.minutes)
    state.mute(args.key, until)
    state.save(args.state)
    print(f"muted {args.key} " + ("until unmuted" if until is None else f"until {format_time(until)}"), file=out)
    return 0


def _unmute(args, out) -> int:
    state = State.load(args.state)
    if not state.unmute(args.key):
        print(f"{args.key} was not muted", file=out)
        return 0
    state.save(args.state)
    print(f"unmuted {args.key}", file=out)
    return 0


def _show_state(args, out) -> int:
    state = State.load(args.state)
    data = state.to_dict()
    print(f"muted: {len(data['muted'])}", file=out)
    for key, until in data["muted"].items():
        print(f"  {key} until {until or 'unmuted'}", file=out)
    print(f"last alerts: {len(data['last_alert'])}", file=out)
    for key, at in data["last_alert"].items():
        print(f"  {key} at {at}", file=out)
    print(f"sent on {state.day or '-'}: {state.count}", file=out)
    return 0


def main(argv=None, out=None, err=None, now=None) -> int:
    """Run one command. ``out`` and ``err`` default to stdout and stderr; ``now`` (a UTC datetime) to the clock."""
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    now = datetime.now(timezone.utc) if now is None else now
    try:
        if args.command == "replay":
            return _decide(args, out, err, outbox=None)
        if args.command == "run":
            return _decide(args, out, err, outbox=Outbox(args.outbox))
        if args.command == "explain":
            return _explain(args, out)
        if args.command == "what-if":
            return _what_if(args, out)
        if args.command == "digest":
            return _digest(args, out)
        if args.command == "check-feed":
            return _check_feed(args, out)
        if args.command == "history":
            return _history(args, out)
        if args.command == "check-config":
            return _check_config(args, out)
        if args.command == "settings":
            return _settings(args, out)
        if args.command == "mute":
            return _mute(args, out, now)
        if args.command == "unmute":
            return _unmute(args, out)
        return _show_state(args, out)
    except AlertdError as exc:
        print(f"alertd: error: {exc}", file=err)
        return 2
