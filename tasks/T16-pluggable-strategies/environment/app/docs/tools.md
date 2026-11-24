# Tools

Small programs around the backtest, in `bt/tools/`. None of them changes what `python -m bt` does; the engine does
not use them.

## compare

    python -m bt.tools.compare A.json B.json [--tolerance X]

What differs between two JSON reports: one line per difference with the path to it (`metrics.sharpe: 0.61 !=
0.62`, `drawdowns[0].trough: ...`), then the count. Keys must come in the same order, and numbers must be the same
number of the same kind (`1` and `1.0` differ) unless a tolerance is given. Exit status 0 if the reports are the
same, 1 if they differ, 2 if a file cannot be read. `docs/operations.md` says how the desk uses it to check a
change.

## prices_info

    python -m bt.tools.prices_info PRICES.csv [--max-fill-gap N]

One line per symbol: first and last price date, number of prices, days missing after the first price, the longest
gap, the gaps longer than the fill gap (each would force a sale), the last price, and the annualised volatility of
the day-on-day returns. Useful before a new price file goes into the nightly runs.

## sweep

    python -m bt.tools.sweep --prices P.csv --config C.json --set KEY=V1,V2,... [--start D] [--end D]

Runs the config once per value of one setting and prints a line per run: total return, annual volatility,
Sharpe, max drawdown and trades. `KEY` is a setting (`top_n`, `rebalance`) or a parameter of the signal
(`signal.lookback`); values are JSON (`20`, `0.5`, `"weekly"`, `null`). A value the config check refuses shows its
message on its line. The runs are exactly those of `python -m bt` with that one value changed.

## batch

    python -m bt.tools.batch --prices P.csv CONFIG.json [CONFIG.json ...]

One line per config: total return, annual volatility, Sharpe, max drawdown and trades; a config `python -m bt`
would refuse shows its message instead. Exit status 1 if any config was refused.

## walkforward

    python -m bt.tools.walkforward --prices P.csv --config C.json [--min-days N]

The config run separately on each calendar year of the price file (each year from the initial capital, with its
own warm-up), one line per year. Years shorter than `--min-days` (20) are skipped.

## settings

    python -m bt.tools.settings [--json]

Every setting with its default and a line on what it does; with `--json`, the defaults as a config file.

## migrate

    python -m bt.tools.migrate OLD.json

Prints a bt 3.x config (signal named as a string, its parameters at the top level, some settings under their old
names) in today's layout. It does not check the result: run it through `python -m bt` before using it. The 3.x
layout is described in `bt/legacy/config_v3.py`.
