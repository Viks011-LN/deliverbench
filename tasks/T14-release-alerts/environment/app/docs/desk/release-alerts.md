# Release alerts

The rules the economics team agreed with the desk in November 2026 for alerts on economic releases. This page is
the rule; the README says how alertd runs.

## What the desk wants

An alert when an economic release comes out far from what the market expected, or revises the previous figure by
enough to matter. The desk covers three economies: Valdoria (`VD`), Quelmark (`QM`) and Xerania (`XR`).

## The events

Releases come in on the feed as kind `release`, one event per figure published:

| Field | Meaning |
|---|---|
| `id`, `kind`, `at` | as for every event; `at` is when alertd sees the release |
| `country` | `VD`, `QM` or `XR` |
| `release` | the release's code, such as `CPI`, `PAYROLLS` or `TRADE_BALANCE` |
| `released_at` | when the figure was published (UTC) |
| `importance` | `high`, `medium` or `low`, as the economists rate the release |
| `unit` | `pct` (percent), `k` (thousands) or `bn` (billions) |
| `actual` | the figure published |
| `consensus` | the economists' consensus for the figure; null when none was collected |
| `previous` | the previous period's figure, as first published |
| `revised` | the previous period's figure as published with this release; null when it was not revised |

## The rules

**Thresholds.** A release is judged against the threshold for its importance and unit. The thresholds are settings
in alertd's config, under `release.thresholds.<importance>.<unit>`, with these defaults:

| importance | `pct` | `k` | `bn` |
|---|---|---|---|
| `high` | 0.10 | 15 | 1.0 |
| `medium` | 0.20 | 30 | 2.0 |
| `low` | 0.30 | 50 | 3.0 |

**Surprise.** The surprise is the actual figure less the consensus. When the size of the surprise is at least the
threshold, the release has the reason `surprise`, at level `info`; at least twice the threshold makes it `warning`,
and at least three times the threshold `critical`.

**Revision.** The revision is the revised figure less the previous figure. When the size of the revision is at
least the threshold, the release also has the reason `revision`, and the revision raises the level one step:
`info` becomes `warning`, `warning` becomes `critical`, and `critical` stays `critical`. A revision alone, with no
surprise, is `info`. A smaller revision is not a reason and changes nothing.

**No consensus.** When there is no consensus, there is no surprise; a revision can still make an alert.

**Neither.** A release with neither reason is not worth an alert.

**Reasons** are listed with `surprise` first.

**Stale.** A release is stale when alertd sees it more than `release.stale_after_minutes` minutes after it was
published, counted from `released_at` to `at`. The default is 120 minutes.

**Key.** The key for mutes and the cooldown is `release:<country>:<release>`, for example `release:VD:CPI`.

Mutes, quiet hours, the cooldown and the daily cap apply to release alerts as they do to every alert.

## Messages

Messages are in the house style, like every other alert's. The examples below show the wording for a surprise, a
revision and both.

## Worked examples

Six releases from `examples/feed-release.jsonl`. Each decision is the line alertd prints for the release when it
replays that feed from `examples/state.json` with the default thresholds: none of the six is muted, stale or in quiet
hours, and none follows an alert with the same key.

### 1. A surprise

    {"id": "r01", "kind": "release", "at": "2026-11-03T07:00:05Z", "country": "VD", "release": "CPI", "released_at": "2026-11-03T07:00:00Z", "importance": "high", "unit": "pct", "actual": 0.46, "consensus": 0.22, "previous": 0.31, "revised": 0.33}

The threshold is 0.10. The surprise is +0.24, more than twice the threshold but less than three times: `warning`.
The revision, +0.02, is below the threshold, so it is not a reason.

    {"id": "r01", "kind": "release", "key": "release:VD:CPI", "sent": true, "level": "warning", "reasons": ["surprise"], "message": "WARNING VD CPI: actual 0.46% vs consensus 0.22% (surprise +0.24%)"}

