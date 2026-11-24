# ALRT-212 solve notes: release alerts in alertd

## What I changed, and why

| File | Change |
|---|---|
| `alertd/rules/release.py` (new) | The rule for kind `release`, built like the other rules: `KIND`, `key(event)`, `evaluate(event, settings)` that returns a `Finding` or `None`. It reads fields only through the `Event` helpers and writes the message only with `alertd/format.py` |
| `alertd/registry.py` | Registers `release` next to the four existing kinds |
| `alertd/defaults.toml` | New `[release]` table: `stale_after_minutes = 120`, plus `[release.thresholds.high/medium/low]` with `pct`, `k` and `bn`, set to the page's default table. So the dotted keys are `release.thresholds.<importance>.<unit>`, as the page names them, and `config/alerts.toml` can override any of them without a release |
| `examples/decisions-release.jsonl` (new) | What `python -m alertd replay --feed examples/feed-release.jsonl --state examples/state.json` prints, so the examples folder again has a decisions file for every feed, as the README says |
| `tests/test_release.py` (new, 57 tests) | Rule, settings, suppressions, worked examples, example decisions, check-feed |
| `README.md` | Added `release` to the Events table |
| `docs/settings.md` | New `[release]` section listing the 10 settings |
| `docs/desk/README.md` | Removed "(agreed November 2026; not in alertd yet)" |
| `docs/CHANGELOG.md` | Added an "Unreleased" entry for the new kind |

Not touched: `config/alerts.toml` (it needs only what differs from the defaults, and the desk asked for the page's
defaults), the shared modules `suppress.py`, `format.py`, `config.py`, `engine.py`, the other rules, and every
existing test.

### The rule, as written

- threshold = `settings["thresholds"][importance][unit]`
- surprise = actual − consensus, only when there is a consensus. |surprise| ≥ 3×threshold gives `critical`,
  ≥ 2× gives `warning`, ≥ 1× gives `info`, with the reason `surprise`.
- revision = revised − previous, only when `revised` is not null. |revision| ≥ threshold adds the reason
  `revision` and raises the level one step with the existing `levels.raise_level`, so critical stays critical. A
  revision alone is `info`.
- Neither reason means `None` (not worth an alert). The reasons list `surprise` first.
- `as_of = released_at` and `stale_after = release.stale_after_minutes`, so the shared `stale` suppression applies
  "more than 120 minutes from released_at to at".
- Key: `release:<country>:<release>`.
- Message: the subject is `<country> <release>`. The "what" part is `actual X`, plus ` vs consensus Y` only when the
  surprise is a reason, plus `, previous revised from P to R` only when the revision is a reason. The detail is
  `surprise ±S` and/or `revision ±R`. Figures use `fmt.amount` and `fmt.signed` with the event's unit (`pct` → 2
  decimals and `%`; `k` → 0 decimals, thousands commas and `k`; `bn` → 1 decimal and `bn`). All of these units
  were already in `format.UNITS`.

## How I checked it

- **The page's worked examples.** All six expected lines (r01, r03, r04, r06, r08, r10) match alertd's output
  character for character. `test_the_worked_examples` checks this using the defaults only, as the page specifies.
  The same six lines also come out with the desk's `config/alerts.toml`.
- **Every example release gets a decision.** All 12 do (`test_every_example_release_gets_a_decision`). The six
  events that are not worked examples:
  - r02: neither reason, so no alert.
  - r05: −0.52 against a threshold of 0.20, so `warning`.
  - r07: no consensus and no revision, so no alert.
  - r09: `info` surprise, but seen 185 min after publication, so held as `stale`.
  - r11: +0.12, so `info`.
  - r12: `info`, but 22:30 falls in quiet hours, so held as `quiet_hours`.
- **check-feed** reports `12 events: 12 can be decided, 0 cannot, 0 of kinds with no rule`.
- **explain, digest, what-if and settings** all work on releases. For example, `what-if` with
  `release.thresholds.medium.k = 100` flips r08, and `settings` lists the 10 new keys as `# default`.
- **Boundaries.** A surprise of exactly 1×, 2× or 3× the threshold reaches that level. Every importance × unit
  default threshold is tested just below and exactly at its value.
- **Suppressions.** Muting by key, by `release:VD:*` and by `release:*` all apply. A critical release passes a
  mute. Quiet hours, the cooldown by release key, the shared daily cap and staleness (exactly 120 min is not stale,
  120 min 1 s is) all work.
- **Settings.** A config file can override one threshold and the others keep their defaults. An unknown
  importance or unit under `release.thresholds` is refused with ConfigError.
