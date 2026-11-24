# alertd

alertd is the desk's alert system. It reads events from a feed, decides for each whether the desk should be
alerted and how urgently, and sends the alerts worth sending to the desk's chat (through an outbox file the chat
bridge reads). Version 1.6.2; the changes are in docs/CHANGELOG.md.

## Running alertd

alertd needs Python 3.11 or later and nothing outside the standard library. Run it from this folder:

    python -m alertd <command> [options]

`bin/alertd <command> [options]` does the same from any folder.

| Command | What it does |
|---|---|
| `replay --feed F --state S [--config C]` | decides every event in the feed F, starting from the state file S, and prints one decision per event (below). It sends nothing and never writes S, so a feed can be replayed as often as you like |
| `run --feed F --state S --outbox O [--history H] [--config C]` | decides the feed as `replay` does, appends every alert sent to the outbox O (and every decision to the history H) and writes the state back to S |
| `explain --feed F --state S --id ID [--config C]` | shows step by step how one event of the feed is decided: its rule, then each suppression |
| `what-if --feed F --state S --config A --with B` | decides the feed with two settings files and prints every event decided differently |
| `digest FILE` | counts the decisions in a file `replay` wrote: by kind, by level, and held back by each suppression |
| `check-feed --feed F [--config C]` | checks that every event in a feed can be decided by its rule |
| `history --history H [--key K] [--since T] [--sent]` | prints a decision history in short |
| `check-config [--config C]` | checks a settings file against `alertd/defaults.toml` |
| `settings [--config C]` | prints every setting, its value and where the value comes from |
| `mute KEY [--for MINUTES] --state S`, `unmute KEY --state S` | mutes a key, or every key with a prefix (a key ending in `*`), for a while or until unmuted |
| `show-state --state S` | prints a state file in short |

`--config` defaults to `config/alerts.toml`. The exit status is 0 when the command did its work and 2 when alertd
refuses its input (a settings file, feed or state it cannot use); the reason is one line on stderr.

## The replay output

`replay` prints one JSON object per line, one for each event it decides, in the order of the feed:

| Field | What it holds |
|---|---|
| `id` | the event's id |
| `kind` | the event's kind |
| `key` | the alert's key; mutes and the cooldown go by it |
| `sent` | `true` when the alert goes out |
| `level` | `info`, `warning` or `critical`; `null` when the event is not worth an alert |
| `reasons` | why the event is worth an alert, as tags (each kind's page lists its own), followed by the tag of the suppression that stopped it, if one did; `[]` when the event is not worth an alert |
| `message` | the message sent, in the house style; `null` when nothing is sent |

For example:

    {"id": "p03", "kind": "price_move", "key": "price_move:ORVK", "sent": true, "level": "warning", "reasons": ["move"], "message": "WARNING ORVK: price down 3.12% (last 41.27, from 42.60)"}
    {"id": "p04", "kind": "price_move", "key": "price_move:BRHW", "sent": false, "level": "warning", "reasons": ["move", "cooldown"], "message": null}

An event of a kind alertd has no rule for is skipped with a note on stderr and prints nothing. So is an event whose
rule cannot read it (a field absent or of the wrong type); the rest of the feed is decided as usual.

## Events

Each line of a feed is a JSON object with `kind`, `id` and `at`, the time alertd sees the event (UTC, written
2026-11-03T10:00:00Z), and the fields its kind needs.

| Kind | Rule | The desk's page |
|---|---|---|
| `price_move` | `alertd/rules/price_move.py` | `docs/desk/price-moves.md` |
| `limit_usage` | `alertd/rules/limit_usage.py` | `docs/desk/limit-usage.md` |
| `stale_feed` | `alertd/rules/stale_feed.py` | `docs/desk/stale-feeds.md` |
| `news` | `alertd/rules/news.py` | `docs/desk/news.md` |
| `release` | `alertd/rules/release.py` | `docs/desk/release-alerts.md` |

`examples/` has a feed for each kind (`feed-<kind>.jsonl`) and the decisions alertd prints for it
(`decisions-<kind>.jsonl`), from `python -m alertd replay --feed examples/feed-<kind>.jsonl --state examples/state.json`.

## How a decision is made

1. The rule for the event's kind decides whether the event is worth an alert, its level and its reasons
   (`alertd/rules/`, one module per kind, registered in `alertd/registry.py`).
2. The shared suppressions decide whether it is sent: staleness, mutes, quiet hours, the cooldown and the daily
   cap, the same for every kind (`alertd/suppress.py`, which gives their order and what passes them).
3. An alert that is sent is recorded in the state and its message is written in the house style
   (`alertd/format.py`). `alertd/engine.py` runs the three steps.

## The state

The state file (`alertd/state.py`) holds the mutes, the time of the last alert sent for each key, and how many
alerts were sent on the current day. A mute names a key, or a prefix ending in `*`, and runs out at a time or stays
until it is lifted.

## Settings

Every setting alertd reads is declared, with its default, in `alertd/defaults.toml`. The desk's own values are in
`config/alerts.toml`, which needs to set only what differs from the defaults; a key that is not declared in the
defaults is an error (`alertd/config.py` has the rules). Shared settings are under `[alerts]`, each kind's under a
table named after the kind.

## Layout

| Path | What it holds |
|---|---|
| `alertd/` | the package: `cli.py`, `engine.py`, `feed.py`, `state.py`, `config.py`, `defaults.toml`, `suppress.py`, `format.py`, `levels.py`, `model.py`, `registry.py`, `outbox.py`, `timeutil.py`, `errors.py`, and the tools `explain.py`, `digest.py`, `feedcheck.py`, `history.py` |
| `alertd/rules/` | one rule per kind |
| `config/alerts.toml` | the desk's settings |
| `docs/` | `ARCHITECTURE.md`, `CHANGELOG.md`, `operations.md` (how the desk runs alertd), `settings.md` (every setting), and `desk/`, the desk's page for each kind of alert |
| `examples/` | example feeds, a state and the decisions alertd prints |
| `tests/` | the tests: `python -m pytest` |
| `CONTRIBUTING.md` | how changes are made |

## Documents

`docs/desk/` holds the rules the desk agreed for each kind of alert; the code follows them. `docs/ARCHITECTURE.md`
describes how alertd is put together and is reviewed less often than the code changes. Where docs/ARCHITECTURE.md
and the code disagree about today's behaviour, the code is right.
