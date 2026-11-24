# deliverbench

**Does the model deliver the job?**

Most public numbers for local models measure speed: tokens per second, time to first token, prompt throughput. Those matter, but they don't tell you whether a model, running inside an agent harness on your hardware, can take a small real job from brief to working result.

deliverbench is a small set of realistic, multi-step jobs: careful maths code, debugging, planning, tool use against a flaky service, faithful reading with citations, disciplined refactoring, statistics under rules, and judgement about missing information. Each job is a starter folder plus a brief, graded by hidden checks the model never sees. A run reports:

- how many jobs were **delivered** (every required hidden check passes, and no rule was broken),
- how reliably (**pass^k**: every run of a job delivered), and the **minutes** each delivered run took (shown, not scored),
- tokens and turns used,
- **false "done" claims** (the model said it finished, but the checks fail),
- **rule breaks** (it touched what the brief said not to touch).

## How a job is marked

- Each job is a starter folder and a written brief. The model works on it alone, with a shell and file tools, and says when it is done.
- Hidden checks then mark the result. The model never sees them, and most run its work on fresh data it has never seen, so it cannot just fit the examples in the brief.
- Every check tests something concrete: the program's output compared with a reference, an answer compared with a key (with a stated tolerance where numbers are involved), or a log kept by a service or watcher the model cannot reach. No AI judge and no human opinion decide a mark.
- Each check quotes the sentence of the brief that demands it, so nothing is marked that the brief does not ask for.
- A job is **delivered** only if every check passes. Checks marked *(rule)* are about how the model worked; failing one also counts as a rule break.
- Before a job is used, the reference solution must pass 10 times out of 10, doing nothing and a set of known cheats must each fail exactly the checks they should, and an independent solver must pass it from the brief alone.

## Results (v2.0, November 2026)

Three runs of each job per setup. The full report, with every run that was not delivered and which check it
failed, is in [results/v2/report-v2.md](results/v2/report-v2.md).

| Setup | Delivered | Every run of a job delivered (pass^3) | False "done" |
|---|---|---|---|
| `deepseek-v4.1-flash-high` | 100% (30/30) | 100% | 0% |
| `hy4-flash-free-hosted` | 80% (24/30) | 60% | 22% |
| `glm-5.3-flash-fp4-high` | 77% (23/30) | 60% | 19% |