- **Unreadable events.** These raise EventError, which the engine skips with a note: a country outside VD/QM/XR,
  an unknown importance or unit, a non-number actual/consensus/revised, a missing previous, a bad released_at, an
  empty release code.
- **Whole suite.** `python -m pytest`: 258 passed (the 201 existing tests unchanged, plus 57 new). The existing
  example decisions for the other four kinds are byte-for-byte unchanged (`test_examples.py` passes).

## What I assumed

- **Country.** I assumed `country` must be `VD`, `QM` or `XR` and treated any other value as an unreadable event
  (EventError, skipped with a note, and a "problem" in `check-feed`). The page lists that field's values as a
  closed set, "`VD`, `QM` or `XR`", in the same way as `importance` and `unit`. The `release` field, by contrast,
  says "such as `CPI`, ...", so I read it as open: any non-empty text.
- **Exact decimal differences.** I computed the surprise and the revision exactly, on the figures as written
  (`Decimal(repr(x))`). Thresholds are compared the same way. With floats, 0.3 − 0.2 = 0.09999999999999998 would
  miss a threshold of 0.10, 0.42 − 0.22 would miss "twice 0.20", and 0.1 × 3 = 0.30000000000000004 would make an
  exact 0.30 surprise miss `critical`. The page says "at least the threshold". `format.py` already writes numbers
  "on the value as written", so I kept to that principle. The helper sits in the rule, so the shared `format.py`
  is unchanged.
- **Fields are read up front.** I assumed every field the page lists is read and checked first, so a release with
  a broken `released_at` or `previous` is skipped even when it would not have made an alert. The page marks only
  `consensus` and `revised` as nullable, so `previous` is required even when `revised` is null. (The existing
  rules read their as-of time last, so a bad time there can slip through when there is no alert. I chose to be
  strict so that `check-feed` catches feed problems either way.)
- **Absent fields.** I assumed an absent `consensus` or `revised` field counts the same as null. The existing
  `Event.optional_number` behaves that way.
- **Fixed multiples.** I assumed the 2× and 3× multiples are fixed parts of the rule, not settings. The page makes
  only the thresholds (and `stale_after_minutes`) settings.
- **Messages.** I assumed `vs consensus` and `previous revised from ...` appear only when their reason holds, as
  the worked examples show: r03 has a consensus but no surprise reason, and leaves it out; r01 has a small
  revision and leaves it out.
- **Version.** I assumed releasing is a separate step. So I gave the CHANGELOG an "Unreleased" heading and did not
  bump the version: `__version__`, `pyproject.toml` and the README's "Version 1.6.2" stay at 1.6.2. Earlier new
  kinds came with a minor bump (1.3.0, 1.4.0), so 1.7.0 is the likely version when it ships.
- **Example decisions.** I generated `examples/decisions-release.jsonl` exactly as the README says, with the desk's
  `config/alerts.toml` (the default `--config`), as the other example decisions are. The page's worked examples use
  the default thresholds. Both give the same six lines, because the desk config does not set release thresholds.

## Ambiguous, for the desk

- **A threshold of 0.** The config rules allow it ("no number is negative", but zero is fine). With 0, every
  release with a consensus would be `critical`, and even an unchanged previous figure (revised == previous) would
  count as a `revision`. I did not guard against this in code. Per CONTRIBUTING: ask the desk.
- **A country the desk does not cover** (see the first assumption): skip it as unreadable, or decide it like the
  others? The page does not say what to do with one.
- **`previous` null with no revision** (for example, a new series): this is skipped as unreadable today, following
  the page's field table.

## Things that looked like traps

- **`docs/ARCHITECTURE.md` disagrees with the code.** It was last reviewed for 1.4.0. It lists `stale` as the last
  suppression, and says a mute names one key. The code (since 1.5.0 and 1.6.0, per the CHANGELOG) checks `stale`
  first and supports prefix mutes. The README says the code is right. That is why r09 is held as `stale`. I
  followed the code and left ARCHITECTURE.md alone (it is "reviewed less often").
- **Float subtraction** at threshold boundaries (above).
- **The desk's config differs from the defaults** (quiet_end 07:00, cooldown 45, daily cap 20). r01 arrives at
  07:00:05, just after the desk's quiet hours end, so it is sent under both configs.
- **r12** (22:30) falls in quiet hours and is only `info`, so it is held, not sent. **r09** is worth an alert but
  stale.
- **`tests/test_examples.py` hard-codes the four old kinds,** and existing tests must not be edited. So the release
  example check lives in the new `tests/test_release.py`.
- **`docs/operations.md`** has a stray line break in the "Changing settings" section. It is cosmetic and unrelated,
  so I left it alone.
