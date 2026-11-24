# Risk notes

How the desk measures risk, and the choices behind folio's risk numbers. The code is the authority on
everything folio already prints; these notes say what the numbers mean, and how anything new is to be
measured so that it agrees with them.

## The series behind every risk figure

Every risk figure is measured on today's holdings revalued at historical prices and FX (`calc/returns.py`):
"what would today's portfolio have done?". Trades never show up as jumps, and a holding bought last week
counts with its whole price history.

The window is the last `risk.var_lookback_days` daily returns, the same window for volatility, VaR,
expected shortfall and anything that splits them. With fewer daily returns than `risk.min_observations`,
folio refuses the figure rather than guess.

A daily return is simple: the day's NAV over the previous day's, minus one. `folio risk` annualises its
volatility from log returns of the same series. Anything that splits a risk figure works on the simple
returns instead, because P&L adds up and logs do not.

## Splitting a risk figure by line

To say where a risk figure comes from, it is split over the lines of the portfolio: every position, and
every cash balance as a line of its own (a balance in a foreign currency moves with its exchange rate; one
in the base currency never moves).

A line's daily P&L share is its P&L from one day to the next as a share of the previous day's NAV. On every
day the lines' shares add up to the portfolio's simple return. Splits work from these shares, never from
today's weights times each line's return: weights drift over the window, and the P&L shares are what the
portfolio actually did. `folio risk --by` splits expected shortfall this way (`tail_losses()` in
`calc/risk.py` averages each group's P&L shares over the tail days).

## Shares of volatility

Volatility is split with the Euler allocation of volatility, applied to the daily P&L shares over the
window above. A line's share of volatility is a fraction of the portfolio's volatility, so annualisation
does not come into it, and the shares of all lines, cash included, add up to 100%. A line that moves
against the rest of the book has a negative share: it takes risk away.

- Volatility is measured about the mean of the window's returns, as in `folio risk`. Estimates over the
  window may divide by the number of returns or by one less. Use the same divisor for every figure in the
  split: it cancels out of the shares.
- A group's share (a sector, say) is the sum of its lines' shares. Cash is in no sector: as in the sector
  report, a breakdown by sector shows it as a `Cash` row of its own.
- Limits by name follow the `name_share` limit: a name is an issuer, so a company's shares and its bonds
  count together. Cash is not a name.
