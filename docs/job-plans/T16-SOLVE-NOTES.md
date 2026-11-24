# t16: Make strategies pluggable — solve notes

## What I changed, and why

The slot is built as `docs/design/strategy-slot.md` describes. A strategy is one file, `bt/strategies/<type>.py`,
that defines `PARAMETERS`, `warmup(params)` and `score(history, params)`. The config's `signal.type` picks it up,
with no change to the engine and no list to add it to.

New files:

- `bt/strategies/__init__.py`: the package that holds the strategies. It contains only a docstring, on purpose.
  An imported submodule becomes an attribute of its package, so any function defined here could clash with a
  strategy's name (a strategy called `find_strategy.py` would overwrite it).
- `bt/strategies/momentum.py` and `bt/strategies/reversion.py`: the two built-ins, now strategies like any other.
  They use only the standard library and do the same arithmetic in the same order as before (reversion: mean by
  `sum()`, then the squares oldest first). Their `PARAMETERS` are the README's defaults:
  `{"lookback": 60, "skip": 5}` and `{"window": 20, "entry_z": 1.0}`.
- `bt/signals/slot.py`: the engine's side of the slot.
  - `find_strategy(kind)` returns the module only when `bt/strategies/<kind>.py` exists with exactly that name,
    case included, and `kind` is a string that is a Python identifier other than `__init__`. Anything else
    returns None.
  - `get_strategy(signal)` is the same lookup, but raises `unknown signal type ...` when nothing is found.
  - `parameters(strategy, signal)` builds `params`: every name in `PARAMETERS`, in that order, with the config's
    value or the default. It builds a new dict on every call and leaves out `type`.
  - `strategy_scores(...)` gives `score()` the history: each traded symbol's forward-filled closes from day 0 to
    today, as new lists. Every symbol with no close today then scores None, and so does a symbol the strategy
    leaves out.
- `tests/test_strategy_slot.py`: 26 new tests. The existing tests are untouched. These tests plug a strategy in
  from a temporary folder by extending `bt.strategies.__path__`, so nothing is ever written into `bt/strategies/`.
  They also run the example end to end in-process against `examples/expected/`.

Changed files:

- `bt/config/signal_params.py`: `check_signal` keeps the same order and messages. It checks that the section is
  an object, then that a strategy module exists for the type (otherwise `unknown signal type <repr>`), then for
  unknown parameters in the config's order (checked against `PARAMETERS`), then the values. The value checks
  moved into each built-in's optional `check_parameters(params)`, which returns None or the problem; the engine
  reports it after the config's path. `SIGNAL_TYPES` and `SIGNAL_PARAMETERS` are gone. `signal_parameter()`
  stays, now running through the slot.
- `bt/config/defaults.py`: `SIGNAL_DEFAULTS` removed, because it named the strategies. `DEFAULTS["signal"]` is
  still `{"type": "momentum"}`, the one name the design note allows.
- `bt/engine.py`:
  - The warm-up is `max(strategy.warmup(params), vol_window)`.
  - The strategy is found once per run and passed to `rebalance()`.
  - `first_trading_day(signal, config)` and `warmup_days(signal)` keep their signatures.
- `bt/signals/__init__.py`: `compute_scores(prices, symbols, t, signal)` keeps its signature (the tests use it)
  and now runs through the slot, with no `if` on the type.
- `bt/signals/momentum.py` and `reversion.py`: compatibility modules. `momentum_score` and `reversion_score`
  delegate to the strategies' own helpers, so there is one copy of the arithmetic. They have to stay because
  `tests/test_signals.py` and the 2021 runner (`bt/legacy/runner.py`) import them. `bt/signals/stats.py` is
  unchanged; its tests still cross-check the reversion strategy's numbers to the last bit.
- `bt/report/json_report.py`: the echo is `{"type": ..., **params}` in `PARAMETERS` order.
- `bt/report/summary.py`: the line is `Strategy: <type> (<name> <str(value)>, ...)`.
- Unknown types still fall back as they did before: the echo shows the section as given and the line reads
  `Strategy: <type>`.
- Docs: `README.md` (Signals), `docs/ARCHITECTURE.md` (modules, day loop, "Adding a signal type"),
  `docs/strategies.md` (where the code is now, and the optional `check_parameters` hook), `docs/CHANGES.md` (an
  "Unreleased" entry), and the design note's status line.

Not changed:

- `cli.py`, the data, portfolio, execution and metrics code, the tools and the legacy code.
- The 2021 runner is momentum-only by definition, and `config_v3.py` maps 3.x keys, so both still name strategies.
  `bt.tools.sweep`'s fallback `{"type": "momentum"}` is the default `signal.type`.

