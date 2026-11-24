# The metrics

What every figure in the report means. The daily return of the book on day *i* is NAV(i) / NAV(i-1) - 1, so a run
of *n* days has *n* - 1 daily returns. A year is 252 trading days. Sums run over the days oldest first.

## `metrics`

| Field | Meaning |
|---|---|
| `total_return` | the last NAV over the first, less 1 |
| `annual_return` | the mean daily return times 252 |
| `annual_volatility` | the sample standard deviation of the daily returns times the square root of 252; null with fewer than two returns |
| `sharpe` | the mean daily excess return (over `risk_free_rate` / 252) over its sample standard deviation, times the square root of 252; null with fewer than two returns or no variation |
| `sortino` | like `sharpe`, but the risk is the root mean square of the shortfalls below `risk_free_rate` / 252, over all days; null when no day falls short |
| `max_drawdown` | the worst fall from a previous high, a negative fraction (0 if the NAV never fell) |
| `calmar` | `annual_return` over the size of `max_drawdown`; null if the NAV never fell |
| `hit_rate` | days up over days up or down; flat days count as neither; null if every day was flat |
| `best_day`, `worst_day` | the largest and smallest daily return |
| `average_gross`, `average_net` | the mean over all days of the gross and the net exposure, as fractions of the NAV |
| `average_holdings` | the mean over all days of how many names were held, long or short |
| `turnover` | the traded notional over the mean NAV, per year (over the run's length in years of 252 days) |
| `trades`, `forced_exits`, `stop_losses` | how many trades, and how many of them were forced exits and stop losses |
| `commissions`, `slippage`, `borrow_fees` | what each cost came to over the run |
| `interest` | the interest the cash earned (negative: paid) over the run |

## `benchmark`

Only when the config names a benchmark column. The benchmark's closes are forward-filled as the stocks' are (at
most `max_fill_gap` days); its daily returns are paired with the book's on the days the benchmark has one.

| Field | Meaning |
|---|---|
| `symbol` | the benchmark column |
| `total_return` | the benchmark's last close in the period over its first, less 1 (null with fewer than two closes) |
| `excess_return` | the book's `total_return` less the benchmark's |
| `beta` | the sample covariance of the paired returns over the benchmark's sample variance; null with fewer than two pairs or a flat benchmark |
| `correlation` | the sample covariance over the product of the two sample standard deviations |
| `tracking_error` | the sample standard deviation of the book's return less the benchmark's, times the square root of 252; null if it is 0 |
| `information_ratio` | the mean of that difference times 252, over the tracking error |
| `up_capture`, `down_capture` | on the days the benchmark rose (fell): the book's mean return over the benchmark's |
| `days` | how many paired days there are |

## `drawdowns`

The three deepest drawdown periods, deepest first. A period starts at the last high before the NAV falls; its
trough is the lowest NAV before the NAV gets back to that high; it ends on the first day the NAV is at or above
the high again (`recovery`, null if it has not). `depth` is the trough over the high, less 1, and `days` counts the
trading days from the high to the recovery (or to the last day).

## `positions`

From the trade log. A position opens with a trade from no units and closes with a trade to none (a rebalance, a
forced exit or a stop loss); a trade to the other side keeps it open. `opened`, `closed` and `still_open` count
them; `average_days_held` is the mean of the closed ones' trading days from open to close (null if none closed),
and `longest_held` the first closed position with the most days (null if none).

## `monthly_returns`, `yearly_returns`

Per calendar month ("YYYY-MM") and year ("YYYY"): the product of the daily NAV ratios of the days in it, less 1.
The run's first day only sets the starting NAV of its month.

## `pnl_by_symbol`, `final_positions`

Profit and loss per traded symbol, net of its commission, slippage and borrow; and the positions held on the last
day, with their units, last price, value and weight of the final NAV.
