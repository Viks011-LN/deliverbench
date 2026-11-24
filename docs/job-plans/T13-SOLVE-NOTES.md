# Solve notes: regime table from Woodgrove Macro Data

## What I built

- `app/pipeline.py`: the job. Standard library only (urllib, json, csv, decimal), so it does not depend on what
  is installed. It reads `MACRO_API_URL` and `REGIMES_OUT` (README defaults; a relative output path is taken from
  the repo root, i.e. the folder `pipeline.py` sits in). It fetches both series afresh, works out each month's
  figure as it stands today, builds the table in memory, and only then writes `REGIMES_OUT`. Exit 0 only after
  the file is written. On any failure it logs the reason to stderr, writes nothing (an existing output is left
  untouched) and exits 1, so the desk is alerted.
- `app/output/regimes.csv`: today's table from a run of `python pipeline.py` from the repo root with both
  variables unset. 298 rows, 2001-04 to 2026-09; 72 deflation, 79 goldilocks, 75 reflation, 72 stagflation.
  Two separate runs (different fault patterns from the gateway) gave byte-identical files.
- `app/tests/test_pipeline.py`: pytest tests against a fake gateway (see "How I checked").
- `_scratch/` (workspace root, not part of the repo): my exploration and cross-check scripts plus a raw dump of
  today's observations (`raw.json`). Not needed by the job.

## Vendor behaviours met or prepared for

| Behaviour | Where the document states it | Met today? | What the pipeline does |
|---|---|---|---|
| Paging: up to 24 observations a page, `next_page` until `null` | 2.1 | yes, 15 pages per series | follows `next_page`; never computes the page count |
| Page size counts observations including vintages, not months | 2.1, 4, history 3.1 | yes, 341 / 345 observations for 309 months | a client that used `/meta` `months` (309) to work out pages (13) would lose the last two pages; I never do that |
| Every vintage kept; "as it stands today" = latest vintage | 4 | yes, 15 revised months per series, some with 4 vintages and with the latest not the largest | collects all pages first, then keeps each month's latest vintage (sorted by vintage date, vendor order as tie-break) |
| A month's vintages may continue on the next page | 4 | yes (IP 2006-07; CPI 2004-12, 2006-10, 2017-12, 2024-11 split across pages) | handled by choosing only after all pages are in |
| `"."` = no figure, not zero; every month first..last appears | 3 | yes, IP 2007-04 and 2024-08, CPI 2009-10 and 2020-06 | `"."` is "no figure": that month and the month three months later get no row; never read as 0 |
| Values are decimal strings with 2 dp | 3 | yes | parsed with `Decimal`, so changes are exact (no float noise near zero) |
| Retired series: 410 + `replaced_by`; follow on every 410; chains possible; never hard-code the successor | 5 | yes, `CPI_OLD` -> `CPI_YOY` | follows `replaced_by` at run time, through chains (with a loop guard), and on the `/meta` call too. If a 410 comes mid-series it restarts from page 1 of the successor so all kept observations come from one series. The code names only `IP_YOY` and `CPI_OLD` |
| 404 for an id never issued / no such page | 5, 8 | no | alert (exit 1) |
| 429 with `Retry-After` (whole seconds); wait counts from when the 429 arrives; no request until then; the 429'd request was not served | 6, 7 | yes, 4-5 per run | records the arrival time, sends nothing (to any endpoint) until arrival + Retry-After + 1 s margin, then resends the same request |
| Passing errors 500, 502, 503; same request answered when sent again | 6 | yes, 4-8 per run | resends the same request with a short backoff (0.5 s, 1, 2, 4, then 8 s), up to 12 in a row before alerting |
| Gateway may answer with the page before the one asked for; `page` names the page held | 6 | yes, about one per series per run | checks the answer's `page` against the page asked for; on a mismatch discards the answer and asks again |
| Faults can come at any request, whatever the pattern | 6 | yes, including on page 1 | every request goes through the same retry loop |
| One request at a time; early or overlapping requests are breaches that can suspend the line | 7 | n/a | strictly sequential; one client-wide "not before" clock; long (120 s) timeout so a slow answer is not abandoned and overlapped |
| Error bodies carry `error` | 8 | yes | quoted in the alert message |
| `/series/<id>/meta`: first, last, months (each month once), last_updated (latest vintage) | 2.2 | yes | used as a completeness check: received months must be exactly first..last with `months` months, and the newest vintage received must not be older than `last_updated`; otherwise alert. If `/meta` answered 404 the check is skipped with a log line |
| 400 for a malformed request | 8 | no | alert (it would be our bug) |
| `/health` not counted against the limit | 2.3 | n/a | not used (a health check would add nothing the data calls do not tell us) |
| Release calendar: figures change only on release days; any earlier month may be revised, benchmark in March | 9 | yes (March benchmark vintages visible) | nothing cached; every run fetches everything |

## Business rules applied and their source