One fix along the way: my first build looked the strategy up on every rebalancing day. Each lookup lists the
folder, and on the solver's slow shared drive a listing takes about 15 ms, so the changed copy ran about 4x slower than the
original in the comparison. The engine now looks the strategy up once per run, so a command-line run does about
three lookups. I chose not to cache lookups across calls: a cache could keep serving a deleted strategy, or miss
one added while the program runs.

## How I proved that nothing printed changed

- I kept a pristine copy in `orig/` and never edited it.
- Tests: the 296 existing tests pass unchanged on the new code (Python 3.12, as the README asks; I ran pytest
  through `uv`). With the new file the total is 322.
- A differential harness in `difftest/` (`gen_cases.py`, `run_cases.py`, `compare_runs.py`, `subproc_compare.py`):
  - The same **3421 command lines** go through `orig/` and `app/`, each case in its own working directory.
  - For each case it compares stdout, stderr, the exit status (and the type and message of any uncaught
    exception), and every file written (`equity.csv`, `trades.csv`) byte for byte.
  - Result: **0 differences** over 3421 cases and 3254 written files. On the original's side, 1968 runs finished
    with exit 0, and about 1330 were refusals with exit 2. Those cover every config message (313 `unknown signal
    type`, 127 `has no parameter`, 247 `signal.<name> must be ...`, 155 `unknown setting`, ...) and every
    price-file and window error. The other cases were argparse exits and 120 tool runs.
  - One case crashes in **both** copies, identically, with `ZeroDivisionError: float division by zero`:
    `initial_capital` 100 with `min_commission` 50, so commissions drive the NAV to zero. That bug was already
    there. I left it alone, because fixing it would change what the program prints for that input; it is worth a
    ticket of its own.
- What the cases cover:
  - **2020 random valid configs** on 19 price files. Two are the repo's sample files; 17 are synthetic: from 2 to
    300 days and 1 to 10 columns, with gaps longer and shorter than the fill gap, late listings, an empty column,
    flat (never-moving) columns, holidays, year-end gaps, quoted cells and benchmark columns. Every setting is
    varied, including ints against floats (`entry_z` 1 against 1.0), parameter orders, lookbacks and windows longer
    than the file, `skip` 0 and `lookback - 1`, and random `--start`/`--end` windows. The format is json, text or
    html, with and without `--equity`/`--trades`.
  - **900 broken configs**, each with 1 to 3 faults injected, so the order of the checks is exercised.
  - **183 signal cases**:
    - 35 bad types, each alone and combined with bad parameters and a bad `top_n`. The types include `"carry"`,
      `"Momentum"`, `"MOMENTUM"`, `"momentum "`, `""`, `"__init__"`, `"slot"`, `"stats"`, `"channel"`,
      `"momentum.py"`, `"os"`, `"../momentum"`, `"momentum\u0000"`, `"__pycache__"`, `5`, `1.5`, `true`, `null`,
      `[...]` and `{...}`.
    - A missing `type`, and `signal` that is not an object.
  - **102 hand-made edge configs**, each in all three formats: every setting at once, and the warm-up landing
    exactly at, or one day after, the end of the file.
  - **54 cases with odd JSON**: NaN and ±Infinity in parameters, `1e400`, duplicate keys, trailing commas, a
    non-object, and an empty file.
  - **42 other cases**: 30 bad price files, missing and unwritable files, too-short windows, benchmark errors,
    `--help`, missing arguments and a bad `--format`.
  - **120 tool runs**: `sweep` over `signal.*` values (including `signal.type="carry"`/`"Momentum"`/`null`),
    `batch`, `walkforward`, `settings`, `migrate` and `prices_info`.
- Because the main harness runs in-process, I also ran **501** cases as real `python -m bt` processes against both
  copies: all 381 hand-made `bt` cases plus 120 random ones. It compared exit status, stdout, stderr and the files
  written. **0 differences.**
- All of the above ran on the final code. Where the harness lives:
  - the scripts: `difftest/*.py`;
  - the generated inputs: `difftest/cases/`;
  - each copy's outputs: `difftest/out_orig/`, `difftest/out_app/` and `difftest/out_sub/`.

## The example strategy's result

`examples/strategies/channel.py` was copied into `bt/strategies/` of a scratch copy of `app/` (`exrun/`, deleted
afterwards) and run with the two commands in `examples/README.md`:

