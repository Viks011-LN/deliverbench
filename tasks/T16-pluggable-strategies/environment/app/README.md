# bt: the desk's backtest

`bt` simulates a cross-sectional equity strategy on daily closing prices: every rebalancing day it scores each
stock with the configured signal, holds the best (and, if allowed, shorts the worst), and books the costs. It
prints a JSON report, or a one-page text summary, and can write the daily equity curve.

Standard library only (Python 3.12). The design of the code is in `docs/ARCHITECTURE.md`; design notes for work
in progress are in `docs/design/`.

## Running it

From the repo root:

    python -m bt --prices tests/data/prices.csv --config tests/data/momentum.json
    python -m bt --prices P.csv --config C.json --equity equity.csv --start 2024-03-01 --end 2024-09-30
    python -m bt --prices P.csv --config C.json --format text

| Option | Meaning |
|---|---|
| `--prices FILE` | the price file (required) |
| `--config FILE` | the config file (required) |
| `--equity FILE` | also write the daily equity curve to this CSV file |
| `--trades FILE` | also write the trade log to this CSV file |
| `--start YYYY-MM-DD` | first day to use; earlier days are dropped before anything else happens |
| `--end YYYY-MM-DD` | last day to use |
| `--format json\|text\|html` | `json` (the default): the full report; `text`: the one-page summary; `html`: the summary as a web page, with a chart of the NAV |

- **Prices**: a CSV with a `date` column (YYYY-MM-DD, oldest first) and one column per stock. A blank cell is a
  missing price; a blank line is skipped.
- **Output**: the report (or the summary) on stdout. Gaps in the prices longer than `max_fill_gap` are reported on
  stderr as `warning: ...` lines before the run (for the traded columns, not the benchmark); they do not stop it.
- **Equity curve** (`--equity`): `date,nav,cash,gross,net`, one line per day. **Trade log** (`--trades`):
  `date,symbol,side,units,price,notional,commission,slippage,reason`, one line per trade in the order they were
  made; `units` is signed and `reason` is `rebalance` or `forced exit`. Numbers in both are written in full.
- **Problems with the inputs** (a bad price file, a bad config, a window of fewer than two days, a file that
  cannot be opened, a benchmark that is not a column) are reported on stderr as `error: ...`, with exit status 2.
  Nothing is then printed on stdout and no file is written. `docs/operations.md` lists the messages.

## The config file

A JSON object. Every setting is optional; an unknown key is an error, so a typo cannot pass silently. The
settings are checked in a fixed order and the first problem is reported (see `bt/config/validate.py`).

| Setting | Default | Meaning |
|---|---|---|
| `initial_capital` | `1000000.0` | the starting cash |
| `signal` | `{"type": "momentum"}` | the signal: `type` selects it, and the section may give any of its parameters (below) |
| `top_n` | `3` | how many names to hold on each side |
| `allow_short` | `false` | also short the `top_n` most negative scores; each side is then half the book |
| `max_weight` | `0.4` | the most any one name may weigh, as a fraction of the NAV; the excess goes to the others on its side |
| `min_price` | `0.0` | names whose price today is below this are left out of the ranking (0: no floor) |
| `min_history` | `0` | names with fewer prices than this in the run so far (counted from their first price, today's included) are left out of the ranking |
| `exclude` | `[]` | symbols never held (a restricted list); they are scored like any other and left out of the ranking; symbols the price file does not have are ignored |
| `rebalance` | `"monthly"` | `daily`, `weekly` (the first trading day of a new week) or `monthly` (the first trading day of a new month) |
| `rebalance_band` | `0.0` | trades smaller than this fraction of the NAV are skipped |
| `vol_target` | `null` | target annual volatility of the book; `null` for none |
| `vol_window` | `20` | days of returns for each name's volatility |
| `max_leverage` | `1.5` | the most the volatility target may scale the book up |
| `drawdown_limit` | `null` | when the NAV is this far below its high, the book is cut; `null` for no control |
| `drawdown_scale` | `0.5` | what the book is multiplied by while the drawdown control is on |
| `stop_loss` | `null` | a position that has lost this fraction of its entry price at a day's close is closed at that close (a stop loss); `null` for none |
| `max_turnover` | `null` | the most one rebalancing may trade, as a fraction of the NAV; beyond it every trade is cut by the same factor; `null` for no cap |
| `commission_bps` | `5.0` | commission, in basis points of the traded notional |
| `min_commission` | `0.0` | the smallest commission charged on a trade |
| `slippage_bps` | `2.0` | slippage, in basis points of the traded notional |
| `borrow_bps` | `50.0` | the yearly fee on shorts, in basis points of their market value, charged daily (252 days a year) |
| `cash_rate` | `0.0` | yearly interest on the cash balance, paid (or, on a negative balance, charged) daily from the second day, 252 days a year; may be negative |
| `max_fill_gap` | `5` | a missing price is carried forward for at most this many days; a held name missing for longer is sold at its last price (a forced exit) |
| `benchmark` | `null` | a column of the price file that is the benchmark, not a stock: it is never scored or traded, and the report compares the book with it |
| `risk_free_rate` | `0.0` | yearly, for the Sharpe and Sortino ratios |

### Signals

| `signal.type` | Parameter | Default | Meaning |
|---|---|---|---|
| `momentum` | `lookback` | `60` | the return from `lookback` days ago... |
| | `skip` | `5` | ...to `skip` days ago (skipping the last days avoids short-term reversal) |
| `reversion` | `window` | `20` | minus the z-score of today's price against the mean of the last `window` prices |
| | `entry_z` | `1.0` | inside the band \|z\| < `entry_z` the score is 0 |

A positive score is a reason to be long; with `allow_short`, a negative one a reason to be short. Momentum needs
`lookback` days of prices before its first score and reversion `window` days; nothing is traded before that, nor
before `vol_window` days of returns.

## Outputs

The JSON report's sections, in order: `period`, `capital`, `strategy` (every setting that shapes the book, the
signal with its parameters' defaults filled in), `costs`, `metrics`, `benchmark` (only with a benchmark),
`drawdowns` (the three worst), `positions` (opened, closed, days held), `monthly_returns`, `yearly_returns`, `pnl_by_symbol`, `final_positions`.
`docs/metrics.md` defines every figure. The text summary shows the same run rounded for reading, with the worst
drawdowns and a calendar of monthly returns.

## Conventions

- Trades happen at the close, at the close price, after the day's profit and loss has been booked.
- Weights are fractions of the NAV at the moment of the trade; long-only books add up to 1, long-short books
  have half the NAV on each side (before the weight cap and the scaling).
- Costs are commission and slippage in basis points of the traded notional; shorts also pay a daily borrow fee.
- Every number in the JSON report and the equity curve is written in full, so two runs can be compared byte for
  byte. The arithmetic is plain floats in a fixed order: the golden files depend on it.

## Tools

`python -m bt.tools.compare A.json B.json` shows what differs between two reports. `bt.tools.prices_info`,
`bt.tools.sweep`, `bt.tools.batch`, `bt.tools.walkforward`, `bt.tools.settings` and `bt.tools.migrate` describe a
price file, sweep one setting, run several configs, run a config year by year, list the settings, and migrate a
3.x config. `docs/tools.md` has the details; `docs/data.md` describes the price file and `docs/strategies.md` the
two signals.

## Tests

    pytest

from the repo root. `tests/golden/` holds the program's output on the sample in `tests/data/`, byte for byte.
`tests/test_legacy.py` keeps the 2021 runner (`bt/legacy/`) in agreement with the engine.
