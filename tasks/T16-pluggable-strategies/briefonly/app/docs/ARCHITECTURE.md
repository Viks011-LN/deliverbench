# Architecture

How `bt` is put together. The README says how to run it and what every setting does.

## The modules

| Module | What it does |
|---|---|
| `bt/cli.py` | the command line: reads the inputs, runs, prints; turns a `BacktestError` into `error: ...` and exit status 2 |
| `bt/config/` | `defaults.py` (every setting and its default), `loader.py` (JSON), `validate.py` (the checks, in a fixed order), `signal_params.py` (the `signal` section: the strategy it names, unknown parameters, and the strategy's own checks on the values) |
| `bt/data/` | `prices.py` (the price file), `series.py` (forward fill, returns), `window.py` (`--start`/`--end`), `benchmark.py` (splits off the benchmark column), `calendar.py` (week and month tests), `quality.py` (gap warnings) |
| `bt/strategies/` | the strategies, one module per signal type (`momentum.py`, `reversion.py`): `docs/design/strategy-slot.md` and `docs/strategies.md` |
| `bt/signals/` | the scoring: `slot.py` is the engine's side of the strategy slot (finds the strategy that `signal.type` names, fills in its parameters, hands it the history); `compute_scores()` in `__init__.py` scores a day with it; `momentum.py` and `reversion.py` keep the older per-series calls on the strategies' arithmetic, and `stats.py` the rolling mean and standard deviation of prices by index |
| `bt/portfolio/` | `turnover.py` (the turnover cap), `ranking.py` (exclusions, minimum history, price floor, scores to weights), `caps.py` (weight cap), `volatility.py` (each name's volatility, the volatility scale), `drawdown.py` (drawdown control), `schedule.py` (rebalancing days), `targets.py` (weights to units) |
| `bt/execution/` | `book.py` (cash, units, P&L, statistics, interest, the trade log), `costs.py`, `borrow.py`, `exits.py` (forced exits) |
| `bt/engine.py` | the day loop, and the warm-up |
| `bt/metrics/` | the summary metrics: returns, drawdown, ratios, monthly and yearly returns; `benchmark.py` (the book against its benchmark), `drawdowns.py` (drawdown periods), `holding.py` (positions, from the trade log) |
| `bt/report/` | `json_report.py` (the report), `equity.py` (the equity curve), `trades.py` (the trade log), `summary.py`, `formatting.py` and `calendar_grid.py` (the text summary), `html.py` (the HTML page) |
| `bt/legacy/` | the 2021 runner, kept for the reconciliation test only, and the 3.x config layout |
| `bt/tools/` | the desk's tools (`docs/tools.md`); nothing in the engine uses them |

## The day loop

Before the loop, `bt/cli.py` applies the window and splits off the benchmark column, so the engine sees only the
columns it trades. `run_backtest()` forward-fills the prices (at most `max_fill_gap` days) and works out each
name's daily returns, then goes through the days in order. Each day:

1. **Mark.** The day's profit and loss is booked at the close. A held name whose price is missing beyond the fill
   gap is sold at its last price, with costs: a forced exit. With a `stop_loss`, a position that has lost that
   fraction of its entry price is closed at the close: a stop loss.
2. **Interest and borrow.** From the second day on, the cash earns (or pays) a day of `cash_rate`. Shorts pay the
   day's borrow fee.
3. **Value.** The NAV before trading; the high-water mark and the drawdown are updated.
4. **Rebalance**, on the first day after the warm-up and then on the schedule:
   1. the strategy scores every name (`strategy_scores` in `bt/signals/slot.py`; `compute_scores` does the same
      for one day from the config's `signal`): its `score()` gets each name's forward-filled closes from the
      run's first day to today; a name with no price today scores None;
   2. names on the `exclude` list, then names with less than `min_history` of prices, then names under
      `min_price`, are left out;
   3. the scores become weights (`scores_to_weights`), then the weight cap applies;
   4. each held name's volatility over `vol_window` days of returns, and the volatility scale;
   5. the drawdown control;
   6. every name with a price today gets its target units; with a `max_turnover`, the trades are cut to fit
      (`bt/portfolio/turnover.py`); each name is traded to its target, unless the trade is inside the band, and
      each trade goes into the trade log.
5. **Close.** The book is valued again for the equity curve.

The warm-up: the first rebalancing day is the day with index max(strategy warm-up, `vol_window`), the run's first
day being day 0. The strategy's warm-up is its `warmup(params)`: momentum's `lookback` and reversion's `window`.

## Numbers

Plain Python floats, added up in a fixed order. There are three standard deviations in the code and they are not
interchangeable: `bt/strategies/reversion.py` (prices, for reversion: mean by `sum()`, then the squares oldest
first; `bt/signals/stats.py` has the same by index),
`bt/portfolio/volatility.py` (returns, for the volatility scale: newest first, as the risk desk's spreadsheet
does) and `bt/metrics/returns.py` (the run's daily returns, which `bt/metrics/benchmark.py` also uses for its
covariances). Each one's order of adding is what the golden files were made with. `bt.tools.compare` with no
tolerance tells whether two reports agree to the last digit.

## Adding a signal type

A new signal type is a strategy: one file, `bt/strategies/<type>.py`, that defines `PARAMETERS`, `warmup(params)`
and `score(history, params)` (`docs/design/strategy-slot.md`). Nothing else changes: the config check, the
warm-up, the scoring, the echo in the report and the line in the summary all go through the strategy slot
(`bt/signals/slot.py`), and no part of the engine names a strategy. A strategy may also define
`check_parameters(params)` to refuse values it cannot use (`docs/strategies.md`).
