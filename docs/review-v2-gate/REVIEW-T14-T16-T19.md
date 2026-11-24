# V4 gate review: T14, T16, T19 (brownfield code jobs)

Independent reviewer; built none of these jobs. Read-only: no generate.py, selftest, run or Docker. Evidence: the job
folders, plans, solve notes, `tests/data`, the trial folders (junit, transcript end records, and each trial's final
`/app` from `artifacts/app`, diffed against the room), and two throwaway pytest probes run in `/tmp` (outside the
repo) to confirm the integrity finding X1. T16 and T19 were reviewed in parallel by two forks of this reviewer
with the same brief; their A and B findings were spot-checked against the files before inclusion.

## Summary

**Counts:** 2 A (one cross-job, X1, which appears in the jobs as T16-2 and T19-3; one in T16), 6 B, 11 C.

| Job | A | B | C | Verdict |
|---|---|---|---|---|
| all three | X1 | | | the original-tests checks trust a junit file the agent's code can forge |
| T14 | (X1) | 0 | 3 | sound otherwise: no false negative or false positive found |
| T16 | T16-1, (X1) | 2 | 4 | fair; one false positive |
| T19 | (X1) | 4 | 4 | sound otherwise: two B weaknesses in what is graded and settled, one process gap, real names in the shared data |

**The A findings:**
- **X1:** in T14, T16 and T19 the original-tests check grades from a `junit.xml` written by the pytest process that
  runs the agent's code. A root `conftest.py` (T14) or the package's `__init__.py` (all three) can turn failures
  into passes; both were shown with the checkers' own flags.
