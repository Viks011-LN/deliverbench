# V4 gate review: T11, T12, T13

Reviewer: fresh, independent, read-only. Repo `~/Projects/deliverbench`, branch `v2-harness` at `2b7ca03`.
Read: PLAN-V2 (sections 2 to 4, D8 to D20), AGENTS.md, SCORING-2-DRAFT, LESSONS, CHANGELOG (22 and 23 Nov),
BRIEF-ONLY-SOLVES, STATUS; each job's ticket, room, tests, generator, wrong solutions, deliverbench.toml, plan and
solve notes; T11's tick list, `isda/driver.py` and `isda/answers.json`/`tests/data/cases.json`; every T11 to T13
trial's junit, finish claim and transcript (tool calls), and the trial artifacts.

**Result: 0 A, 2 B, 6 C. All three jobs are sound: no false negative or false positive that can change a delivery,
and no integrity hole.**

| Job | Verdict |
|---|---|
| T11 | Sound. The tolerance is exactly the agreed one, and the plan's premise is proved on every hidden case. One wording/copy mismatch between the README and the grader (B1). |
| T12 | Sound. Nemotron's failure was fair: it read the README line that sends it to CONTRIBUTING.md, never opened that file, and wrote no test. |
| T13 | Sound. Every kind of quirk, with its one handling, is in the vendor document; the grading service has other instances of the same kinds; the waits are judged on the re-run only. |

---

## T11: the tolerance against the agreed threshold

The agreed bar (PLAN-V2 section 3 and D11): spreads within 0.5bp; an upfront within what 0.5bp is worth on that
contract; schedules exact. It is "the level at which a careful implementation that skips the standard's smallest
details still agrees with an independent one" (the owner's earlier pricer, which differs from ISDA only by the
half-day adjustment).

**As built, the tolerance matches this exactly. It is no tighter and no looser anywhere.**
- Spreads: `SPREAD_TOLERANCE_BP = 0.5` (generate.py) for the quoted spread from an upfront, and for the par spread
  and quoted spread off a curve.
- Upfronts: the cash tolerance per contract is ISDA's own dirty-cash change for a 0.5bp bump. For a conversion, the
  quoted spread is bumped; for a contract priced off a curve, the coupon is bumped (generate.py, `IsdaEngine.upfront`
  and `curve_price`). Points get the same amount in percent. The bump comes to $539 on a 1-year IG contract, $2,246
  on a 5-year IG contract and $43 on the 1-month U-16, which matches the plan's "about $2,000 on 10 million over
  five years".
- Exact items: the accrued premium and every coupon are graded to the cent, and dates exactly. These are pure
  date arithmetic on settled rules, so the plan's "schedules exactly" covers them. No reading moves them.
- The premise is proved, not just claimed. generate.py reruns the reference without the half-day adjustment and
  asserts that it passes every hidden case under the checks' own rules (largest effect 0.09bp). Distressed names
  were removed for exactly this reason. The owner's earlier pricer deviates only by the half day (+$9 IG, +$42 HY),
  so it would pass every case.
- What the room leaves open moves an answer by 0.04bp at most (tick list, measured). The one-day observation rules
  sit near the line but are each written in the conventions: protection start moves C-11 by 0.65bp and fails; the
  flat-curve start is 0.39bp, value date 0.33bp and survival to the payment date 0.19bp, and none of those fails on
  its own. Fair, because each is settled in the room.

**The other side of the same bar (trial evidence, C1).** Two of the three passes are not exact pricers:

| Setup | Largest error | Tie-outs | Time |
|---|---|---|---|
| glm-5.3-flash-fp4-high | 0.000bp on every check | to the cent | 13 min, 47 turns |
| deepseek-v4.1-flash-high | 0.331bp (U-16), 0.330bp (C-11) | off by about $2 to $20; said so in its summary, finished `done` | 85 min, 121 turns |
| qwen3.8-27b-hosted-xhigh | **0.490bp (Q-14)**, 0.441bp (U-13) | 2 to the cent, 2 within 30 to 50 cents | 75 min, 141 turns |

