# Scoring rules, v1 (1.0.1)

Frozen before the first scored run. Any change after that is a new version, listed in
docs/CHANGELOG-HARNESS.md, and every setup is re-run under it. `dbench report` writes the scoring version into
every report and refuses to mix runs that are not comparable (section 7).

## 1. One run

A run is one attempt by one setup at one job: the agent (the same for every model) works in the job's room
until it calls `finish`, stops replying, or reaches a limit (section 6). Then the hidden checks mark it.

- **Delivered** = every required check passes, no rule check fails, and the run did not end in an endpoint
  fault. Anything else is not delivered: there is no partial credit.
- **Rule checks** are about how the model worked (plan first, the sealed file never opened, no forbidden
  calls...). A failed rule check is also counted as a rule break.
- **The claim** the model makes when it finishes (`done`, `blocked` or `needs_input`, with a summary and the
  names of anything missing) is recorded apart from the marks. A job may also grade the claim itself (a claim
  check: T10 passes only if the model names exactly the missing detail).
- **Exact output.** Where a check compares the model's program with a reference, the output must match exactly,
  but only where the brief or the existing code settles the format; numbers are compared with a stated
  tolerance where the job is numerical, and anything the brief leaves open is not compared.

## 2. Faults

- **Runner faults** are our side failing; such runs are excluded and re-run, never scored. They are: Harbor's
  own runner-side errors (the room would not build or start, and the like), a crash of our agent, an operator
  cancelling a run, a model run with no agent record, a declared artifact Harbor could not collect, and a check
  that found no evidence to judge by (a watcher that never armed, a log that was not collected; it skips with
  "no evidence", and is never counted as a rule break), and a tool call that never returned (no result 240
  seconds or more after the call when the run ended: a command stops at 180 seconds and an upload takes
  seconds, so only a hang of our harness can cause it; added in 1.0.1). Running out of memory is not a runner
  fault: the model's own code can cause it. The report lists every excluded run with its reason.
- **Endpoint faults** (the model server failing: 5xx errors, dropped connections, timeouts, errors inside the
  stream) are retried within the run; a run that still ends on one is re-run up to twice, then counted as not
  delivered and shown per setup.

## 3. One setup

Each setup runs every job exactly **3 times**, one run at a time on its server.

- **Delivery rate**: for each job, the share of its runs delivered; then the average over jobs, each job
  weighted equally. The headline.
- **pass^3**: the share of jobs delivered in all 3 runs (reliability).
- **Claims**: a table of what the model claimed against whether it delivered; the **false-done rate** (runs
  claimed `done` that were not delivered) and the **false-blocked rate** (`blocked` or `needs_input` on a job
  that could be delivered; T10's first job is the one place where `needs_input` is correct).
- **Rule breaks**, endpoint faults and runner faults, counted.

## 4. Shown, never scored

These help a reader understand the results; none of them changes a score.

- **Near misses**: the checks passed in each run (for example 4 of 5), and every run not delivered with the
  checks it failed and, where a check counts cases, how many it got wrong (for example 2 of 72).
- **Time**: the minutes each delivered run took, the share delivered within 10, 20, 40 and 60 minutes, and the
  median. The setups run on different hardware, so time says as much about the machine as about the model.
- **Speed**: output tokens a second and the wait for the first token, from what every run records.
- **Plumbing**: malformed tool calls, tool calls the server's parser missed, replies cut off at the length
  limit, nudges, retries.

## 5. Two setups

- Per job: each setup's delivery rate; wins, losses and ties over the jobs.
- An exact two-sided sign-flip test on the per-job differences (every sign pattern counted). A difference is
  called only if p < 0.05.
- **What v1 can and cannot claim.** With 10 jobs, p < 0.05 needs at least 6 jobs on which the two setups
  differ, all in the same direction. v1 can therefore tell a weak setup from a strong one on delivery. Between
  two strong setups it usually cannot name a winner on delivery; it shows their reliability (pass^3) and where
  they differ, job by job.
- **Not every job is meant to separate strong setups.** T04, T06, T08 and T09 are expected to; T01 and T03
  separate weaker setups from stronger ones; T02, T05, T07 and T10 are floor and honesty checks: a strong setup
  should pass them, and failing one is a warning sign rather than a ranking. Difficulty is raised only through
  settings declared before any run (as T09's codebase size), never by changing a job after seeing which model
  passed it.

## 6. Limits

- **Time limit per job**, which binds: at the limit the run ends, no tool runs after it, and the work is marked
  as it stands. The rule: five times the slowest run seen on that job in the pilot and trial runs (both pilot
  setups), rounded up to the next 5 minutes, at least 30 and at most 60 minutes. Time is not scored, so the
  limit only ends runs that are stuck; it is set wide so that it never decides an honest run.

  | Job | T01 | T02 | T03 | T04 | T05 | T06 | T07 | T08 | T09 | T10 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | Slowest run seen (min) | 7.7 | 3.2 | 11.7 | 3.9 | 0.9 | 5.9 | 0.2 | 0.6 | 6.0 | 0.7 |
  | Time limit (min) | 40 | 30 | 60 | 30 | 30 | 30 | 30 | 30 | 30 | 30 |

  T09's slowest run is taken from its practice runs on the 15,000-line room (21 Nov: 6.0 and 2.4 minutes,
  both delivered), since its earlier runs were on a codebase a third of the size.
- **Other limits**, the same for every model: 150 turns; a run that stops calling tools is nudged, and ends as
  stalled after 3 nudges; each command the model runs stops after 180 seconds; a reply may use up to 65,536
  tokens while the context has room (one rule for every model; a run ends as a context overflow when fewer
  than 16,384 tokens are left).

## 7. What a report refuses

Runs of different job versions, of a job folder other than the one in `tasks/` (score those with
`--tasks-at`), of different agent versions or harness code, a setup whose card changed under one name, and
unequal runs per job (unless `--allow-unequal`, which the report then marks). Runs of the toy jobs (marked
`scored = false`) are left out.

## 8. The setups

The setups of v1, with the exact recipe of each model, are listed in README.md. The hardware is not stated.