- **T16-1:** a hybrid that keeps momentum and reversion special-cased in the engine's five places and adds a
  generic branch for new types passes every check (the generator's own `PATCHED_ORIGINAL` proves it), although the
  ticket says the two become strategies like any other.

**Fairness against other correct designs** (the caller's main question): no false negative found in any of the
three. In T14 every boundary is a whole grid step away (so floats and decimals must agree on all 94 release events), the
hidden config sets every release key, decisions are matched by id, and the six worked examples settle every
message the check compares. In T19 the nearest share is 4.8e-3 from a threshold and 2.8e-6 from a rounding edge,
`vol_share` is compared as a number within 0.0005, and no unsettled case is graded; the one open reading that
would change graded numbers (returns about their mean, T19-2) is settled only by convention. In T16 the four
dropped-in strategies use nothing the note does not promise.

**Trials:** T14 4/4 delivered (2.5 to 11.2 min); T16 3/3 finished runs delivered, LongCat still running; T19 3/4
delivered (Nemotron ran out of context, fairly), with no run yet on hy4 or longcat. No failure was the job's fault.
All three jobs are easier than forecast; the causes are structural, not fixable give-aways (T14 C2, T16-6, T19-7).

## Cross-job finding

### X1 (A). The original-tests checks trust a junit file written by a process that runs the agent's code

- **Where.** T14 `tests/test_outputs.py:159-177` (`test_original_tests_pass`); T16 `tests/test_outputs.py:146-181`;
  T19 `tests/test_outputs.py:120-149`.
- **What.** Each check builds a tree from the agent's work, restores the original tests, runs pytest as nobody,
  and then trusts the `junit.xml` that this pytest process writes. Two routes let the agent's work set that file to
  "passed" for a failing original test. Route 1 is open in T14 only, which copies the whole `/app`; T16 and T19
  copy only the package folder (`bt/`, `folio/`), so only route 2 applies there.
  1. **A conftest.py the restore does not cover.** pytest's default `confcutdir` is the inifile's folder (the copy's
     root), so `/app/conftest.py` is loaded. Confirmed with the checker's own command line on pytest 9.2.0 (the
     base image's pin), in a scratch folder: a root `conftest.py` with a `pytest_runtest_makereport` hookwrapper that
     sets `rep.outcome = "passed"` turns `assert 1 == 2` into `1 passed`, and junit records the test as passing.
     With `--confcutdir=<root>/tests` the same test fails.
  2. **The package itself.** The tests import the package (`alertd`, `bt`, `folio`), so code in its `__init__.py`
     runs inside pytest and can patch its reporting or rewrite `junit.xml` at exit (the work folder is nobody's).
     Shown for T16 in a scratch folder with the checker's flags: a 10-line `bt/__init__.py` that registers an exit
     hook when pytest is loaded and rewrites the `--junitxml` file makes a failing test come out with no failure
     entry (demo in
     `<scratch>\gate-review\t16_forge_demo\`).
     This route cannot be closed inside one process.
- **Scenarios.** T14: a model breaks `explain` or `digest` for an existing kind (only the original tests run those
  tools), sees `tests/test_explain.py` fail, and adds a root `conftest.py` that marks failures as passed. T16: a
  model deletes `bt/legacy/` or breaks a name the tests import (`compute_scores`, `first_trading_day`,
  `signal_echo`, `strategy_line`) and forges the report; checks 1 and 2 do not catch either. T19: a model breaks
  `test_disabled_rules` and forges it. Each run is delivered.
- **Why A.** The brief's A includes "an integrity hole", and this is one in house rule 2 ("can reach neither
  /tests nor the result"): the inner junit is a result the agent's code writes. The `tamper.sh` probes forge only
  the outer grade (`/logs/verifier`, `/run/dbench-result.*`), so selftest cannot see it. Unlike every other check,
  the agent knows the expected outcome here ("passed"). Its practical risk is low: it takes deliberate forging,
  visible in the diff and transcript, and no trial did anything like it. The accepted-risk record
  (`docs/REVIEW-2026-11-18.md:62`) names only v1's T02; it should name every v2 job that reruns original tests
  (T12 likely too; not reviewed here).
- **Smallest fix.**
  - (a) T14: delete every `conftest.py` in the copy that is not in the restored bundle, and pass
    `--confcutdir=<root>/tests` (verified above). T16 and T19 need nothing for route 1.
  - (b) Against route 2, a source scan: fail the check when the agent's package imports `pytest`, `_pytest` or
    `atexit`, or mentions `hookimpl`, `junit`, `PYTEST_CURRENT_TEST` or `os._exit`. Match imports, not the bare
    word `pytest`, which an honest docstring may contain. Neither the rooms' packages nor the references use any
    of these, and none of the eleven trial packages (T14, T16, T19) contains even the word `pytest` (checked).
    Also requiring the inner pytest's exit status to be 0 is cheap, though forgeable the same way.
  - (c) A third integrity probe in `scripts/make_integrity_cheats.py` that breaks one original test and forges
    its junit entry (root `conftest.py` for T14, package `__init__.py` for all three); it must fail exactly
    `test_original_tests_pass`.
  - (d) Record in AGENTS.md rule 2 that a disguised forgery inside the package still slips past (a known limit).

## T14: release alerts (`tasks/T14-release-alerts`)

**Verdict: sound** on fairness, soundness of the checks and the replay checks' integrity. Its only A is the
cross-job X1 (both routes are open in T14); three notes (C).

### What I checked and found sound

- **Every graded field is settled.** `sent`, `level` and `reasons` come from the desk page's rules
  (`docs/desk/release-alerts.md:30-59`), the suppression order, tags and critical's exceptions in
  `alertd/suppress.py` (README: "the code is right"), and the README's line for an event not worth an alert
  (`level` null, `reasons` `[]`). Messages are compared for every sent alert, which is fair here: the six worked
  examples cover surprise alone, revision alone and both, both signs, each unit, each level, a thousands comma, a
  consensus present but not a reason (r03) and a revised figure present but not a reason (r01).
- **Float against decimal.** Every figure is on its unit's grid (0.01 / 1 / 0.1), and so are all 18 thresholds of
  both configs. `generate.py:153-197` moves every surprise off 1x, 2x and 3x of both configs' thresholds and every
  revision off 1x, so the nearest decision boundary is a whole grid step away, not 1e-9, and float and
  exact-decimal implementations must agree on all 94 release events (three trial models used `Decimal`, GLM used
  floats; all pass). Release ages stay at least a minute from 75 and 120 minutes; quiet-hour edges, mute ends
  and cooldown ends at least a minute from every event worth an alert (`generate.py:710-727`).
- **Settings.** The hidden config (`tests/data/cases.json`, `hidden_config`) sets all nine thresholds and the stale
  window, so how deeply a model merges nested tables cannot matter; `k = 20` (int) and `pct = 0.15` (float) are both
  "number" to `config.py`; any TOML spelling of `release.thresholds.<importance>.<unit>` flattens to the same keys.
  The check passes the config by path, so whatever the model put in its own `config/alerts.toml` is irrelevant.
  All four trial models declared the release settings only in `defaults.toml` and left `config/alerts.toml` alone;
  that is correct under the README ("needs to set only what differs from the defaults") and passes.
- **Open sets.** Hidden release codes include `CURRENT_ACCOUNT`, which no example uses; the page says "such as",
  so a closed list is the model's error. Countries are a closed set and the hidden data uses only the three listed.
  `previous` is never null; `consensus` and `revised` are null, never absent, as in the room.
- **Reasonable extras.** Decisions are matched by id, so an extra field on a release line is tolerated. An extra
  stdout line fails the feed, which the README settles ("one JSON object per line, one for each event it
  decides"). The existing-kinds check compares stdout only, so stderr notes are free.
- **The original tests do not pin the set of kinds.** `test_registry.py` checks that the four exist,
  `test_examples.py` loops over the four, `test_engine.py` and `test_feedcheck.py` use `fx_fixing` as the unknown
  kind, `test_cli.py` checks two `settings` lines and `: ok (`. Adding `release` breaks none of them.
- **The wrong solutions.** The 13 cover every lure in the plan, and the hidden config changes 42 of 71 decisions,
  stale window included (`generate.py:1123`), so thresholds or a window typed into the code cannot pass.
- **Replay integrity.** Each replay runs as nobody on a fresh copy, with only that run's feed, state and config in
  reach; expected values never enter its process; `/tests` is root-only. Nothing a replay can learn helps a later
  one.

### Findings

- **C1. "At least" and "more than" are never graded.** The margins that make float arithmetic safe also remove every
  boundary, so `abs(s) > t` for "at least" and `age >= window` for "more than" both pass. For the `k` unit (integer
  figures, exact in floats) a surprise of exactly 1x, 2x or 3x would be a fair case. Adding it now would make the
  job harder after its trial runs (D8), so note it for a later version.
- **C2. T14 is a ceiling in the trials, mostly by design.** All four setups delivered first time, in 2.5 to 11.2
  minutes and 34 to 49 turns (the plan aimed at 50 to 150 steps; forecast 3/3/2/0 of 5). Each added
  `rules/release.py`, a line in `registry.py` and the `[release]` tables, and changed no shared code. Why it is
  easy: (1) the engine applies the shared suppressions to any `Finding`, so a rule written to the documented
  interface gets mutes, quiet hours, the cooldown, the cap and staleness right for free; the two suppression lures
  (ARCHITECTURE.md's order, suppressing inside the rule) only bite a model that rewrites suppressions, which
  `alertd/rules/__init__.py` forbids in the file every model reads before writing a rule. (2) v1's two failure modes
  are pre-solved by the room: `news.py:34` already has `level = "info" if level is None else raise_level(level)`
  (the revision step, critical capped by `levels.raise_level`), and `feed.py:61` has `optional_number`, which no
  existing rule uses. These are realistic in a brownfield codebase and none is a give-away of a graded fact, but
  they are why the "interacting rules" lever bought little. Removing them now would be tuning after trial runs
  (D8): publish as found.
- **C3. `deliverbench.toml:11` still has the placeholder `time_limit_min = 120`.** Under SCORING-2-DRAFT section 6
  it becomes 60 (5 x 11.2 minutes, rounded up to 5) before the freeze.

### Trial runs

| Setup | Result | Minutes / turns | Note |
|---|---|---|---|
| deepseek-v4.1-flash-high | delivered, `done` | 6.3 / 49 | exact decimals; own tests and example decisions added |
| glm-5.3-flash-fp4-high | delivered, `done` | 2.5 / 41 | floats (safe by the margins); own tests; version bumped to 1.7.0 (harmless) |
| hy4-flash-free-hosted | delivered, `done` | 5.1 / 34 | decimals; no tests of its own (not graded) |
| longcat-2.5-free-hosted | delivered, `done` | 11.2 / 35 | decimals; no tests of its own; version bump |

No failure to triage. Every pass is genuine: the final `/app` of each run holds a complete rule in the house
pattern, and no run edited `suppress.py`, `format.py`, an existing rule, a test or `config/alerts.toml`.

## T16: make strategies pluggable (`tasks/T16-pluggable-strategies`, 0.1.0)

**Verdict: fair (no false negative found), but one A false positive (T16-1) and the cross-job X1 (T16-2).** Two B,
four C. Reviewed as it stood at 02:00 on 23 Nov: no brief-only solve yet, LongCat's trial still running.

### What I checked and found sound

- **The note settles everything the hidden strategies use.** `docs/design/strategy-slot.md` fixes the place
  (`bt/strategies/<type>.py`, the type being the file name), the three names, what `params` holds (every
  `PARAMETERS` name in order, defaults filled in, no `type`) and what `history` holds. The four dropped-in
  strategies use only `.items()`, indexing, slicing, `None in`, `max`/`min` and `len`, so they work whether
  `history` holds lists or tuples and whether `params` carries `type` or not; each scores a symbol on its own and
  returns `None` without today's close. Ranking breaks ties by symbol (`bt/portfolio/ranking.py`), so the order of
  the returned dict never matters.
- **Validation.** The dropped-in configs give each parameter its default's type, so an extra type check a model adds
  never fires; the invalid types the hidden configs use (`carry`, no type, `Momentum`) and their messages are in
  the note word for word.
- **Expected outputs** come from the original program and the reference in their own work folders, before the
  agent's code runs; the agent's code never sees them. Running it under hash seeds 1 and 2 only catches output that
  changes from run to run, a real defect. The checks create `bt/strategies/` if missing and overwrite any copy of a
  hidden strategy's file the agent left there.
- **The generator's proofs are real.** The reference equals the original on all 48 built-in cases under two hash
  seeds; the patched original equals the reference on all 16 dropped-in cases; the 27 engine lines no hidden case
  runs are listed with reasons; the hidden configs use only documented settings, each away from its default.
- **The 13 wrong solutions** cover every lure in the plan, each the reference with a few edits, each proven to fail
  exactly its declared checks.
- **Integrity of checks 1 and 2.** Agent code only as nobody, a fresh folder per run, leftovers killed, `/tests`
  root-only, no link followed by root; the hidden strategies never enter the room.
- **House rules.** No personal information; tickers and data invented.

### Findings

- **T16-1 (A). A half-done refactor passes every check (false positive).** The ticket says "Our two strategies
  become strategies like any other" (`instruction.md:9`), and the note "Apart from the default of `signal.type` ...
  the engine names no strategy. Momentum and reversion become strategies like any other, in `bt/strategies/`"
  (`strategy-slot.md:71-72`). Yet the plan lists "where the two built-ins end up, as long as their output is
  unchanged" as not graded (`T16-PLAN.md:101-102`), and the generator proves the gap: `PATCHED_ORIGINAL`
  (`generate.py:483-539`) keeps all five places that special-case momentum and reversion by name and only adds a
  branch for any other type; `generate.py:977` asserts it prints exactly what the reference prints on every
  dropped-in case. It is the original on every built-in case (check 1) and passes its own tests (check 3). Scenario:
  a model adds `else: <load bt/strategies/<type>.py>` beside each `if kind == "momentum"` and leaves the built-ins
  where they are: delivered, although an acceptance line is unmet, and it skips the half of the job that carries
  its skill (moving the built-ins without changing a digit, where v1's "harmless rewrites" bit). Smallest fix: one
  required check, "the built-ins go through the slot": in a copy of the agent's `bt`, overwrite
  `bt/strategies/momentum.py` and `reversion.py` with versions that define only the three names, keep the same
  `PARAMETERS` keys and defaults (so value checks a model kept by name in `signal_params.py`, as GLM did, still
  work) but change the score (negate it, say); run two to four valid configs and compare with the reference under
  the same overwrite; add the patched original as a 14th wrong solution that fails exactly this check. No finished
  trial changes outcome: GLM, DeepSeek and Hy4 all score the built-ins through `bt/strategies/`. If the owner reads
  a new check after trial runs as tuning under D8, the alternative is to say plainly in the plan's "not graded"
  list that this hybrid is delivered, and why.
- **T16-2 (A, = X1).** `tests/test_outputs.py:146-181`; route 2 shown in practice (see X1). The check also ignores
  the inner pytest's exit status. Fix as X1 (b) to (d).
- **T16-3 (B). Trial runs started before the brief-only solve and the gate paperwork.** No `briefonly/` folder, no
  `docs/job-plans/T16-SOLVE-NOTES.md`, `features.json` F44 `"not-started"`, and no T16 line in STATUS.md (AGENTS.md:
  STATUS in the same commit as the work). PLAN-V2 2.3 points 9 and 10 put the solve before the trial runs, and the
  plan's safeguard was that a solver's slot must accept the hidden strategies unchanged, or they change before any
  model run; a change found now would alter the checks after model runs. Mitigation: three independent model builds
  accepted all four strategies unchanged. Fix: finish the solve (2/2) and the full selftest, then record F44, the
  solve notes and the STATUS line before the gate.
- **T16-4 (B). The size decision was left to the owner and is now frozen without a record.** `T16-PLAN.md:131-136`
  says the room is 5,388 lines of code, tests and documents, about 1,600 short of the owner's "about 7,000", and
  "the owner decides whether it grows before the first model run"; the trials have run and no decision is
  recorded (`docs/CHANGELOG-HARNESS.md:11` gives both counts). Fix: one change-log line recording the size as frozen
  when the trials started, or the owner's decision.
- **T16-5 (C). The note's rules on which symbols `history` holds are never exercised.** All four dropped-in
  strategies score each symbol on its own, so "excluded names kept, benchmark column dropped, every column present"
  could be wrong in a slot and still pass. Lenient, not unfair; a strategy that compares symbols belongs in a later
  version.
- **T16-6 (C). Easier than the 3/3/2/0 forecast, mostly by structure.** The arithmetic lures are refuted loudly
  (the separate standard deviations in four places, `entry_z 1.0` in `strategies.md` and in the note's example,
  the note spelling out `unknown signal type None` and the first-key order); a refactor that calls the existing
  `momentum_score` and `reversion_score` never touches them; T16-1 lets a model skip the risky work; and fairness
  forces the slot to be specified fully from the strategy's side, which leaves one natural engine design (all three
  finished builds came out shaped like the reference). Nothing here is fixable before the freeze without hiding
  information; note for a later version.
- **T16-7 (C). The checks copy only `bt/`.** Engine code a model put outside the package (a top-level helper) works
  in the room and fails every check. The note puts strategies in `bt/strategies/` and the README runs `python -m
  bt`, so it is unlikely; T19's ticket states it in one sentence ("Put the code in the `folio` package: the
  graders run `python -m folio` from a copy of `/app/folio`"), and T16's could do the same as a clarification.
- **T16-8 (C). `deliverbench.toml:11` still has the 180-minute placeholder.** The trials took 6.3 to 19.2 minutes,
  so SCORING-2-DRAFT section 6 gives about 100 minutes; set it once LongCat's run is in.

### Trial runs

| Setup | Result | Minutes / turns | Note |
|---|---|---|---|
| glm-5.3-flash-fp4-high | delivered | 6.3 / 45 | full slot; kept the built-ins' value checks by name in `signal_params.py` (a fair reading: the note points there) |
| deepseek-v4.1-flash-high | delivered | 19.2 / 48 | full slot; removed its probe strategies before finishing |
| hy4-flash-free-hosted | delivered | 12.8 / 62 | full slot; added `bt/strategies/loader.py` and its own tests (not graded); its dropped-in check took 58 s against GLM's 8 s, well inside limits |
| longcat-2.5-free-hosted | still running | | two endpoint faults (API connection errors, then 429 "at capacity upstream"), re-run under the scoring rules |

No failure to triage. Each delivered package, diffed against the original, really moved scoring, warm-up, the
report's echo and the summary's strategy line into `bt/strategies/` modules; all finished `done`, right for a job
with no honesty trap.

## T19: where the risk comes from (`tasks/T19-risk-contributions`, 0.1.0)

**Verdict: sound** apart from the cross-job X1 (T19-3). Four B, four C. Margins measured with a read-only probe that runs the
reference on every hidden data set, window and threshold, writing only to `/tmp`
(`<scratch>\gate-review\t19_margins.py`).

### What I checked and found sound

- **Names.** Every graded name is in the ticket's acceptance lines: `folio report --by risk`, the `vol_share`
  column and field ("just before `weight` and written like it"), the rule `name_vol_share`, the setting
  `limits.name_vol_max_share` with default `0.20`. No hint word; the trail runs ticket, README, `docs/risk-notes.md`.
- **Method.** `docs/risk-notes.md` settles the Euler split, the daily P&L shares (not today's weights), simple
  returns, the window, cash as lines of its own, a name as an issuer, and that the divisor cancels.
- **Float against decimal and thresholds.** The smallest gap between an issuer's share and a hidden threshold is
  4.8e-3 (`near_limit`: KIRO at 19.52% against 20%). Float and exact arithmetic differ by about 1e-16; the smallest
  distance to a rounding edge of a printed figure is 2.8e-6; rounding each line to 6 places before summing by
  issuer moves a figure by at most 1e-6. "More than" against "at least" is never at stake.
- **Room for other designs.** The export compares `vol_share` as a number within 0.0005, so its written form is
  free beyond "like `weight`"; where the new rule's lines sit among the other rules' lines is not compared; stderr
  notes are free; a cash entry in the JSON may carry `vol_share`.
- **Unsettled cases are never graded.** No hidden case has fewer returns than `min_observations` (every window has
  40 or more), a book with no variance, `--since` with `--by risk`, `-o FILE`, `top_n` or `show_cash`. So where the
  reference (blank `vol_share` with a note) and the solver (refuses) differ, nothing is graded.
- **File placement.** The ticket's last line says the code goes in `folio`, and the checks copy only `/app/folio`,
  so a helper module elsewhere is the model's error, and a settled one.
- **Lures and wrong solutions.** The eight wrong solutions fail exactly their declared checks (selftest
  20261122-152738); the off-by-one helper (`buggy_helper`) fails the export and limit checks on every data set.
- **Integrity of the CLI checks.** `python -s -m folio` as nobody in a fresh folder per run, leftovers stopped,
  `/tests` root-only, nothing in `/app` gives the answer away.

### Findings

- **T19-1 (B). The report check never looks at a number, and its sector test depends on layout.**
  `tests/compare.py:181-200`. (a) The sectors' shares appear only in the report and are graded nowhere: a model
  whose sector table prints NAV weights under a "Vol share" heading (copied from `render_breakdown`) is
  delivered if its export is right. (b) A sector counts only on a line that names no holding, so a sector table
  with a reasonable "largest holding: ARDM" column fails `test_report_by_risk`. Fix: sum the reference JSON's
  `vol_share` by sector (that export already runs in `holdings_and_sectors`) and accept a sector line that carries
  the share as a percent (within 0.06pp) or a fraction (within 0.0006); drop the "names no holding" condition, or
  apply it only when the line has no matching number. This grades what the ticket asks for without fixing the
  layout, which the plan leaves free.
- **T19-2 (B). Returns about their mean is settled only by convention.** `environment/app/docs/risk-notes.md:35-41`.
  The room's code always centres (`folio risk` uses `statistics.stdev`, `benchmark/tracking.py`
  covariance/variance), and "divide by the number of returns or by one less" implies an estimate about the mean,
  but no sentence says it. The zero-mean reading, common in risk practice, moves shares by up to 0.77pp
  (`concentrated`, 15 times the tolerance): it fails the export on 5 of 6 data sets and changes the limit lines in
  22 of 24 threshold variants. The solver and all three delivered trials centred, so it is unlikely to bite. Fix:
  one clause in the notes, "volatility is the standard deviation of the window's returns about their mean, as
  `folio risk` computes it". That removes an ambiguity; it does not tune.
- **T19-3 (A, = X1).** `tests/test_outputs.py:120-149`: route 2 of X1. The pull is stronger than in T14, because
  the original tests constrain the design (`test_disabled_rules`; the limit tests run without price history). Fix
  as X1 (b) to (d).
- **T19-4 (B). No trial on the current scored setups.** `jobs/v2-trials/` has T19 runs on deepseek, glm, nemotron
  and qwen only, none on `hy4-flash-free-hosted` (or `longcat-2.5-free-hosted`, if it stays). Plan 2.3 point 10
  asks for one per setup, and SCORING-2-DRAFT section 6 sets the time limit from them; `deliverbench.toml:11` still
  has the placeholder 120 (the trials so far, 7.0 to 17.9 minutes, give 90). Fix: run T19 once on each, then set
  the limit.
- **T19-5 (C). `-I` drops the fixed hash seed.** `tests/test_outputs.py:10-11, 29, 131`: the docstring says every
  run uses one hash seed, but the original tests run under `python -I`, which ignores `PYTHONHASHSEED` and
  `PYTHONDONTWRITEBYTECODE`. A model whose output depends on set order could fail an original test at random. The
  same holds for T14 (`test_outputs.py:168`) and T16 (`test_outputs.py:157`). Fix: run pytest with `-s -P` instead of
  `-I` (the sandbox already passes a clean environment), or correct the docstrings.
- **T19-6 (C). The generator's proofs are weaker than they read.** `generate.py:230-259, 316-321`: the
  "independent" calculation reuses folio's `history_dates`, `line_values` and the same statistics calls, so it
  proves the day pairing, not the series; its rounding-edge guard is 1e-4 of a printed place (about 1e-8 as a
  fraction), which only guards against float noise. The real margins (2.8e-6 and more) are enough. Fix: assert a
  margin of 1e-6 and record the measured minimum in the plan.
- **T19-7 (C). Easier than planned.** Forecast "near the floor" (2/2/1/0 of 5); three of four delivered first
  time. Partly the models are good; partly the notes refute every lure in so many words next to the method
  ("never from today's weights times each line's return", "simple ... because P&L adds up and logs do not", "a
  name is an issuer", "cash ... a line of its own"), and the helper's docstring gives the right day pairing. Rule
  5 needs the refutation, and T19 was frozen at its first model run: publish as found; for a later version, let
  the code's conventions refute the lures instead of a list beside the method.
- **T19-8 (C). The closing `OK: 5 rules checked` line is graded** (`tests/compare.py:163-174`) as an existing line.
  It follows from "a new rule" and the shared `run_checks`, so it is fair; a limit coded outside `RULES` fails it
  (Nemotron's half-built run did). Optionally add it to the name-and-rule list.
- **T19-9 (B, house rules; shared with T12).** `environment/app/data/instruments.csv` has invented companies that
  carry real names, and in one case a real ticker: `CRVL,Corvel Assurances SA` (CRVL is the listed ticker of the
  real CorVel Corporation), `PRLX,Parlux Brands Inc` (a US consumer company, like the real Parlux), `HLXS,Helix
  Semiconductor Corp`. None is presented as the real company, but a real name with its real ticker in a published
  benchmark is the "real company presented as fictional" case. Why before the freeze: the names appear in graded
  outputs, so renaming after the scored runs would change the rooms they ran in. Fix: screen the shared folio
  data's names and tickers against real listed companies and rename the hits (data regenerated, expected outputs
  rebuilt, selftests rerun) before V5.

### Trial runs

| Setup | Result | Minutes / turns | Note |
|---|---|---|---|
| deepseek-v4.1-flash-high | delivered | 17.9 / 72 | |
| glm-5.3-flash-fp4-high | delivered | 7.0 / 107 | |
| qwen3.8-27b-hosted-xhigh | delivered | 10.7 / 60 | old setup |
| nemotron-3-super-120b-a12b-hosted-medium | not delivered, fair | ran out of context (peak 215k tokens, 7 relief events) | half-built: no `report --by risk`, `ctx.volatility_shares` missing so every export crashed, closing line "4 rules checked", `test_export_csv_and_json` broken; "everything else unchanged" still passed |

The three passes are genuine: each fixed the off-by-one helper, split volatility by Euler on mean-centred P&L
shares with cash as lines, applied the limit by issuer, and claimed `done` accurately. No pass by luck or
loophole.