Qwen's pricer contains a fitted fudge. Its `cdslib/legs.py:116` (the trial's artifact) sets the first coupon to
`(pay_date - step_in).days - (step_in - accrual_start).days / 360`, which subtracts a fraction of a coupon from a
day count. That term fits the investment-grade tie-outs, but it treats the paid-back accrued premium as risky. The
error grows with the hazard rate, and on a 1-year HY contract at 25% recovery it reaches 0.49bp: Qwen passed by
0.01bp. This is the 0.5bp rule working as the plan wrote it ("Passing needs only the 0.5bp threshold"). It is not a
defect. It does mean that T11 "delivered" does not mean "priced to the standard", and a near miss either way is
decided by the mix of hidden cases.

---

## Findings

### B1. T11: the README promises a copy of the whole folder, but the grader copies only `cdslib` and two data files

- **Where:**
  - `tasks/T11-cds-pricing/environment/app/README.md:14` says: "The desk's tools import `cdslib` from a copy of
    this folder, with `data/` beside the package".
  - The grader, `tests/test_outputs.py:33-37`, copies only `/app/cdslib`, then writes `CASES["files"]`.
  - That list leaves out `data/tie-outs.csv` (`generate.py:462`).
  - The name-and-rule list says "the graders copy cdslib with the original data/ beside it", and the original
    `data/` includes the tie-outs.
- **Scenario:** a model puts a shared helper at `/app/isdamath.py` and imports it from `cdslib`, or has
  `cdslib/__init__.py` load `data/tie-outs.csv` for a self-check at import. Everything works in the room, which is
  "this folder". At grading the driver's `import cdslib` raises ModuleNotFoundError or FileNotFoundError, and all
  five checks fail on a correct pricer. No trial did this; it is rare but plausible.
- **Smallest fix (a clarification, not a tuning):**
  - Keep `data/tie-outs.csv` in `files` (drop the filter at `generate.py:462`).
  - Reword README line 14 to "from a copy of the `cdslib` package alone, with the desk's `data/` folder beside it
    (nothing else in this folder is copied)".

### B2. T11 to T13: trial failures not triaged in writing; T11 and T12 not trial-run on an exam setup; one T13 run has no verdict

- **What STATUS records:**
  - T12: no trial runs at all.
  - T13: only "both local setups: delivered".
  - T11: no trial outcome beyond the changelog.
  - The V4 gate requires "every failure triaged in writing".
- **Untriaged runs:**
  - T11 Nemotron (fail).
  - T12 Nemotron (fail).
  - T13 Nemotron (fail).
  - T13 Qwen (no verdict).
- **The Qwen T13 run:**
  - The agent finished at 9.9 minutes.
  - Harbor's log stops at "Stopping main service before sidecar evidence collection" (`jobs/v2-trials/T13-vendor-pipeline--qwen3.8-27b-hosted-xhigh--20261122-210647/*/trial.log`).
  - The job's `result.json` has `finished_at: null`, and there is no junit.
  - It is either a teardown hang outside the agent's call cap or a manual stop.
  - Its own run left a correct room table (it matches `keys.json` "room" row for row). Its re-run was never graded.
  - It is 1 of 14 sidecar teardowns in the trials, so a one-off so far.
- **Missing exam-setup trials:** T11 has trials on the four old setups only, and T12 on three (DeepSeek, GLM,
  Nemotron). Neither has a run on `hy4-flash-free-hosted`, which is an exam setup since 22 Nov (or on longcat).
  SCORING section 6 sets each job's time limit from the trial runs, and T11 is the longest job (85 minutes, with
  peak prompts of 342k to 647k tokens).
- **Fix:**
  - Paste the triage below into STATUS.
  - Record the Qwen T13 run as a runner fault with no verdict.
  - Run one trial each of T11 and T12 on `hy4-flash-free-hosted` (and later on each local exam model) before
    setting their limits.

