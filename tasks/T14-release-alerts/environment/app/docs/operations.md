# Running alertd on the desk

How the desk runs alertd day to day. The README has the commands; this page has the routine.

## The minute job

The scheduler collects the events of the last minute from the desk's sources into one feed, in the order they
arrived, and runs

    python -m alertd run --feed batch.jsonl --state state/alerts-state.json --outbox state/outbox.txt \
        --history state/history.jsonl

from the alertd folder. `run` reads the state, decides the batch, appends the alerts it sends to the outbox and
every decision to the history, and writes the state back. The chat bridge posts each new line of the outbox to the
desk's channel. Nothing else writes the state file while `run` is working; the scheduler never starts a second
`run` before the first has finished.

If `run` stops with exit status 2, the batch is kept and retried the next minute, and the bridge posts the error
line to the support channel. A batch that fails three times in a row pages the support engineer.

## Mutes during an incident

When a source misbehaves, mute its alerts rather than stopping alertd, so that the other kinds keep coming:

    python -m alertd mute 'price_move:*' --for 60 --state state/alerts-state.json

A mute ending in `*` covers every key with that start. Remember that critical alerts still come through a mute;
that is deliberate. `show-state` lists the mutes in force and `unmute` lifts one early.

## When the desk asks "why did (or didn't) I get this alert?"

Take the batch from the archive and the state as it was before it (the scheduler keeps both for a week), and run

    python -m alertd explain --feed batch.jsonl --state before.json --id <event id>

It decides the batch up to that event and then shows its rule's finding and each suppression in turn. `history`
answers the quicker question of what was decided for a key during the day:

    python -m alertd history --history state/history.jsonl --key 'limit_usage:rates:*' --since 2026-11-03T00:00:00Z

## The morning note

The note quotes yesterday's digest:

    python -m alertd replay --feed archive/yesterday.jsonl --state archive/yesterday-start.json > decisions.jsonl
    python -m alertd digest decisions.jsonl

## Changing settings

Settings changes go through review like code: change `config/alerts.toml`, run `check-config` and the tests, and
show the reviewer what the change would have done to yesterday's feed:

    python -m alertd what-if --feed archive/yesterday.jsonl --state archive/yesterday-start.json \
        --config config/alerts.toml --with proposed.toml
 A key that is not declared in
`alertd/defaults.toml` is refused when the file is loaded, so the minute job would stop with exit status 2: check
before you deploy.

## A new source

The feed team runs `check-feed` on a sample of a new source's events before it goes live. Events of kinds alertd
has no rule for are only noted; events its rules cannot read are problems and must be fixed at the source.
