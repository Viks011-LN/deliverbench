# Changes

## 1.6.2 (2026-10-14)

- news: headlines longer than 80 characters are shortened, ending in "...".
- `show-state` prints the mutes in key order.
- New command `check-feed`, for the feed team to try a new source before it goes live.

## 1.6.1 (2026-07-21)

- limit_usage: a usage above the limit itself adds the reason `breach` after `usage`.
- `run --history H` keeps every decision; `history` prints it in short.

## 1.6.0 (2026-06-02)

- A mute may end in `*` to mute every key that starts with what comes before it (`news:wire:*`).
- New command `settings`, which prints every setting and where its value comes from.
- New command `explain`, which shows how one event of a feed is decided, suppression by suppression.
- `mute --for MINUTES`.

## 1.5.1 (2026-03-30)

- New command `digest`, for the morning note.

## 1.5.0 (2026-02-17)

- Stale is now the first suppression, so an alert on old figures is reported as `stale` whatever else applies. It
  used to be checked last.
- The daily cap counts every alert sent, of every kind, against one cap (`alerts.daily_cap`). It used to count each
  kind on its own.
- Settings: a config file may set only keys declared in `alertd/defaults.toml`; any other key is an error.

## 1.4.0 (2025-09-08)

- New kind `limit_usage`.
- news: a watched tag on a ticker of the watchlist is one level more serious.

## 1.3.0 (2025-05-12)

- New kind `stale_feed`.
- Quiet hours are settings (`alerts.quiet_start`, `alerts.quiet_end`).
