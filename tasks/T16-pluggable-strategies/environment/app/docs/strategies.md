# The signals

The two signals the desk runs today, as the engine computes them. `signal.type` selects one; the README lists
their parameters and defaults.

## Momentum (`momentum`)

Buy what has risen. A stock's score on day *t* is its return from `lookback` days before *t* to `skip` days
before *t*:

    score = close[t - skip] / close[t - lookback] - 1

Skipping the last few days avoids the short-term reversal effect, which works against momentum over a week or
two. The score is missing when either close is. Momentum needs `lookback` days of prices before its first score.

The code: `bt/signals/momentum.py`. Its constants `LOOKBACK` and `SKIP` predate `SIGNAL_DEFAULTS`; the defaults the
program uses and shows are the README's.

## Mean reversion (`reversion`)

Buy what is cheap against its own recent average, sell what is dear. Over the last `window` closes (today's
included), with their mean and their sample standard deviation:

    z = (close[t] - mean) / standard deviation
    score = -z, or 0 when |z| < entry_z

A stock far below its average scores high. Inside the entry band the score is 0, which keeps the stock out of
the book (a score of 0 is neither long nor short). The score is missing when a close in the window is missing,
and when the price did not move at all over the window. Reversion needs `window` days of prices before its first
score.

The mean is taken with Python's `sum()`, then the squares are added up oldest first (`bt/signals/stats.py`): that
is the arithmetic the golden files were made with. Its constants `WINDOW` and `ENTRY_Z` predate
`SIGNAL_DEFAULTS`; the defaults the program uses and shows are the README's.

## From scores to a book

Whatever the signal, the engine then ranks the scores: the `top_n` highest positive scores are bought, each in
proportion to its score, and with `allow_short` the `top_n` most negative are shorted the same way, half the book
on each side. The weight cap, the volatility target, the drawdown control and the turnover cap come after
(`docs/ARCHITECTURE.md`, the day loop).

## A new signal

Today a new signal is a change to the engine in several places (`docs/ARCHITECTURE.md`, "Adding a signal type").
`docs/design/strategy-slot.md` describes the slot that is to replace that.
