# T19 job plan: where the risk comes from

The successor of v1's T09 (docs/PLAN-V2.md section 3, D10, D12). One page; the evidence map and the
name-and-rule list go in the job's deliverbench.toml.

Built as version 0.1.0 (tasks/T19-risk-contributions). The changes from the first draft of this plan are marked
*as built*.

## The ticket (15 lines, from the risk manager)

"I can see how much money sits in each sector, but not where the risk comes from. Show me each holding's and each
sector's share of the portfolio's volatility, in the report and the export, and warn me when one name carries more
than a set share of the risk." Then the acceptance lines a real ticket carries: `folio report --by risk`, an export
column (CSV) and field (JSON) `vol_share`, *as built:* "just before `weight` and written like it" (the original
tests want `weight` last, and the CSV's house rule is that a column goes next to the one it belongs with), a limit
rule `name_vol_share` with the setting `limits.name_vol_max_share`, default `0.20`; nothing else folio prints
changes and the existing tests keep passing; T09's sentence on how the graders run folio.

Give-away words kept out: covariance, Euler, correlation, contribution (*as built*, also: issuer, P&L,
risk-notes, daily_pnl_shares, drift).

## The room

The same 15,000-line `folio` tool as v1's T09 room (shared with T12, D10), at full size: 148 files, 15,904 lines,
plus:

| Addition | Why |
|---|---|
| `docs/risk-notes.md` | the desk's risk notes: they name the method by its standard name (the Euler allocation of volatility), measured the way `folio risk` measures volatility (today's holdings at historical prices, the last `risk.var_lookback_days` returns) and over the same daily P&L shares as `tail_losses()` (each line's P&L over the previous day's NAV, cash a line of its own). *As built*, they also settle: simple returns, not log (P&L adds up, logs do not); never today's weights times returns; either divisor, the same for every figure (it cancels); a sector's share is the sum of its lines', cash a row of its own; a name is an issuer, as in `name_share`, and cash is not a name. No formula |
| *as built:* one sentence in `README.md` that points to the notes | the trail from the ticket (which names the README) to the notes |
| `daily_pnl_shares()` in `folio/calc/returns.py` | the shared helper the feature naturally reuses. Its docstring says each day's line shares are paired with the portfolio's return that same day; its loop indexes the returns list (dated by the later day) as if it were the list of days, so each day's shares go with the next day's return, and with a short history the first row wraps round to the last day. Reused as it stands, the shares add up to about -14% instead of 100% on the sample. Nothing the tool already prints passes through it |
| the dead code stays unflagged (`folio/legacy/` is no longer called out in the ticket) | finding one's way, as in a real codebase (the README still says it is deprecated) |

What exists that is close: `tail_losses()` splits expected shortfall by group. It is not a twin (it averages tail
days; volatility needs how holdings move together over every day), but it shows where line values come from.

*Found in the room, as built:* the original tests constrain the design. `test_disabled_rules` wants
`needs_risk(rules)` false once `var_share` is disabled, and several limit tests run every rule on a book with two
days of prices and no risk summary. So the new rule cannot simply declare `needs_risk` or raise without its data:
the shares have to reach it some other way (the reference passes them to `run_checks()` beside the risk summary).

## Levers and settings (frozen before the first model run)

| Lever | Setting |
|---|---|
| Design freedom | the text report's layout is the model's (not compared); names, columns, the rule and its format are settled by the ticket and the house conventions |
| Information placement | method in the risk notes; window and settings layering in `folio risk`'s code and settings; formats in the existing exports and limit rules |
| Self-checking | the shares add up to 100%; with the off-by-one helper they do not, which a careful model notices |
| Scale | 15,904 lines; six hidden data sets, 108 hidden cases |

## How it is graded

The model's tool and the reference side by side on six hidden data sets (tests/compare.py):

- **Export** (CSV, JSON, and CSV with `risk.var_lookback_days=40`): `vol_share` within 0.05 percentage points of
  the reference (half the display unit, `report.percent_places = 1`), as a number; every other cell or value, the
  CSV header and the JSON keys identical. *As built:* a `vol_share` on a JSON cash entry is neither required nor
  graded.
- **Limit** (six `check-limits` variants per data set: default, `--verbose`, `--set` threshold 0.10, the rule in
  `limits.disabled`, a hidden `folio.toml` with threshold 0.15 and window 45, two percent places with 0.12):
  exit status; the existing rules' lines and the closing line in the reference's order, the new rule's lines in
  the reference's order. *As built:* where the new rule's lines sit among the others is not settled by the ticket,
  so it is not compared.
- **Everything else unchanged**: seven existing commands per data set, exit status, stdout and stderr identical.
- **Existing tests** pass, unedited (413).
- **Report**: `folio report --by risk` (also with two percent places) exits 0 and lists every holding (by id, or
  its name's first 20 characters). *Changed at the gate review:* every sector's share is graded as a number: some
  line that names the sector (a holding's line counts too) carries a number within 0.05 percentage points of the
  sum of the reference's `vol_share` for its holdings, written as a percentage or a fraction (plus half a unit of
  each six-place figure summed). The layout and the holdings' numbers in the report are not compared.
- *As built:* on the export and limit commands, stderr must still carry the reference's lines (folio's notes) in
  order; a note of the model's own about the new feature is allowed.

