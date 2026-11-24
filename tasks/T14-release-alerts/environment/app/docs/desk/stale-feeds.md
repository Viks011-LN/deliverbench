# Stale feeds

An alert when a data feed the desk relies on stops updating. (This kind of alert is about the feeds; it has nothing
to do with the `stale` suppression, which stops alerts on old figures.)

## The events

Kind `stale_feed`, from the feed monitor, every few minutes for each feed:

| Field | Meaning |
|---|---|
| `feed` | the feed's name, e.g. `prices-eu` |
| `last_update` | when the feed last updated (UTC) |

## The rules

- The silence is the time from `last_update` to `at`.
- A silence of at least `stale_feed.warn_after_minutes` is a `warning`; of at least
  `stale_feed.critical_after_minutes`, `critical`.
- The reason is `silent`.
- These alerts are never stale themselves: a silent feed is worth knowing about however late alertd hears of it.
- The key is `stale_feed:<feed>`.

## Messages

    WARNING prices-eu: no update for 23 min (last at 09:12 UTC)