**Triage of every T11 to T13 trial that failed a check (all fair, all the model's fault):**

| Trial | Failed | What happened | Fair? |
|---|---|---|---|
| T11 Nemotron | all 5 | The last period ends on the maturity date instead of the day after, against the conventions' "runs through the maturity date itself". Points are far off (-117 for -0.835), and the quoted spread is pinned at 1,000bp. Finished `needs_input`, listing four functions as missing, after 9.7 minutes. | Yes: settled rules, and the plain tie-outs show both errors |
| T12 Nemotron | regression test only | The right one-character fix; the other 5 checks pass. It never wrote a test (`no new tests/test_*.py file in /app`). Turn 5: it read `/app/README.md` in full, including lines 94-95, "Before you hand in a fix, read `CONTRIBUTING.md`: it says what a fix and its test must do". Turn 6: `ls -la /app` listed CONTRIBUTING.md. It never opened it, and finished `done` at turn 39. | **Yes.** The demand sits on a short, plain trail (ticket, then "start with /app/README.md", then the Tests section, then CONTRIBUTING.md), and the evidence map records that trail. DeepSeek and GLM both read CONTRIBUTING.md at turn 2. The check did not misfire: no file existed to judge. A care slip, and a near miss for the report |
| T13 Nemotron | table, re-run | It wrote the CSV with literal `\n` (backslash, n) between rows, so the file is one line and the header check fails. Every one of its 298 rows is numerically right (checked against `keys.json`). It never looked at its file; finished `done` in 3.6 minutes. | Yes: the output is not a CSV. This is the self-checking the plan describes |

### C1. T11: the 0.5bp bar lets non-standard pricers pass, by margins down to 0.01bp

As set out in the section above. No change is possible under D8, and none is needed: the plan chose this bar.
Three things to do:
- Record in the T11 notes that the plain, IG-only tie-outs can be overfitted (Qwen) and that the bar absorbs that.
- Make sure the report prints T11's largest-error diagnostic beside its delivery, so a reader sees 0.000bp against
  0.490bp.
- Soften PLAN-V2 line 153 ("A slip that looks right ... moves the spread by more than half a basis point"). It is
  true for the listed lures and false for one-day slips (up to 0.39bp each, per the tick list) and for Qwen's fudge.
For a later version: one HY tie-out, or a per-case look at the diagnostic.

### C2. T11: outsiders cannot rebuild the methodology paper

`deliverbench.toml:55-60` declares the paper with a `local_source` and an sha256, but no address. Anyone rebuilding
T11 needs a byte-identical copy of the 2003 Lehman PDF, or the build fails, so the public benchmark has one job
outsiders likely cannot build. This does not block the freeze. For V6, either:
- find a public copy whose sha256 matches (for example, an archive.org capture) and add it as `url`/`backup_url`; or
- say in the README that T11 needs the paper added by hand, and what to do if no matching copy exists.

### C3. T12: easier than planned, because of where two things sit (fixable only in a later version)

All three setups opened `positions.py` between turns 6 and 27, made the fix between turns 13 and 34, and finished
in under 6 minutes. DeepSeek: 4.7 minutes, 28 turns. GLM: 2.8 minutes, 30 turns. Nemotron: 5.2 minutes, 39 turns.
Nobody tried the "next-day holdings" lure. Two things shorten the planned five-call path:
- **The docstring.** The bug's own docstring states the right rule on the line above it: `positions.py:54` says
  "The lots traded on or before ``as_of``", and line 57 has `<`.
- **The reconcile check.** The documented self-check `folio.ledger reconcile` prints "DIFF GRVS: open quantity
  12,200 from trades.csv, 19,700 in positions.json", plus the lot dates. That names the instrument and the day.

Both are deliberate: the docstring is one of the four places that settle the rule, and reconcile is the room's
self-check. Under D8 neither may change now. For v3: keep the rule in ARCHITECTURE.md and ledger.md, which already
settle it, and leave the docstring neutral. Separately, the models are good: DeepSeek and GLM read CONTRIBUTING.md
at turn 2, and DeepSeek proved its new test fails on the original by undoing its fix and rerunning the test.

### C4. T12: the regression-test check cannot tell a real regression test from a sham one

The check needs at least one new test that fails before the fix by an assertion and passes after it. A test such
as `assert "<=" in inspect.getsource(Position.lots_as_of)` meets that. Also, the before and after statuses are read
from a junit file written by a pytest process that runs the agent's test code (`tests/test_outputs.py:113-126`), so
an `atexit` hook in the test file could rewrite it. Neither gives more than the sham test already gives, and every
other check stands on its own. Note only; a guard (rerun the junit report from a root-owned process) is not worth
the cost now.

### C5. T13: easy for capable setups by design, not through a fixable give-away

Delivered by GLM in 2.7 minutes (18 turns), hy4 in 3.8 (17), DeepSeek in 8.2 (17) and longcat in 19.3 (52).
Qwen's own table was right too. All of them read the whole vendor document first and handled every quirk on their
first write; the two pipelines I sampled (GLM, hy4) really check `page`, keep the latest vintage, treat "." as no
figure, follow `replaced_by` and sleep out `Retry-After`. Under house rule 5, the document must state each fact
("it is not zero", "the figure as it stands today is its latest vintage", "a response's `page` always names the
page it holds"), so a careful reader needs to notice nothing in the data. This is the job as designed plus good
models, and there is nothing to fix. The re-run grading is sound:
- The quirk cycle covers every starting point.
- The 429-plus-5xx and 5xx-plus-5xx runs at grading are the same patterns met in the room.
- The service log is root-only.
- No-network and `python -E -s` match the README's "nothing else can be installed".

### C6. T13: the vendor's name is Microsoft's stock fictional brand

"Woodgrove" (README.md:28; macro-api.md:1) is a fictional name, not a real company, so house rule 5 holds. It is,
though, Microsoft's well-known sample brand (Woodgrove Bank). Consider an invented name before V6.

---

## Checked and found fine (so nobody re-checks them)

- **Hint words.** No forbidden word in any of the three tickets. The T13 ticket's "has both figures" and "as they
  stand today" are business rules, not give-aways.
- **Integrity.**
  - In all three jobs the agent's code runs only as nobody in a scratch copy.
  - Keys (`cases.json`, `keys.json`, `grading.json`, the bundles) stay in root-only `/tests`.
  - T11's `isda/` and the ISDA library never enter the room.
  - T12 restores the original tests and pyproject before running anything, and runs the original suite in a fresh
    root without the agent's conftest.
  - T13's grading service and log are root-owned.
- **The T11 reference.**
  - `isda/driver.py` sets only the dates and conventions the conventions note states (accrual start, step-in, T+3
    on the desk's calendar, F/S stub, `protectStart`, CDSone benchmark at the accrual start).
  - The par spread is taken from clean prices at coupons 0 and 1, which is linear in the coupon, so it is exact.
  - An independent Python reference agrees with ISDA to 1e-8bp and $0.001, asserted on every generate run.
  - All 10 hidden schedules are consistent with the written rules, including the Juneteenth roll (S-03, S-07) and a
    trade accruing from the 20th itself (S-05).
- **T12's one right behaviour.**
  - Settled in four places.
  - Settled dates (a weekend, a date past the last price) follow `resolve_as_of`'s docstring.
  - "Where the fix sits" is truly ungraded: both strong setups' fixes are the reference's single character.
- **T13's checks.** Numbers are compared within 1e-9 (so "0.53" and "0.5300" both pass). There are no zero changes
  and nothing sits on a rounding edge (asserted). `CPI_YOY` answers 404 at grading, as the document says an id that
  was never issued does.
- **House rules.** No personal names, paths or addresses in the three job folders or their plans. The fetched texts
  are git-ignored and uncommitted.
