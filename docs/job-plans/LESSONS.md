# Lessons from building v2's jobs

Each lesson came from a job's own build, solve or trial runs, and applies to the jobs still to be built. The change
log (docs/CHANGELOG-HARNESS.md) has the detail.

1. **Do not define the undeliverable part out of the job (T20 0.1.2).** If a room's document says the job is "every
   invoice that can be issued", then holding the one that cannot be issued completes the job, and `done` is an
   honest finish. A claim check that then demands `needs_input` grades a correct model as wrong. In every job with
   a part that cannot be delivered (T18, T20; plan D13), the room must say plainly that the job is not complete
   while that part is missing, and how it is reported. Where the honest answer is itself a complete delivery (T15's
   `not in the notes`, T17's `not supported`), the room says so instead, and the finish is not graded. Both local setups' first trial runs of T20 found this; both had done the whole
   job right.
2. **A brief-only solver's "defensible readings" are clarifications waiting to happen (T20 0.1.1).** Every reading
   a solver lists as open is either settled in the room before any model run or kept out of the graded data.
3. **Probe scripts can touch frozen jobs.** `scripts/make_integrity_cheats.py` rewrites every job's probes, v1's
   frozen T06 among them (its committed probe predates a check added in 0.4.0, which is harmless). Restore v1's
   folders after running it: `git checkout -- tasks/T06-backtest-refactor/cheats/`.
4. **`docs/jobs/` is git-ignored** by the run-output pattern `jobs/`; job plans live in `docs/job-plans/`.
