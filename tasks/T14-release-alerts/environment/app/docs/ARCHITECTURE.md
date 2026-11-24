# How alertd is put together

Last reviewed for alertd 1.4.0 (September 2025). What has changed since is in docs/CHANGELOG.md.

## The flow

    feed --> engine --> rule for the kind --> suppressions --> message --> outbox
                ^                                  |
                +------------- state <-------------+

alertd is one process that reads a feed from start to end. Nothing runs in the background and nothing is shared
between runs except the state file and the outbox.

## The parts

| Module | Its job |
|---|---|
| `feed.py` | reads the feed: one JSON object per line, each with `kind`, `id` and `at`; `Event` gives the rules typed access to the other fields |
| `registry.py` | maps each kind to its rule |
| `rules/` | one module per kind; a rule turns an event into a `Finding` (key, level, reasons, the parts of the message) or nothing |
| `suppress.py` | the suppressions every alert goes through |
| `engine.py` | runs an event through its rule and the suppressions, records what was sent |
| `state.py` | mutes, the last alert per key, the count of alerts sent today |
| `format.py` | the house style of messages |
| `config.py`, `defaults.toml` | settings: every key declared with its default, a config file over them |
| `cli.py` | the commands |

## Rules

A rule knows about its own kind only. It reads the event, compares it with its settings and says whether it is worth
an alert, at what level and why. It does not know whether the alert will be sent.

The levels are `info`, `warning` and `critical`. Each kind's page in `docs/desk/` gives its own thresholds, levels
and reason tags.

## Suppressions

Every alert, of every kind, goes through the same suppressions after its rule. They are checked in this order, and
the first that applies stops the alert and adds its tag after the reasons:

1. `muted`: the alert's key is muted in the state.
2. `quiet_hours`: the event comes in during quiet hours.
3. `cooldown`: an alert with the same key went out less than the cooldown before.
4. `daily_cap`: the day's cap of alerts has been reached.
5. `stale`: the figures behind the alert are older than its kind allows.

Critical alerts pass mutes, quiet hours and the daily cap.

A mute names one key and lasts until it runs out or is lifted.

## Messages

`format.message(level, subject, what, detail)` writes `<LEVEL> <subject>: <what> (<detail>)`. Rules build the
subject, what and detail with the number helpers in `format.py`, so every kind writes figures alike.

## Settings

`alertd/defaults.toml` declares every setting with its default. `config/alerts.toml` sets the desk's values; an
undeclared key is refused when the file is loaded, so a typing mistake is caught before any event is decided.

## Tests

`tests/` has a test module for each module above and one for the examples. `python -m pytest` runs them all.
