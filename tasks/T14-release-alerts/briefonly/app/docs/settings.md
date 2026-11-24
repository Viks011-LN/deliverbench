# Settings

Every setting alertd reads, as declared in `alertd/defaults.toml`. The desk's values are in `config/alerts.toml`;
`python -m alertd settings` prints the values in force and where each comes from. The rules for config files are
in `alertd/config.py`.

## Shared: `[alerts]`

Read by the suppressions (`alertd/suppress.py`), for every kind alike.

| Key | Default | Meaning |
|---|---|---|
| `alerts.cooldown_minutes` | 30 | no second alert for the same key within this many minutes |
| `alerts.daily_cap` | 25 | at most this many alerts a day (UTC), every kind counted together |
| `alerts.quiet_start` | `"22:00"` | quiet hours start (UTC) |
| `alerts.quiet_end` | `"06:30"` | quiet hours end, not included (UTC) |

## `[price_move]`

| Key | Default | Meaning |
|---|---|---|
| `price_move.threshold_pct` | 1.5 | a price move of at least this many percent is a warning |
| `price_move.threshold_bp` | 8.0 | a yield move of at least this many basis points is a warning |
| `price_move.critical_multiple` | 2.5 | a move of at least this many times its threshold is critical |
| `price_move.stale_after_minutes` | 10 | a quote older than this is stale |

## `[limit_usage]`

| Key | Default | Meaning |
|---|---|---|
| `limit_usage.info_at_pct` | 70.0 | usage of a limit, in percent, from which it is info |
| `limit_usage.warn_at_pct` | 85.0 | ... a warning |
| `limit_usage.critical_at_pct` | 100.0 | ... critical |
| `limit_usage.stale_after_minutes` | 60 | a measurement older than this is stale |

## `[stale_feed]`

| Key | Default | Meaning |
|---|---|---|
| `stale_feed.warn_after_minutes` | 15 | a feed silent for at least this long is a warning |
| `stale_feed.critical_after_minutes` | 45 | ... critical |

## `[news]`

| Key | Default | Meaning |
|---|---|---|
| `news.watch_tags` | guidance, downgrade, profit_warning, default, halt | a story with one of these tags is a warning |
| `news.critical_tags` | default, halt | a story with one of these tags is critical |
| `news.watchlist` | (none) | tickers the desk follows: a story naming one is at least info |
| `news.stale_after_minutes` | 180 | a story published longer ago than this is stale |

## `[release]`

A release is judged against the threshold for its importance (`high`, `medium`, `low`) and its unit (`pct`
percent, `k` thousands, `bn` billions), `release.thresholds.<importance>.<unit>`. A surprise of at least the
threshold is info, at least twice it a warning and at least three times it critical; a revision of at least the
threshold raises the level one step (docs/desk/release-alerts.md).

| Key | Default | Meaning |
|---|---|---|
| `release.thresholds.high.pct` | 0.10 | the threshold for a high-importance release in percent |
| `release.thresholds.high.k` | 15 | ... in thousands |
| `release.thresholds.high.bn` | 1.0 | ... in billions |
| `release.thresholds.medium.pct` | 0.20 | the threshold for a medium-importance release in percent |
| `release.thresholds.medium.k` | 30 | ... in thousands |
| `release.thresholds.medium.bn` | 2.0 | ... in billions |
| `release.thresholds.low.pct` | 0.30 | the threshold for a low-importance release in percent |
| `release.thresholds.low.k` | 50 | ... in thousands |
| `release.thresholds.low.bn` | 3.0 | ... in billions |
| `release.stale_after_minutes` | 120 | a release seen longer than this after it was published is stale |