- Series: growth `IP_YOY`, inflation `CPI_OLD` (ticket). Named only by those ids (README: "names each series only
  by the id its ticket gives"; vendor 5: "does not write a successor's id into its own code or settings").
- Figure for a month = its latest vintage (ticket "figures as they stand today"; vendor 4 defines that as the latest
  vintage).
- Change = this month's figure minus the figure three calendar months earlier (ticket), by month arithmetic, not
  "three rows back", to 4 decimal places, written with 4 decimals (e.g. `0.2300`, `-1.1500`, `0.0000`). Never
  `-0.0000`.
- Regime: reflation if both changes > 0; goldilocks if growth > 0 and inflation not; stagflation if inflation > 0
  and growth not; deflation otherwise (ticket). "Above zero" is strict, so a change of exactly 0 counts as "not".
- A row only for a month where both series have a figure for the month and for three months earlier (ticket).
  Oldest first, columns `month,growth_change,inflation_change,regime`, months `YYYY-MM` (ticket).
- Output: plain CSV, UTF-8 without BOM, `\n` line ends, header row, nothing else written (README).
- Exit 0 only when written; fetch afresh; keep nothing between runs; standard library only (README).

## How I checked the table

1. Independent rebuild: `_scratch/verify.py` rebuilds the table from the raw observations with pandas (a different
   code path: sort by vintage and take the last, numeric values with `"."` as NaN, a 3-month PeriodIndex shift,
   float rounding to 4 dp) and compares it with `output/regimes.csv`: identical, 298 rows.
2. Row count by hand: 309 months, minus the first 3 (no lookback) = 306, minus 8 months knocked out by the four
   `"."` months (each removes itself and the month three later: 2007-04/07, 2024-08/11, 2009-10/2010-01,
   2020-06/09) = 298. Those 8 months are absent from the file; their neighbours are present.
3. Hand check of a revised row: 2025-02 growth = IP 2025-02 latest (1.68, vintage 2025-04-16) minus IP 2024-11
   latest (1.45, vintage 2025-03-16) = 0.2300, as in the file. (With first vintages it would have been 0.49.)
4. Meta cross-check inside every run: both series 2001-01..2026-09, 309 months, newest vintage = `last_updated`.
5. Two full runs against the gateway with different fault sequences: byte-identical outputs.
6. Tests (`python -m pytest -q tests`, 12 pass): a fake gateway that serves small pages so months' vintages split
   across pages, injects 429 / 500 / 502 / 503 / "page before" faults, retires `CPI_OLD` through a two-step chain,
   and in another test retires it in the middle of paging. The expected table there is worked out by hand and
   includes a zero change on each side (strict "above zero"), a `"."` month, a series with an extra earlier month
   and one with an extra later month, and revisions that change the answer. The fake records any request sent
   before a Retry-After wait is over or while another request is unanswered; the tests require none. I checked the
   detector is not vacuous: with the margin forced negative it flags the early requests. Failure tests: unknown
   series (404), a month missing from the data, and a `replaced_by` loop all exit 1 and write nothing.
7. Ran from another working directory with a relative `REGIMES_OUT`: it lands under the repo root, same content.

## Assumptions

- I assumed "the figures as they stand today" means each month's latest vintage, as section 4 defines, and not
  "latest vintage dated on or before the machine's clock". I do not filter vintages by the system date.
- I assumed the regime is decided on the change as published (4 dp). With 2 dp inputs the change is exact, so it
  makes no difference; it would only matter for inputs with 5+ decimals.
- I assumed a month whose latest vintage is `"."` has no figure today, even if an earlier vintage had one (none
  does today).
- I assumed a set-but-empty `MACRO_API_URL` / `REGIMES_OUT` means "use the default", like an unset one.
- I assumed the job should alert rather than publish when the data looks incomplete (a gap in the months, or a
  mismatch with `/meta`), since a silently short table is worse for the desk than a late one.
- I assumed it is fine to create the output's parent folder if it does not exist.
- I assumed one extra second on top of `Retry-After` is an acceptable cost for never being early.
- I assumed 120 s is long enough to wait for one answer, and that a lost connection (no answer at all) can be
  retried like a passing error after a short pause.
- I assumed if two observations had the same month and the same vintage, the later one in the vendor's order wins
  (logged). This does not occur today.
- I assumed an empty table (header only) is still a valid output (exit 0). Today's table has 298 rows.
- I assumed adding a `tests/` folder to the repo is welcome; the scheduler only runs `pipeline.py`.

## Ambiguities

- "To 4 decimal places": I write the change with exactly 4 decimals (`0.2300`), not trimmed (`0.23`).
- Zero changes: "above zero" read as strictly positive, so 0.0000 is "not above zero" (none occur today, but the
  fresh data might have some).
- Whether to resume a successor at the same page after a mid-series 410 (the document says it carries the history
  "in the same pages") or restart: I restart at page 1, which is correct either way and costs a few requests.
- The `/meta` cross-check makes the job stricter than the ticket asks. If the vendor ever published a release in
  the middle of a run, the check could alert once; a rerun would fix it.

## Things that looked like traps

- `CPI_OLD` is retired (410 -> `CPI_YOY`). Hard-coding `CPI_YOY` would break the README rule and would fail when
  `CPI_YOY` is itself retired; ignoring the 410 gives no inflation series.
- Revisions: taking the first vintage, or the first observation per month, or the last observation of a page
  instead of after all pages, gives wrong figures (15 revised months per series; several split across pages).
- `"."` months: reading them as 0, or dropping them and then shifting by three rows, misaligns the three-month
  lookback for months near the gaps.
- Paging: `/meta` says 309 months but there are 341/345 observations; page counts from `months` would truncate.
- "Page before" answers: a client that trusts the answer without checking `page`, or increments its own page
  counter, would duplicate one page and skip another.
- 429: resending at once, or counting the wait from when the request was sent, or running requests in parallel,
  would breach the line's terms and risk suspension.
- Faults on the very first request (it happened: a 500 and a 429 on page 1), so retry logic must cover every call,
  including `/meta`.
- Floats: values are decimal strings; I used `Decimal` to keep changes exact and avoid `-0.0000`.
