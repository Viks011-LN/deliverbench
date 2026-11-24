# News

An alert when a story carries a tag the desk watches, or names a ticker on the desk's watchlist.

## The events

Kind `news`, from the news service, one event per story:

| Field | Meaning |
|---|---|
| `source` | where the story comes from, e.g. `wire` |
| `headline` | the headline |
| `published_at` | when the story was published (UTC) |
| `tickers` | the tickers it names (may be empty) |
| `tags` | the news service's tags (may be empty) |

## The rules

- A tag in `news.watch_tags` makes the story a `warning`, one in `news.critical_tags` `critical`; the reason is
  `tag`.
- A ticker on `news.watchlist` adds the reason `watchlist`. With no watched tag, the story is `info`; with one, it
  is one level more serious (a `warning` becomes `critical`).
- Otherwise the story is not worth an alert.
- A story older than `news.stale_after_minutes` when alertd sees it is stale.
- The key is `news:<source>:<first ticker>`, or `news:<source>:-` for a story with no ticker.

## Messages

The subject is the first ticker (the source when there is none), then the headline, shortened to 80 characters,
then the source and the watched tags:

    CRITICAL KSVH: Kesvora Holdings shares suspended pending announcement (wire, tags: halt)
    INFO ORVK: Orvik Energy names new chief financial officer (dowline)
