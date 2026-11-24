# The signals

The two signals the desk runs today, as the engine computes them. `signal.type` selects one; the README lists
their parameters and defaults. Each is a strategy, a module of its own in `bt/strategies/`, written for the
strategy slot (`docs/design/strategy-slot.md`) like any other.

## Momentum (`momentum`)

Buy what has risen. A stock's score on day *t* is its return from `lookback` days before *t* to `skip` days
before *t*:

    score = close[t - skip] / close[t - lookback] - 1

Skipping the last few days avoids the short-term reversal effect, which works against momentum over a week or
two. The score is missing when either close is. Momentum needs `lookback` days of prices before its first score.

The code: `bt/strategies/momentum.py`. `bt/signals/momentum.py` keeps the older call `momentum_score(series, t,
lookback, skip)` on the same arithmetic (the 2021 runner uses it); its constants `LOOKBACK` and `SKIP` predate the
strategy's `PARAMETERS`, and the defaults the program uses and shows are the README's.

## Mean reversion (`reversion`)

Buy what is cheap against its own recent average, sell what is dear. Over the last `window` closes (today's
included), with their mean and their sample standard deviation:

    z = (close[t] - mean) / standard deviation
    score = -z, or 0 when |z| < entry_z

A stock far below its average scores high. Inside the entry band the score is 0, which keeps the stock out of
the book (a score of 0 is neither long nor short). The score is missing when a close in the window is missing,
and when the price did not move at all over the window. Reversion needs `window` days of prices before its first
score.

The code: `bt/strategies/reversion.py`. The mean is taken with Python's `sum()`, then the squares are added up
oldest first: that is the arithmetic the golden files were made with (`bt/signals/stats.py` has the same
statistics by index). `bt/signals/reversion.py` keeps the older call `reversion_score(series, t, window,
entry_z)`; its constants `WINDOW` and `ENTRY_Z` predate the strategy's `PARAMETERS`, and the defaults the program
uses and shows are the README's (`entry_z` 1.0).

## From scores to a book

Whatever the signal, the engine then ranks the scores: the `top_n` highest positive scores are bought, each in
proportion to its score, and with `allow_short` the `top_n` most negative are shorted the same way, half the book
on each side. The weight cap, the volatility target, the drawdown control and the turnover cap come after
(`docs/ARCHITECTURE.md`, the day loop).

## A new signal

A new signal is a new strategy: one file, `bt/strategies/<type>.py`, with no change to the engine.
`docs/design/strategy-slot.md` says what it defines (`PARAMETERS`, `warmup(params)`, `score(history, params)`)
and what the engine does around it; `examples/strategies/channel.py` is one, and `examples/README.md` says how to
try it.

Optionally, a strategy may also define `check_parameters(params)`, to refuse values it cannot use: it gets the
same `params` as `score()` and returns None when they are fine, or the problem, which the config check reports
after the config's path, as `error: <path>: <problem>` with exit status 2. It runs after the check for unknown
parameters and before every setting outside `signal`. Momentum's and reversion's checks are theirs
(`signal.lookback must be a whole number of at least 2`, and so on: `docs/operations.md`). A strategy without one
gets no checks on its values.