### 2. A revision alone

    {"id": "r03", "kind": "release", "at": "2026-11-03T09:00:06Z", "country": "XR", "release": "TRADE_BALANCE", "released_at": "2026-11-03T09:00:00Z", "importance": "low", "unit": "bn", "actual": -14.6, "consensus": -15.9, "previous": -12.4, "revised": -15.8}

The threshold is 3.0. The surprise, +1.3, is below it. The revision is -3.4, at least the threshold: a revision
alone, so `info`.

    {"id": "r03", "kind": "release", "key": "release:XR:TRADE_BALANCE", "sent": true, "level": "info", "reasons": ["revision"], "message": "INFO XR TRADE_BALANCE: actual -14.6bn, previous revised from -12.4bn to -15.8bn (revision -3.4bn)"}

### 3. A surprise and a revision

    {"id": "r04", "kind": "release", "at": "2026-11-03T09:30:03Z", "country": "VD", "release": "GDP", "released_at": "2026-11-03T09:30:00Z", "importance": "high", "unit": "pct", "actual": 0.31, "consensus": 0.45, "previous": 0.2, "revised": 0.34}

The threshold is 0.10. The surprise is -0.14, at least the threshold but less than twice it: `info`. The revision,
+0.14, is at least the threshold, so it is a reason too and raises the level one step: `warning`.

    {"id": "r04", "kind": "release", "key": "release:VD:GDP", "sent": true, "level": "warning", "reasons": ["surprise", "revision"], "message": "WARNING VD GDP: actual 0.31% vs consensus 0.45%, previous revised from 0.20% to 0.34% (surprise -0.14%, revision +0.14%)"}

### 4. No consensus

    {"id": "r06", "kind": "release", "at": "2026-11-03T12:00:05Z", "country": "QM", "release": "PAYROLLS", "released_at": "2026-11-03T12:00:00Z", "importance": "high", "unit": "k", "actual": 212, "consensus": null, "previous": 175, "revised": 198}

No consensus was collected, so there is no surprise. The threshold is 15 and the revision is +23: a revision alone,
`info`.

    {"id": "r06", "kind": "release", "key": "release:QM:PAYROLLS", "sent": true, "level": "info", "reasons": ["revision"], "message": "INFO QM PAYROLLS: actual 212k, previous revised from 175k to 198k (revision +23k)"}

### 5. A large surprise

    {"id": "r08", "kind": "release", "at": "2026-11-03T13:30:04Z", "country": "QM", "release": "HOUSING_STARTS", "released_at": "2026-11-03T13:30:00Z", "importance": "medium", "unit": "k", "actual": 1212, "consensus": 1305, "previous": 1288, "revised": null}

The threshold is 30. The surprise is -93, more than three times the threshold: `critical`. The previous figure was
not revised.

    {"id": "r08", "kind": "release", "key": "release:QM:HOUSING_STARTS", "sent": true, "level": "critical", "reasons": ["surprise"], "message": "CRITICAL QM HOUSING_STARTS: actual 1,212k vs consensus 1,305k (surprise -93k)"}

### 6. Critical stays critical

    {"id": "r10", "kind": "release", "at": "2026-11-03T15:00:02Z", "country": "XR", "release": "BUDGET_BALANCE", "released_at": "2026-11-03T15:00:00Z", "importance": "medium", "unit": "bn", "actual": 8.4, "consensus": 1.7, "previous": 3.5, "revised": 1.2}

The threshold is 2.0. The surprise is +6.7, more than three times the threshold: `critical`. The revision, -2.3, is
a reason too, and `critical` stays `critical`.

    {"id": "r10", "kind": "release", "key": "release:XR:BUDGET_BALANCE", "sent": true, "level": "critical", "reasons": ["surprise", "revision"], "message": "CRITICAL XR BUDGET_BALANCE: actual 8.4bn vs consensus 1.7bn, previous revised from 3.5bn to 1.2bn (surprise +6.7bn, revision -2.3bn)"}