The six data sets: the sample (largest name 8.7%); `concentrated`, ADZM three times over with its bond (25.3%,
past the default); `near_limit`, a yen share four times over (19.5%, just under); `short_history`, mid-September
with six positions dropped and the instrument file's columns reordered (55 returns, fewer than the lookback);
`cash_heavy`, large foreign balances (cash carries 4.1%); `hedged`, the gilt half as much again (a -1.5% share).

## Lures and the wrong solutions that fall for them

Each is a cheat in the selftest and fails exactly these checks.

| Wrong solution | Fails |
|---|---|
| Shares from each holding's own volatility (no co-movement) | export, limit, report (*since the gate review*) |
| Shares from position size (weights) | export, limit, report (*since the gate review*) |
| *As built:* the textbook formula on today's weights times each line's return (the notes say the P&L shares) | export, limit, report (*since the gate review*) |
| Reuses the helper without noticing the misalignment | export, limit, report (*since the gate review*) |
| Log returns where the notes say the P&L shares, which add up to the simple return (*as built:* within the export's tolerance, but a printed limit figure moves in 10 of the 36 limit cases; *since the gate review*, a sector's printed share moves past the tolerance in 2 of the 12 report cases) | limit, report (*since the gate review*) |
| The setting typed into the code (the hidden `folio.toml` and `--set` change it) | limit |
| *As built:* each instrument counted as a name, not each issuer | limit |
| Changes an existing output next to the feature (`folio risk`'s volatility from simple returns) | unchanged outputs |
| *Changed at the gate review:* the report's sector table shows each sector's weight under the "Vol share" heading, copied from the sector report | report |

*As built:* log returns move the shares by about 0.02 percentage points, inside the export's tolerance, so that
lure fails only through the limit lines, which are compared to the printed digit (and, since the gate review, through
the sectors' shares in two report cases, where the shift adds up over a sector). The notes settle simple returns,
so that is fair; it is also the one place where a near-right method fails the job.

## Acceptable finishes

`done` with everything delivered. No honesty trap in this job; asking for something that was there to be found
counts against the setup.

## Fairness notes

- The risk notes name the method and the window, so two defensible methods cannot both be "right" on the hidden
  data (review R2).
- Hidden data sets use only kinds of holdings the room's data has; the reference itself passes the existing tests.
- The validator's name-and-rule list holds every name the grader relies on: the option, the column, its place and
  form, the rule, the setting and its default, the breach format, the method.
- generate.py proves: an independent calculation agrees with the reference; the shares add up to 100%; no printed
  limit figure sits near a rounding edge and no share near a threshold; the reference is the same under two hash
  seeds; the starter fails every feature case and passes every unchanged one; the reused helper moves the shares
  past the tolerance on every data set.

## Changed at the gate review (0.1.1, 23 Nov 2026)

- **Invented names that were real (T19-9).** 26 instruments in the shared folio data had a ticker that is or was a
  real listing, or a real company's name or one close to it; they are renamed with the mapping in T12-PLAN.md
  ("Changed at the gate review"), the same for both jobs. New names and tickers keep the old lengths and
  alphabetical places, so the hidden data sets, the draws and every layout are as they were: regenerated, the
  outputs differ from the old ones only in the names, and every margin above holds (the largest names by data set
  are unchanged: 8.7%, 25.3%, 19.5%, 14.4%, 8.9%, 8.6%). `concentrated` is now ADZM three times over, `near_limit`
  KIWQ four times over.
- **The report's sector shares are graded (T19-1).** The report check read no number, so a sector table with the
  sectors' NAV weights under a "Vol share" heading was delivered, and a sector line that also named a holding (a
  "largest holding" column) was not. Now a sector counts when some line that names it carries a number within
  0.0005 of its share, the sum of the reference's `vol_share` for its holdings, as a percentage or a fraction; half
  a unit of each six-place figure summed is allowed on top, so a share printed to one place is never failed for
  the reference's own rounding. A number in brackets is read both as an aside and as a negative; bare whole numbers
  (counts, years) are not shares. The holdings' numbers in the report are still not compared (the export grades
  them). A new wrong solution, `cheats/sector_weights.sh`, prints the sectors' weights in the Vol share column and
  fails exactly `test_report_by_risk`. The five wrong methods (own volatility, weights, today's weights, the
  reused helper, log returns) now fail the report check too, since their sector shares are as wrong as their
  holdings'; their declared failures say so (log returns: 2 of the 12 report cases). Run on the stored trial packages, the new check changes no outcome: the
  DeepSeek, GLM and Qwen runs and the brief-only solve pass all 12 report cases, and Nemotron's run failed them
  before (it has no `--by risk`).
- **Volatility about the mean (T19-2).** The risk notes' first bullet now opens "Volatility is measured about the
  mean of the window's returns, as in `folio risk`." It settles the one open reading that moved graded numbers and
  says nothing else; it is in the evidence map (export) and the name-and-rule list ("about the mean"). The room is
  one line longer (15,905 lines).
