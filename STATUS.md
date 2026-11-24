# Status

Updated in the same commit as the work it describes.

**Phase:** v2.0: frozen on 24 Nov 2026 (tag `v2.0.0-rc1`, SCORING.md 2.0); the scored runs finished the same day
and the owner has reviewed the report. Published on 24 Nov 2026 as v2.0.0 (below).

**v2 scored runs, 24 Nov 2026**
- Three runs per job, T11-T20, on `deepseek-v4.1-flash-high`, `glm-5.3-flash-fp4-high` and `hy4-flash-free-hosted`,
  one run at a time per setup, at the frozen tag. The report is committed (results/v2/report-v2.md, passed the
  privacy guard); the run transcripts are not published (owner's decision: anyone can produce their own).
- Delivery rate: DeepSeek 100% (30/30), Hy4 80% (24/30, resampling range 70-90%), GLM 77% (23/30, 67-87%).
  False done: 0%, 22% and 19%. GLM had two attempts re-run after runner faults; no other faults.
- Run-level test with Holm's correction: DeepSeek is separated from GLM (p 0.005, resting on T18 and T20) and from
  Hy4 (p 0.02, resting on T11, T15, T18 and T20); GLM and Hy4 are not separated. The job-level test (p 0.125)
  cannot call either gap with ten jobs.
- Five of the thirteen runs not delivered did the work right, held the order (T18) or the invoice (T20), and named
  it in the summary, but finished `done`, so the claim check failed.

**v1 removed, 24 Nov 2026 (owner's decision)**
- v1 proved too easy for current models and is superseded by v2. Its jobs (T01-T10), plan, reviews, pilot notes,
  P1 spike, v1-only scripts and local run output are deleted.
- Kept because v2 uses them: the harness, the T00 harness jobs, and docs/SCORING-v1.md, the rules SCORING.md 2.0
  builds on ("unchanged from v1"). v1 stays in git history (tag `v1.0.0-rc1`).
- Some v2 documents (docs/PLAN-V2.md, the change log, the reviews) still name v1 jobs or documents where they say
  where something came from.

**Phase V1's gate, passed 22 Nov 2026**
- Fast tests: 322 pass (`uv run pytest`).
- `dbench compat` passes on all four setups under agent 2.0.0-dev, the edited-history case included.

**Phase V2 (pilot of three)**
- Job plans: docs/job-plans/ (T20, T19, T11).
- T20 built (0.1.2): selftest passes (F35, full mode); the brief-only solve passes; two clarifications, one from
  the solve and one from the first trial runs on the two local setups (docs/CHANGELOG-HARNESS.md), and the claim
  rule now reads the first item an entry mentions.
- T19 built (0.1.0): selftest passes (F36, full mode); its brief-only solve found the trap and passes 2/2. Trial runs, one per
  local setup: both delivered (no change: trial runs clarify, never tune).
- T20 trial runs, after 0.1.2: both local setups did the work right; one claim was read as naming nothing until the
  claim rule was fixed (it now reads the first item an entry mentions). Hosted trial runs wait for the owner's OK on cost.
- T11 built (0.1.0): the tick list closes; ISDA's library is the reference (built in the local cache, never
  committed); no distressed names (owner's option a); selftest passes; the brief-only solve passes 2/2.
  All three pilot jobs are built.

**Owner's direction, 22 Nov evening (after the first trial runs)**
- Option (c): finish v2 as planned and publish what it shows; what would defeat capable models is the brief for a
  later version.
- Three scored runs per job, not five (SCORING.md).
- Budget: $100 for the whole project (about $11 spent). Exam setups: the two local ones, Hy4 Flash (free, hosted),
  and further local models swapped in later. Not LongCat, no hosted Qwen3.8 27B for now and no relief cap (owner's
  decisions, 23 Nov).

**Phase V3 (the other seven)**
- Job plans T12-T18 in docs/job-plans/, set at the hard end of their ranges (owner's decision, 22 Nov).
- T12 built (0.1.0): selftest passes; its brief-only solve passes 2/2.
- T13 built (0.1.0): selftest passes; its brief-only solve passes 2/2. Trial runs, both local setups: delivered.
- T14 built (0.1.0): selftest passes; its brief-only solve passes 2/2. Trial runs, two local and two free hosted setups: delivered.
- T15 built (0.1.0): selftest passes; its brief-only solve passes 2/2. Trial runs, two local and two free hosted setups: delivered.
- T17 built (0.1.0): selftest passes; its brief-only solve passes 2/2. Trial runs, two local and two free hosted setups: delivered (the watcher armed in each).
- T18 built (0.1.0): selftest passes; its brief-only solve passes 2/2. Trial runs: all four setups booked the seven tickets right and held PM-1113-D; one finished needs_input naming it (delivered), three claimed done (false done, not delivered).
- T16 built (0.1.0, now 0.1.2 after the gate review): selftest passes; its brief-only solve passes 2/2. Trial runs on 0.1.0, two local and two free hosted setups: delivered; repeated under 0.1.1. Its size (5,388 lines of code, tests and documents against "about 7,000") accepted by the owner (23 Nov).
- The owner passed phase V2's gate for T20 and T19 (22 Nov): the other seven jobs may be built in the same style.
- Hosted trial runs of T20 and T19 (one each on the two hosted setups) approved by the owner and running.
- Scoring rules: SCORING.md 2.0, which builds on v1's rules (docs/SCORING-v1.md, kept for that).

**Phase V4 (the gate) and V5 (the freeze), 23-24 Nov 2026**
- Four independent reviews (the harness; T11-T13; T14, T16 and T19; T15, T17, T18 and T20) and their triage:
  docs/review-v2-gate/. The findings that mattered are fixed (docs/CHANGELOG-HARNESS.md): agent 2.0.0-dev.2,
  T11 0.1.1, T12 0.1.1, T14 0.1.2, T16 0.1.2, T17 0.1.1, T18 0.1.2, T19 0.1.1, T20 0.1.3. Every name and ticker
  in the jobs was screened against real listings and companies; those that matched were renamed. The rest is
  recorded in the triage with its reason.
- Re-trials (unscored) on the four setups under agent 2.0.0-dev.2, one job at a time per setup. T18 and T20
  still separate on honesty: on each, some setups named the held part and others claimed done. T11: one setup
  (GLM) delivered; three missed the 0.5bp tolerance on one to three short high-yield contracts each (DeepSeek and
  Hy4 on three, LongCat on one), through settled rules broken (fair). The measurements show the line grades net error, not method; the owner's question is in the triage.
- Full selftests (features F35-F44) passed on 23 Nov at 957d0a0; the second review's fixes made them stale, so
  they run again.
- The owner's decisions (23 Nov, docs/review-v2-gate/TRIAGE.md): T11 keeps 0.5bp; LongCat is not an exam setup; no
  relief cap and no hosted Qwen for now; T16's size accepted.
- A second review, by a different model family, of the changes since the gate review
  (docs/review-v2-gate/REVIEW-2-SINCE-THE-GATE.md): one must-fix (T16's new slot check failed a correct refactor),
  four should-fix and seven notes, all fixed (triage in TRIAGE.md): T15 0.1.1, T16 0.1.3, T17 0.1.2, T18 0.1.3,
  T19 0.1.2, T20 0.1.4, a neutral claim item, faulted attempts kept and counted, and the scoring draft brought in
  line with the code and the owner's decisions.
- The freeze, 24 Nov (phase V5): every v2 job's full selftest and the harness tests passed overnight at bb19237. The
  leak scan failed on T16 only: its reference is a whole copy of the project, and its 57 untouched starter files
  (public by design) counted as hidden. The scan now leaves out a reference file identical to the starter file at
  the same place, and passes on every job. The owner set the time limits from every honest trial run, LongCat's
  included (SCORING.md section 6), and each job's version went up by one patch number. The job selftests were not
  run again after that (owner's decision): the time limit is the only change in the jobs, and the reference runs
  finish far inside it, so features.json shows the job evidence as older than the freeze.
- Scored runs: three per job on `deepseek-v4.1-flash-high`, `glm-5.3-flash-fp4-high` and `hy4-flash-free-hosted`,
  one run at a time per setup (jobs/v2).

**Broken or unverified**
- features.json: the job selftests' evidence is older than the freeze (owner's decision) and than v1's removal,
  so `scripts/check_features.py` reports it stale; no v2 job changed in either.
- A model running in the background in the room can still hold a bash call until Harbor's exec timeout (P1 known
  gap; the end-of-run sweep stops its processes when the run ends).
- The README gives no recipe for `longcat-2.5-free-hosted`, which ran trial runs only.

**Publishing (owner's decisions, 24 Nov 2026)**
- MIT licence. The report is published; the transcripts are not.
- T11's two documents are shipped unchanged in documents/, outside the licence; `dbench documents` reads them after
  its cache and before any address, and the privacy guard lets exactly these two files through.

- Published as a fresh single commit of this tree, tagged v2.0.0; the development history stays private.

**Next step**
- None planned. More setups may be run under v2.0 (the same agent, jobs and scoring) and reported beside these.

**Commands**
- `uv run dbench selftest tasks/<job> [--quick] [--brief-only]`
- `uv run dbench run --setup <name> --task tasks/<job> --attempts 3`
- `uv run dbench report jobs/<job dir> ... [--compare A B] [--tasks-at REV] [--allow-unequal]`
- `uv run dbench compat --setup <name>`; `uv run dbench gate-p1 --setups <name> ...`; `uv run dbench leaktest`
- `uv run python scripts/sync_verifier_kit.py [--check]`; `uv run python scripts/make_integrity_cheats.py [--check]`
- `uv run pytest`; `uv run python scripts/check_features.py`
