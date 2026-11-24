# T16 job plan: make strategies pluggable

The successor of v1's T06 (docs/PLAN-V2.md section 3). One page: the ticket, the room, the levers, the lures with
their wrong solutions, the acceptable finishes, and what is not graded. The evidence map and the name-and-rule
list go in the job's deliverbench.toml.

## The ticket (instruction.md, about seven lines, from the quant lead)

Every new strategy means editing the backtest's engine in five places. Please make strategies pluggable: a new
strategy should be a file of its own that the engine picks up from the config, with no change to the engine. The
slot is described in `docs/design/strategy-slot.md`, and `examples/strategies/` has one written for it, with the
output it should give. Our two strategies become strategies like any other. Nothing the program prints may
change, for any input, and the tests in `tests/` keep passing (they will be run as they are).

Give-away words kept out: float, floating, digits, sum, fsum, square root, sqrt, numpy, order of operations,
exit status, error message, warm-up, None, registry.

## The room: a new codebase, described at plan level

The desk's backtest, `bt`: v1's T06 program and its conventions (daily closes, trades at the close, weights of
NAV, commission, slippage and borrow, forced exits, monthly and yearly returns), grown over years into about
5,000 lines in about 40 files, standard library only, with about 100 tests and golden files for both strategies.
Messier than v1's on purpose:

| Part | What it holds |
|---|---|
| `bt/config/` | loading, defaults (every setting documented in the README) and validation; per-strategy parameter lists and their error messages |
| `bt/data/`, `bt/signals/`, `bt/portfolio/`, `bt/execution/`, `bt/engine.py` | prices and forward fill; momentum and reversion scoring behind an `if`/`elif` on `signal.type`; ranking, the weight cap, volatility scaling, drawdown control, rebalancing days and bands; costs, borrow and forced exits; the day loop, which works out each strategy's warm-up from its own parameter names |
| `bt/report/` | the JSON report (it echoes the `signal` section: `type`, then that strategy's parameters with defaults filled), the equity CSV and a text summary that names the strategy |
| the mess | two rolling standard deviations that add up in a different order (one for reversion, one for volatility scaling), constants defined twice, a `bt/legacy/` runner still imported by one test, and v1's week-number quirk in weekly rebalancing |
| `docs/` | README (running it, every setting), ARCHITECTURE.md, and `docs/design/strategy-slot.md` |
| `examples/` | `strategies/channel.py`, written for the slot, with its config, a price file and the `report.json` and `equity.csv` the reference build prints for it (review R11) |

`signal.type` is special-cased in five places: validation, warm-up, scoring, the report's echo and the summary.

`docs/design/strategy-slot.md` fixes the slot from the strategy's side and leaves the engine's design open:

- a strategy is a module `bt/strategies/<type>.py`, chosen by the config's `signal.type`, as today;
- it defines `PARAMETERS` (names and defaults, in order), `warmup(params)` (days of prices it needs before its
  first score) and `score(history, params)`;
- `history` maps each symbol to its forward-filled closes from the first day up to and including today, oldest
  first, `None` where still missing; `score` returns a number or `None` per symbol, and `None` leaves the symbol
  out of the ranking, as today;
- the engine fills in defaults, refuses an unknown parameter or `signal.type` with today's messages, and echoes
  `type` and the parameters in `PARAMETERS` order;
- after scoring, everything existing still applies unchanged (ranking, cap, volatility scaling, drawdown
  control, rebalancing, costs); a strategy receives no portfolio state;
- the engine names no strategy.

## Levers and settings (frozen before the first model run)

| Lever | Setting |
|---|---|
| Scale and length | about 7,000 lines in about 55 files; five special cases to remove |
| Design freedom | the engine's side of the slot is the model's |
| Self-checking | the example strategy and its expected output; golden files for both strategies |
| Lures | the two summation orders, the duplicated constants, the week-number quirk, error messages for bad configs |
| Hidden data | 8 price files; for each built-in strategy 6 configs (every documented setting, the ones the sample never uses included) and 3 option sets; 12 invalid configs; 3 hidden strategies, each on 4 inputs |

**Owner's decision (22 Nov 2026, before any model run of this job): every setting at the hard end of its range.** Raised: about 7,000 lines in about 55 files (was about 5,000 in about 40); three hidden strategies, the top of the plan's two or three.

## How it is graded

1. **Output unchanged**: every hidden run of the two strategies prints the original's stdout, stderr and equity
   file byte for byte, with the same exit status (invalid configs included).
2. **Strategies dropped in**: the example and the three hidden strategies, copied unchanged into
   `bt/strategies/` of a copy of the model's `bt`, print exactly what the reference build prints on the hidden
   inputs.
3. **Existing tests** pass, run in their original form.

## Names and rules the grader relies on (review R2)

| Name or rule | Settled in |
|---|---|
| where a strategy goes, its three names, `history`'s shape, `None`, defaults, the echo's order, the error messages | `docs/design/strategy-slot.md` |
| `signal.type` selects the strategy | the design note; README (settings) |
| what the program prints, for any input and setting | the ticket; the original program; README (every setting) |
| the expected output of a strategy written for the slot | `examples/` |

## Lures and the wrong solutions that fall for them (each must fail exactly its checks)

| Wrong solution | Fails |
|---|---|
| A slot whose engine still keeps a list of the two strategies | dropped in |
| Warm-up still worked out from `lookback` or `window` | dropped in |
| `history` passed in another shape (a matrix by day, or without today's close) | dropped in |
| Defaults left to each strategy, not filled in by the engine | dropped in |
| The two rolling standard deviations merged into one | output unchanged |
| A sum rewritten while the scoring code moves (a loop for `sum()`, `statistics`, `math.fsum`) | output unchanged |
| New validation that changes a message or its order for a bad config | output unchanged |
| The report's echo rebuilt in another key order | output unchanged |
| The week-number quirk fixed on the way | output unchanged |

## Acceptable finishes

`done` with everything delivered. No honesty trap; a quirk the model spots may be mentioned in the summary, and
leaving it as it is is the right move (the ticket says nothing may change).

## What is not graded

The engine's design, module layout and names outside the slot (since 0.1.1 the built-ins' files,
`bt/strategies/momentum.py` and `reversion.py`, are part of the slot; see "Changed at the gate review"); tests of the
model's own; the summary.

## Fairness notes

- The design note fixes everything a hidden strategy relies on and nothing about the engine (review R11: the
  example ships with its expected output, so anyone can test a slot against the note).
- The solver's two builds must accept the example and the hidden strategies unchanged; a hidden strategy that
  needs anything the note does not state is changed or cut before any model run.
- "Nothing may change" meets one edge: a config naming a type that has no module still gets today's error. The
  hidden invalid configs never name a type the example or a hidden strategy could serve.
- Hidden strategies use only the note's interface: `None` scores, defaults, a long warm-up, negative scores with
  shorts allowed, a parameter echo.
- The generator proves each wrong solution above moves at least one compared output, and that the hidden configs
  use only settings the README documents.

## Open questions for the owner

1. **Codebase size.** Recommendation: about 5,000 lines in 40 files. The plan counts T16 among the longest jobs,
   and the special cases have to be spread far enough that removing them is real work.
2. **The week-number quirk.** Recommendation: keep it, unflagged. The ticket says nothing may change, which settles
   it, and it is one of v1's exactness traps carried over.
3. **What a strategy may see.** Recommendation: prices only, no portfolio state, so every honest engine can serve
   the hidden strategies. A strategy that sizes itself would make the slot's design decide the result.

## Decided at the build (version 0.1.0, before any model run)

Built as `tasks/T16-pluggable-strategies`. Where the build differs from the plan above, or settles what the plan
left open:

1. **Size (differs from the owner's setting).** The room holds 5,388 lines of code, tests and documents in 91 files
   (bt: 63 modules, 2,662 lines; tests: 16 files, 2,094 lines, 296 test items; 10 documents, 591 lines; the example
   strategy; pytest.ini), and 7,669 lines in 108 files with the sample prices, the golden files and the example's
   data. The plan's "about 7,000 lines in about 55 files" is met only if the data files count, and the code is split
   into more, smaller modules than planned. Counting code, tests and documents only, the room is about 1,600 lines
   short of the setting; the owner decides whether it grows before the first model run.
2. **Two built-in strategies,** momentum and reversion (v1's blend is gone). The program grew the features a desk
   backtest accrues, none of them strategy-specific: a benchmark column, an exclusion list, a minimum history, a
   stop loss, a turnover cap, interest on cash, a trade log (`--trades`), the worst drawdowns, position statistics,
   a text summary with a monthly grid (`--format text`), an HTML page (`--format html`), gap warnings on stderr,
   and desk tools in `bt/tools/` (compare, prices_info, sweep, batch, walkforward, settings, migrate).
3. **The five special cases** are `bt/config/signal_params.py` (types, parameter lists, value checks), the warm-up in
   `bt/engine.py`, `compute_scores` in `bt/signals/__init__.py`, `signal_echo` in `bt/report/json_report.py` and
   `strategy_line` in `bt/report/summary.py` (the HTML page reuses it). `docs/ARCHITECTURE.md` lists four of them
   (stale; it describes the warm-up in its day-loop section instead). `bt/legacy/` and the migrate tool also name
   the two strategies; they are not the engine.
4. **The slot as the design note fixes it.** `PARAMETERS` is a dict (names to defaults, in order). The warm-up is
   exact: the first rebalancing day has index max(warmup(params), `vol_window`), day 0 being the run's first day
   (v1 added one; T16's engine does not). `history` holds every traded symbol (the benchmark column left out,
   excluded names kept) in file order, forward-filled closes from the run's first day through today, `None` where
   missing; `score` returns a dict; a symbol with no close today is left out whatever it scores. The engine fills
   the defaults, keeps today's messages (an unknown type is written with `repr`, so a config without a type gets
   `unknown signal type None`) and checks the signal where it does today. The message lists no types, so a strategy
   file left in `bt/strategies/` cannot change it. Apart from the default of `signal.type`, the engine names no
   strategy (stated in the note; not graded).
5. **The built-ins' value checks** (lookback, skip, window, entry_z) stay, with their messages; the note says so and
   leaves the how to the model. The reference gives its built-in strategies an optional `check(params)`; the hidden
   strategies define only the three names.
6. **The duplicated constants** carry a lure: `bt/signals/reversion.py` has `ENTRY_Z = 1` (an int) where the README,
   `SIGNAL_DEFAULTS` and the note's own example give 1.0, so a slot built from the scoring module's constants echoes
   `entry_z 1`. TRADING_DAYS is also defined three times, with one value.
7. **Lures, as built.** Every wrong solution is the reference with a few edits (generate.py, WRONG); the generator
   proves each one fails exactly its declared checks, and counts what it moves:

   | Wrong solution | Fails | Moves |
   |---|---|---|
   | the engine keeps a list of the two strategies | dropped in | 16 of 16 dropped-in cases |
   | warm-up from `lookback` or `window` | dropped in | 8 |
   | history as a matrix by day (built-ins adapted) | dropped in | 16 |
   | history cut to the last warm-up + 1 closes | dropped in | 4 (the hidden strategy with an expanding window) |
   | history without today's close | all three | the built-ins cannot keep their output this way |
   | defaults left to each strategy | dropped in | 11 |
   | the two rolling standard deviations merged | output unchanged, dropped in | 10 built-in, 2 dropped-in |
   | reversion's `sum()` rewritten as a loop | output unchanged, existing tests | 10 built-in, 1 test (a golden file) |
   | the signal checked after the other settings | output unchanged | 2 (the invalid configs with two problems) |
   | the echo in the config's key order | output unchanged, dropped in | 4 built-in, 3 dropped-in |
   | the week-number quirk fixed | output unchanged, dropped in | 15 built-in, 7 dropped-in |
   | reversion's defaults from the scoring module (`entry_z` 1) | output unchanged | 6 |
   | `bt/legacy/` deleted as dead code | existing tests | the whole suite (a collection error) |

   Hidden only (no visible test or golden file catches them): the merged deviations, the validation order, the echo
   order, the quirk, `entry_z` 1, and the slot lures the example does not catch (the defaults, the history window).
   The example catches a list of types, the warm-up from names and the matrix by day. Its config gives all its
   parameters and its prices cross no New Year.
8. **Hidden data, as built:** 8 price files (ten names across two New Years with a late listing; gaps and blank
   lines; a pinned takeover target and a cheap name; a crash; a bear market; a 70-day file; one across New Year
   2026; a tiny one for the invalid configs); four carry a benchmark column. Six configs per built-in strategy use
   every documented setting away from its default and give and leave out each parameter (asserted), each under
   three option sets: the JSON report with the equity curve and trade log; the text summary from a later start;
   the HTML page with both files over a window. Twelve invalid configs, all on the signal but two (not JSON, an
   unknown setting), two of them pairing a signal problem with another one. The example and three hidden
   strategies (`pullback`: a warm-up longer than its `lookback`, shorts, defaults; `steady`: an expanding window, a
   long warm-up, `None` scores; `breakout`: mostly `None`, negative scores) on four inputs each, some with a
   benchmark, an exclusion list, a minimum history or a stop loss.
9. **Grading.** Exit status, stdout, stderr, equity curve and trade log are compared exactly; the agent's package
   runs under hash seeds 1 and 2. Expected outputs are produced at grading by the shipped original (built-in cases)
   and by the reference with the strategy dropped in. `--help` and argparse's usage errors are not compared.
10. **The independent implementation** behind the dropped-in outputs is the original with each strategy added the
    old way: five edits, one per special case (generate.py, PATCHED_ORIGINAL). It prints exactly what the reference
    prints on every dropped-in case. The reference also prints what the original prints on every built-in case,
    under two hash seeds, and passes the 296 visible tests. The hidden cases run every line of the original's
    engine-side modules but 27, each listed with its reason (generate.py, UNREACHED: mostly checks on plain
    settings, which the visible tests run, and benchmark edge cases).
11. **Integrity probes.** `scripts/make_integrity_cheats.py` needs one line for T16; its probes were written with a
    scratch wrapper that adds it. T06's own setup would copy `/solution/bt` into the room's existing `/app/bt`:
    `TAMPER["T16"] = (TAMPER["T06"][0], TAMPER["T06"][1], "rm -rf /app/bt\ncp -r /solution/bt /app/bt\ncp /solution/bt/cli.py /app/bt/_reference_cli.txt\n")`
12. **The time limit** is a placeholder (180 minutes) until the trial runs set it. The brief-only solve is run
    separately by the builder.

## Changed at the gate review (version 0.1.1)

The gate review (findings T16-1 and T16-2) found a hybrid that passed every check of 0.1.0: momentum and reversion
still special-cased by name in the five places, and a branch for every other type added beside each. The
generator's own `PATCHED_ORIGINAL` is exactly that, and it printed what the reference prints on every case, although
the ticket says "Our two strategies become strategies like any other."

1. **The note, clarified in one sentence.** It already put the built-ins "in `bt/strategies/`"; it now names their
   files and how they run: "Their files are `bt/strategies/momentum.py` and `bt/strategies/reversion.py`, which the
   engine runs as it runs any strategy file."
2. **A fourth required check, `test_builtins_go_through_the_slot`.**
   - Changed momentum and reversion, written for the slot (`strategies/builtins/`, hidden), are copied over
     `bt/strategies/momentum.py` and `reversion.py` in a copy of the agent's package and of the reference.
   - The two must print the same on four valid configs: two per strategy, under the three option sets, with every
     parameter given in the note's order, no volatility target and no weekly schedule.
   - The changed files keep the built-ins' `PARAMETERS`, defaults and warm-ups and define only the three names, so
     value checks a model keeps by parameter name still hold. Only the score changes: momentum is turned round, and
     reversion keeps the z-score's sign with half the band.
   - A hybrid runs its own built-ins, ignores the files and fails.
3. **A fourteenth wrong solution, `hybrid`:** the room's own bt with `PATCHED_ORIGINAL` applied. It fails exactly the
   new check, on 4 of 4 cases.
4. **The proofs.** The independent implementation is now `FILES_FIRST`: the original with five edits that serve
   any type, the built-ins included, from its file in `bt/strategies/` when there is one. The generator asserts:
   - it prints what the reference prints on every dropped-in and every swapped case, and what the original prints
     on every built-in case;
   - every swapped case moves the reference's output, and the original ignores the swap;
   - doing nothing and the plant probe now fail the dropped-in and the swapped checks;
   - the tamper probe and "history without today's close" fail all four checks, and "history as a matrix by day"
     fails the dropped-in and the swapped checks. The other eleven wrong solutions are unchanged by the new check.
5. **T16-2, the original-tests check's own junit.**
   - T16 copies only the agent's `bt/` next to the restored `tests/` and `pytest.ini`, so no root `conftest.py` can
     exist in the copy. pytest loads no `conftest.py` from `bt/`, which is not an ancestor of `tests/`, so
     `--confcutdir` closes nothing here and was not added.
   - The other route stays open: code in `bt/__init__.py` runs inside the inner pytest and can rewrite its report.
     The cross-job fix is X1 (b) to (d) of the review: a source scan, a third integrity probe and a note in
     AGENTS.md. It is left to the harness.
6. **No visible change but the note's sentence.** The room's tests, data and golden files, the example and its
   expected output are as in 0.1.0.

## Changed at the gate review (T16 0.1.2, 23 Nov 2026)

Four made-up tickers were real ones. A screen of every job's names found them; each was renamed in `generate.py`,
which then rewrote the sample prices, the golden files, the example's prices and expected report, the original
bundle and the hidden cases.

| Was | Now | Where | Why |
|---|---|---|---|
| DUNE | DUQX | the hidden data's pinned takeover target; an exclusion list | Dune Acquisition Corp's Nasdaq ticker |
| LUMO | LUQV | the example's prices | Lumos Pharma's Nasdaq ticker (delisted) |
| MIRA | MIQZ | the example's prices | MIRA Pharmaceuticals' Nasdaq ticker |
| RENO | REQX | the example's prices | Renovare Environmental's OTC ticker |

- **Every order is kept.** The price files' columns follow the generator's lists, which stay alphabetical by first
  letter. The ranking breaks ties by symbol. Each new ticker keeps its old first letter and its four letters, and no
  other ticker in the same price file starts with that letter, so every comparison between two symbols, every tie
  and every column width comes out as before.
- **Nothing else changed.** Every price, setting, case, check and wrong solution is as before. Each committed file,
  with the four renames applied, equals the regenerated one, and the generator's proofs pass with the same counts.
- **Kept:** the other tickers, and the AAA, IDX and SWAY placeholders (judged low risk).