- stdout of the first command equals `examples/expected/report.json` byte for byte;
- the equity curve it writes equals `examples/expected/equity.csv`;
- the `--format text` stdout equals `examples/expected/summary.txt`;
- nothing is printed on stderr, and both exit 0.

The run: 2025-02-03 to 2025-11-28 (215 days), `Strategy: channel (days 30, neutral 0.15)`, total return 4.28%,
Sharpe 0.47, max drawdown -11.05%, 247 trades, final NAV 1,042,799.47. `tests/test_strategy_slot.py` repeats this
check in-process.

## What I assumed

- I assumed the example must **not** be left installed in `bt/strategies/`. With `channel.py` there, a config
  with `signal.type "channel"` would run instead of failing with `unknown signal type 'channel'`, which changes
  what the program prints for that input. The example README itself says "copy it into `bt/strategies/`" to try
  it. A test checks it stays uninstalled.
- I assumed the built-ins' value checks belong in the strategies, since the note says the engine names no
  strategy. I added an **optional** hook, `check_parameters(params)`, which returns None or the message after the
  path. It is documented in `docs/strategies.md`. A strategy that defines only the three names works and gets no
  value checks; for channel, `"days": "x"` would then fail at run time with a traceback.
- I assumed the type must match the file name **exactly, case included**, even on file systems that ignore case,
  so `"Momentum"` stays `unknown signal type 'Momentum'`. Only `.py` files directly in `bt/strategies/` count, and
  `__init__` is excluded.
- I assumed that when a strategy leaves a symbol out of its returned dict, that symbol has no score (None). The
  note says `score` gives every symbol a score; I chose to be lenient rather than crash.
- I assumed that a strategy with an empty `PARAMETERS` gets the summary line `Strategy: <type>`, with no empty
  `()`. That is the fallback form the summary already used.
- I assumed the built-in strategies should use only the standard library, like any other strategy ("What a
  strategy may use"), so the arithmetic lives in them and the old `bt/signals` functions delegate to them.
- I assumed code that calls `run_backtest` directly with a type that has no module may now fail at the start of
  the run (`BacktestError: unknown signal type ...`) rather than on the first scoring day. The command line and
  every tool refuse such a config before the engine runs, so nothing printed changes.
- I assumed the version number stays as it is. `bt/__init__.py` says 4.7.2 while `CHANGES.md` already lists 4.7.3;
  that mismatch was there before me. I added an "Unreleased" entry instead.

## What was ambiguous

- The summary format for a strategy with no parameters (see above).
- Whether a strategy that leaves out a symbol is an error (see above).
- Where the built-ins' checks go. "keep every check they have ... (bt/config/signal_params.py)" next to "the
  engine names no strategy" leaves only a hook, and the note does not name one.
- "The engine names no strategy" against the old modules the tests import (`bt.signals.momentum`,
  `bt.signals.reversion`). I kept them as thin compatibility modules that the engine never imports.
- The README asks for Python 3.12, but the machine's `python3` is 3.14. I ran everything on 3.12 through `uv`.

## What looked like a trap

- **`entry_z`'s default.** The old module constant is `ENTRY_Z = 1` (an int); the README and `SIGNAL_DEFAULTS`
  say `1.0`. Taking the constant would print `entry_z 1` and `"entry_z": 1`, which breaks the golden output. The
  strategy uses `1.0`.
- **Installing the example.** "Copy it into `bt/strategies/`" collides with "nothing printed may change, for any
  input" (see above).
- **Finding modules by name.**
  - `"__init__"` would import the package's own `__init__.py` as a strategy.
  - On a case-insensitive disk, a naive file check accepts `"Momentum"`.
  - Non-string types (`5`, `null`, lists, dicts) must still give `unknown signal type <repr>`. A lookup in a dict
    or set would crash on a dict type, because a dict is unhashable.
- **The order of the checks.** An unknown setting is still reported before a bad signal. Within the signal, the
  order is: the section, the type, unknown parameters in the config's order, then the values (lookback before
  skip, window before entry_z). The broken-config cases pin this down.
- **The config must not be changed.** `load_config` must keep the `signal` section exactly as given, with no
  defaults filled in (`test_defaults_are_filled_in` asserts `config == DEFAULTS`). The defaults are filled in
  only where they are used.
- **Names defined in the strategies package** would clash with strategy module names (see `__init__.py` above).
- **A lookup on every rebalancing day** was slow on a slow disk (see above). The comparison run's timing showed
  it.
- **Residual risk:** a third-party strategy that happens to define its own `check_parameters` with a different
  meaning would have it called by the config check. The name was chosen to make that unlikely, and it is
  documented.