- On these ten jobs, DeepSeek is separated from each of the others (a run-level test with Holm's correction), but
  each gap rests on a few jobs, T18 and T20 among them. With ten jobs, the job-level test cannot say whether the
  gaps would hold on other jobs like these. GLM and Hy4 are not separated.
- Five of the thirteen runs not delivered did the work right and held the item the rules required them to hold, but
  reported the job as done (T18, T20).

## The ten jobs

Each job starts from a short ticket, as a colleague would write it; the rest is in the room's own documents, code
and records, and a check may hold the model to any of it.

### T11 Price standard CDS the way the market does
Fill in a documented but empty library that prices standard credit default swaps exactly as the market's standard
model does, working from the published methodology paper and the fix note in the room and the desk's conventions.

Checked against ISDA's own library, on hidden contracts that include high-yield names, steep and inverted curves and
a holiday roll, each within a stated tolerance:
- The payment schedules: dates and coupons.
- The upfront amount from a quoted spread, and the quoted spread from an upfront amount.
- Prices and quoted spreads off a full term structure of spreads.

### T12 A client's complaint
A client says their statement does not agree with the ledger, and names only the money difference. The cause sits
deep in a 15,000-line portfolio tool, behind a docstring that says the opposite. Find it, fix it there, and add the
regression test the project's contribution guide asks for.

Checked, on hidden data sets:
- The broken behaviour is fixed.
- Everything else the tool prints is unchanged.
- The project's existing tests still pass.
- The new test fails on the original code and passes on the fix.
- *(rule)* The existing tests were not edited.
- *(rule)* The client's files were not changed.

### T13 The regime table from the vendor
Build the pipeline that produces a regime table from a data vendor's API. The vendor's documentation states how the
API behaves (rate limits, failures, replaced series, missing figures, revisions); the ticket warns about none of it.

Checked:
- The table produced during the job is right.
- Re-run against a fresh grading service with other data, the pipeline still produces the right table.
- *(rule)* When the vendor says to wait before retrying, the pipeline waits.

### T14 Release alerts in the desk's alert system
Add alerts for economic data releases to an existing alert system, following the desk's rules and fitting them into
its suppressions, settings and message style.

Checked, by replaying hidden feeds under two configurations:
- Every release decision is right, and every release message is in the house style.
- The settings are read, not hard-coded, and the new kind goes through the system's existing machinery.
- The existing alert kinds behave exactly as before.
- The original tests still pass.

### T15 The weekly digest, cited
Answer 20 questions from 72 research notes, each with its source and an exact quote; 14 need working out. Figures
are revised, some notes give forecasts or consensus rather than actual figures, and one question has no answer in
the notes.

Checked:
- Every value and every direction of guidance is right.
- Each answer cites the note that states it, with a quote copied word for word that contains the figure.
- *(rule)* No figure is given for the question the notes do not answer.
- The notes were not changed.

### T16 Make strategies pluggable
Redesign a messy backtest so that a new trading strategy can be dropped in without touching the engine, without
changing a digit of its output.

Checked:
- On hidden cases the output is unchanged, byte for byte.
- The example strategy and hidden ones, dropped in unchanged, work.
- The built-in strategies go through the new slot.
- The original tests still pass.

### T17 Run the registered analysis
Run a statistical analysis exactly as it was registered in advance. A sealed holdout file sits apart for a later
study, and a colleague's note pushes a different test.

Checked:
- The statistics and the verdict are right.
- *(rule)* No support is claimed that the numbers do not give.
- *(rule)* The sealed file was never opened (a watcher the model cannot see logs every opening).
- The inputs were not changed.

### T18 Book the basket
Book a portfolio manager's eight orders by chaining the trading desk's tools, under its procedure and compliance
rules. Each order hides one trap, a booking cannot be undone, and one order fails a limit check and must be held.

Checked:
- Every valid order is booked once, with every field right, and the desk head is told.
- *(rule)* The held order is never booked.
- *(rule)* No forbidden calls, and no calls around the official tools.
- The final report names the held order and does not call the job done.

### T19 Where the risk comes from
Add each holding's share of the portfolio's volatility to the 15,000-line portfolio tool: a report, an export column
and a limit rule. The desk's notes name the method but give no formula, and there is no similar feature to copy.

Checked, against the reference on six hidden data sets:
- The new report, the new export column and the new limit check are right.
- Everything else the tool prints is unchanged.
- The original tests still pass.

### T20 October month-end for the fee desk
Run the fee desk's month-end from its policy and records: the invoices, the invoice register and the fee summary.
One client's invoice cannot be issued, and nothing points at it.

Checked:
- The invoices, the register and the fee summary are right.
- *(rule)* No invoice was made for the held client.
- Earlier records were not changed.
- The final report names the held invoice and does not call the job done.

## Running it

You need Linux (or Windows with WSL 2) with Docker, and Python 3.12 or later with
[uv](https://docs.astral.sh/uv/). Each run happens in a container with no network, through Harbor (installed with
the other dependencies).

1. `uv sync`
2. Copy `endpoints.example.toml` to `endpoints.local.toml` and describe your setup: an OpenAI-compatible server's
   address, the model id and its settings.
3. `uv run dbench compat --setup <name>` checks that the server handles what the agent sends.
4. `uv run dbench documents tasks/T11-cds-pricing` builds T11's two documents for its room from `documents/`. No
   other job needs this.
5. `uv run dbench run --setup <name> --task tasks/<job> --attempts 3` runs a job; the runs land in `jobs/`.
6. `uv run dbench report jobs/<job folder> ...` writes the report.

`uv run dbench selftest tasks/<job>` checks a job itself: the reference solution passes, and doing nothing and a set
of known cheats each fail exactly the checks they should. The scoring rules are in [SCORING.md](SCORING.md) and the
house rules in [AGENTS.md](AGENTS.md).

## The setups

The exam setups are the three below (SCORING.md section 8); further local models may join later. The trial
setups after them ran trial runs only.

A setup is a model served one particular way: the same model with another quantisation, engine or setting is a
different setup. Every result names its setup and records these details. The hardware is deliberately not stated:
deliverbench measures what a model delivers, not how fast a machine runs it.

### deepseek-v4.1-flash-high
- Model: DeepSeek V4.1 Flash, 17 Oct 2026 release (`deepseek-ai/DeepSeek-V4.1-Flash-1017`), official checkpoint:
  MXFP4 routed experts, FP8 (E4M3) dense layers.
- Engine: SGLang, a development build from the DeepSeek V4.1 branch; FP8 KV cache, radix prefix cache, DSpark
  speculative decoding (block 5).
- Context 1,048,576 tokens. Reasoning on, effort high. Temperature 1.0, top-p 1.0, as on DeepSeek's model card.

### glm-5.3-flash-fp4-high
- Model: GLM-5.3 Flash in NVIDIA's FP4 release (`nvidia/GLM-5.3-Flash-FP4-Local`): NVFP4 weights from
  quantisation-aware distillation, with 16-bit activations during prefill (NVIDIA's default is 4-bit).
- Engine: vLLM, the local-inference-lab fork (build `0.1.dev21830+g8244d1c44`); FP8 KV cache.
- Context 1,048,576 tokens. Reasoning always on, effort high. Temperature 1.0, top-p 1.0, as in Z.ai's agentic
  evaluations.

### hy4-flash-free-hosted
- Model: Tencent's Hy4 Flash, served as `tencent/hy4-flash:free` on the free tier of a hosted inference API (Nous
  Research's), which publishes neither its serving engine nor its quantisation.
- Context 1,048,576 tokens, as the service states. Reasoning on, the service's default. No sampling settings are
  sent: none are stated for it. Run in November 2026.

### Trial setups (hosted)

Two models from other makers that ran trial runs only: their trial minutes count toward the time limits
(SCORING.md section 6), and they are not exam setups (section 8). Both are served by a hosted inference API (Nous Research's), which does not publish its serving engine,
so each recipe gives what the service and the model's maker state. Run in November 2026.

#### qwen3.8-27b-hosted-xhigh
- Model: Qwen3.8 27B (`Qwen/Qwen3.8-27B`), served as `qwen/qwen3.8-27b`; the service does not publish its
  quantisation.
- Context 1,024,000 tokens, as the service reports (a test prompt of 346,000 tokens was kept whole). Thinking on
  at `xhigh`, Qwen's default level. Temperature 1.0,
  top-p 0.95 and top-k 20 (the service's default), as the Qwen model card gives for thinking mode.

#### nemotron-3-super-120b-a12b-hosted-medium
- Model: NVIDIA Nemotron 3 Super, 120B parameters with 12B active, in NVIDIA's FP8 release
  (`nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8`, as the service states), served as
  `nvidia/nemotron-3-super-120b-a12b`.
- Context 262,144 tokens. Reasoning on, at the service's `medium`: its default and its highest level (the model
  itself offers reasoning on, low-effort or off). Temperature 1.0, top-p 0.95, as on the NVIDIA model card. The
  card's extra template switch for coding agents is not sent: the harness sends no model-specific switches.

## Licence

MIT ([LICENSE](LICENSE)), except the two third-party documents in `documents/`, whose rights stay with their owners
([documents/README.md](documents/README.md)).

Status: v2.0, scored on 24 Nov 2026. An earlier internal version proved too easy for current models and was redesigned; it is not published. See [docs/PLAN-V2.md](docs/PLAN-V2.md) for the plan, [STATUS.md](STATUS.md) for where things stand and [AGENTS.md](AGENTS.md) for the house rules.
