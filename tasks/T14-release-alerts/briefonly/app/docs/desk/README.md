# The desk's pages

One page for each kind of alert, with the rules the desk agreed for it: the events it reads, what makes an event
worth an alert, its levels and reasons, its key, its settings and what its messages look like.

| Page | Kind |
|---|---|
| `price-moves.md` | `price_move` |
| `limit-usage.md` | `limit_usage` |
| `stale-feeds.md` | `stale_feed` |
| `news.md` | `news` |
| `release-alerts.md` | `release` |

Mutes, quiet hours, the cooldown and the daily cap are not on these pages: they are the same for every kind, and
`alertd/suppress.py` is their reference.
