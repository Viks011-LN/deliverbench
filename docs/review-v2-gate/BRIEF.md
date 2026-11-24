# deliverbench v2: the V4 gate review (independent)

You are a fresh, independent reviewer. You built none of these jobs and have no stake in them. Your review decides
what must be fixed before v2 is frozen and the scored runs start, so be exact and adversarial, and say plainly when
something is fine.

## The project in one paragraph
deliverbench asks "does the model deliver the job?". Each job is a sealed Docker room (no network) with a short
ticket from a colleague, a repository or set of documents, and hidden checks that grade the run all-or-nothing. A
job is delivered only if every required check passes, no rule check fails, and (for the two jobs with an
undeliverable part, T18 and T20) the finish claim names it. v2 has ten jobs, set at the hard end of their ranges.
Each setup will get 3 scored runs per job. The repo is in WSL at `~/Projects/deliverbench`, branch `v2-harness`.

## Read first (all reviewers)
- `docs/PLAN-V2.md`: section 2 (the rules every job must meet), section 3 (the jobs), section 4 (scoring),
  the D-decisions.
- `AGENTS.md`: house rules (no personal information; never name real private projects; fictional companies;
  published standards only through the download script).
- `docs/SCORING-2-DRAFT.md`.
- `docs/job-plans/LESSONS.md`; `docs/CHANGELOG-HARNESS.md` (22-23 Nov entries); `docs/BRIEF-ONLY-SOLVES.md`.
- `STATUS.md` (the trial results so far).

## Evidence you can use
- Each job: `tasks/<job>/` (instruction.md = the ticket, environment/ = the room, tests/ = the hidden checks,
  solution/ = the reference, cheats/ or generate.py-written wrong solutions, deliverbench.toml = settings, the
  evidence map, the name-and-rule list), its plan `docs/job-plans/<job>-PLAN.md` and the independent solver's notes
  `docs/job-plans/<job>-SOLVE-NOTES.md`.
- Trial runs (unscored, one per setup): `jobs/v2-trials/<job>--<setup>--<time>/<trial>/`. Each has
  `deliverbench-transcript.jsonl` (every model turn and tool call; the `end` record has the finish claim) and
  `verifier/junit.xml` (which checks passed). Setups: `deepseek-v4.1-flash-high`, `glm-5.3-flash-fp4-high`,
  `hy4-flash-free-hosted`, `longcat-2.5-free-hosted` (plus a few older hosted ones). Transcripts are large: read
  them with `grep`, `tail`, or a small Python script; never print a whole one.
- `uv run dbench claims jobs/v2-trials/<job>--*` replays the finish-claim rule.

## Rules for you
- **Read-only.** Do not edit anything in the repo, do not commit, and do not run `generate.py`, `dbench selftest`,
  `dbench run`, Docker or anything that writes into the repo (a full selftest chain is running on this machine,
  and memory is tight). Reading files, `grep`, `git log/diff/show`, and small Python scripts that only read are
  fine. Write scratch scripts in `<scratch>\gate-review\`.
- Use WSL via `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu --exec bash -lc 'cd ~/Projects/deliverbench && ...'`;
  put multi-line code in a script file (written with the Write tool), not inline.

## What to look for, per job
1. **Fairness.** Is every graded output settled by the ticket and the room in plain words? Find any reading a
   careful professional could reasonably take that changes a graded output. Does the ticket give anything away
   (the `[hints]` words)? Could a correct, complete, honest delivery fail a check (a false negative)? Name the exact
   input and output.
2. **Soundness of the checks.** Could a wrong or partial delivery pass (a false positive)? Is anything graded that
   the job never asked for? Do the wrong solutions really cover the lures, and does each fail for the declared
   reason? Are the generator's proofs (independence of the key, rounding edges, uniqueness) real?
3. **Integrity.** Can a model read the key, edit the checks, or game the grader (the room, permissions, what runs
   as whom, what the checks trust from the agent's files)?
4. **The trial runs.** For every trial that failed a check: was the failure the model's fault and fair? For a
   sample of passes: did the model really do the job, or pass by luck or a loophole? Note how fast each setup
   delivered: the trials show the strong setups delivering most jobs first time; say whether any job is easier than
   its plan intended because of something fixable (a give-away in the room, a lure refuted too loudly), and
   separately whether it is simply that the models are good. Do not propose making jobs harder by hiding
   information: house rule 5 requires every graded rule to be settled in the room.
5. **House rules.** Personal information, real private projects, real companies presented as fictional, anything
   that would embarrass a public release.

## Grading your findings
- **A**: must fix before the freeze (a false negative or false positive that can change a delivery, an integrity
  hole, a broken house rule).
- **B**: should fix before the freeze (an ambiguity unlikely to bite, a weak check, a misleading doc).
- **C**: nice to have, or note for a later version.

For each finding: the job, the file and line, what is wrong, a concrete scenario (inputs → wrong outcome), and the
smallest fix. Say explicitly which jobs you found sound. Keep it tight: no padding, no restating the plan.

## Output
Write your review to `<scratch>\gate-review\REVIEW-<your part>.md`
and reply with a short summary: counts of A/B/C and the A findings in one line each.
