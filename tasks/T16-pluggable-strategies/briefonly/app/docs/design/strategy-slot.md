# The strategy slot

Status: agreed by the quant lead, risk and operations; built (`bt/strategies/`, and `bt/signals/slot.py` for the
engine's side; see CHANGES.md). Owner: the quant lead.

## Why

A signal type is special-cased all over `bt` today: its parameter list and checks, its warm-up, its scoring, its
echo in the report and its line in the summary each sit in a different module, behind an `if` on `signal.type`
(`docs/ARCHITECTURE.md`, "Adding a signal type", lists most of them). The desk wants new strategies without
touching the engine. Several are being written against this note already, by people who will not read the
engine, so the slot must accept any strategy that follows this note and needs nothing more.

## The slot, from the strategy's side

**Where.** A strategy is a module `bt/strategies/<type>.py`. The config's `signal.type` selects it, as it selects a
signal today: the file's name without `.py` is the type (a Python identifier). A new strategy is that one file:
no change to the engine and no list to add it to.

**What it defines.** Three names. A strategy may define others for its own use; one that defines only these
three must work.

- `PARAMETERS`: a dict of its parameters' names and their defaults, in order, for example
  `PARAMETERS = {"days": 40, "neutral": 0.1}`.
- `warmup(params)`: how far back it looks, as a whole number of days. The engine first rebalances on the day with
  index max(warmup(params), `vol_window`), the run's first day being day 0, and never earlier, so on its first
  score the history holds at least warmup(params) + 1 closes. Momentum's warm-up is its `lookback` and
  reversion's is its `window`: exactly the days the engine works out for them today.
- `score(history, params)`: a dict that gives every symbol in `history` a score, a number (int or float) or
  `None`.

**`params`** is a dict holding every name in `PARAMETERS`, in that order: the config's value where the `signal`
section gives one, the default otherwise. It does not hold `type`. The engine fills in the defaults, so a strategy
can rely on every one of its parameters being there.

**`history`** maps each symbol the engine trades, in the price file's order, to the list of its closes from the
run's first day up to and including today, oldest first. The symbols are every column of the price file except
the benchmark column, when the config names one (the benchmark is split off before the engine sees the prices);
symbols on the `exclude` list are in `history` like any other, and are left out after scoring. The run's first
day is the price file's first day, or the first day of the `--start` window. The closes are forward-filled as the
engine fills them today (at most `max_fill_gap` days); a close that is still missing (before the stock's first
price, or beyond the fill gap) is `None`. So `history[symbol][-1]` is today's close, and every list's length is
today's index plus one.

**Scores.** A positive score is a reason to be long and, where `allow_short` is set, a negative one a reason to be
short; 0 is neither. `None` leaves the symbol out of the ranking, as today. A symbol with no close today is left
out whatever it scores.

**What a strategy may use.** The standard library and its two arguments. It receives no portfolio state (no
positions, cash, NAV or other settings), keeps nothing between calls and changes neither argument. The engine may
call `warmup` and `score` as often as it needs.

## What the engine does around it

- **Finding the strategy.** The engine looks the module up by `signal.type`. A type with no module is refused with
  today's message, `unknown signal type 'carry'` (the type as Python's `repr` writes it, so a config without a
  type gets `unknown signal type None`), after the config's path as every config message has it.
- **Parameters.** The engine fills in the defaults, and refuses a parameter that the strategy's `PARAMETERS` does
  not name with today's message, `signal: <type> has no parameter '<name>'`, for the first such key in the
  config's order. The two built-in strategies keep every check they have on their values, with today's messages
  (`bt/config/signal_params.py`).
- **When.** All of this happens where the signal is checked today: after the check for unknown settings and
  before every other setting (`bt/config/validate.py` lists the order). A config with two problems reports the
  same one as today.
- **After scoring**, everything works as it does today: the exclusion list, the minimum history, the price floor,
  the ranking, the weight cap, the volatility scaling, the drawdown control, the turnover cap, the rebalancing
  schedule and band, the costs, the forced exits, the stop losses, the interest and the trade log.
- **The echo.** The report shows the signal as `type`, then every parameter in `PARAMETERS` order, defaults filled
  in. The summary's strategy line reads `Strategy: <type> (<name> <value>, <name> <value>, ...)` in the same order,
  each value written as Python's `str` writes it, as the summary writes the built-ins' today
  (`Strategy: reversion (window 20, entry_z 1.0)`).
- **No names.** Apart from the default of `signal.type` (`momentum`, the README's default config), the engine names
  no strategy. Momentum and reversion become strategies like any other, in `bt/strategies/`.

## What does not change

Everything `bt` prints and writes, for every input: the report, the summary, the HTML page, the equity curve, the
trade log, the warnings, the error messages and the exit statuses. The tests in `tests/` keep passing as they are.

## The example

`examples/strategies/channel.py` is a strategy written for this slot, and `examples/README.md` says how to run it.
`examples/expected/` holds what the desk's prototype of the slot printed for it, so a build of the slot can be
checked against it byte for byte.
