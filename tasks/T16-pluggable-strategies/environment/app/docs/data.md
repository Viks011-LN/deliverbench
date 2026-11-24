# The price file

## Layout

A CSV file: a header `date,SYM1,SYM2,...`, then one row per trading day, oldest first. Dates are `YYYY-MM-DD` and
must increase; every row has a cell for every column. A blank cell is a missing price (the stock was not listed
yet, was suspended, or did not trade); a blank line is skipped. Prices must be positive. Cells may be quoted. At
least two days are needed.

The program does not know about holidays: a day is a trading day when it has a row. Weeks and months are
calendar weeks (ISO week numbers) and calendar months of those rows' dates (`bt/data/calendar.py`).

## What the engine does with it

1. `--start` and `--end` keep the rows between them, both included. The run's first day is the first row kept.
2. With a `benchmark`, its column is set aside: it is never scored or traded, and only the report uses it.
3. Each remaining column is forward-filled: a missing price takes the last price before it, for at most
   `max_fill_gap` days in a row. Before a stock's first price nothing is filled; beyond the fill gap the price
   stays missing until the next real one.
4. Day-on-day returns are taken from the filled prices; a return is missing where either day's price is.

A held stock whose price is missing beyond the fill gap is sold at its last price (a forced exit). Stocks with no
price today are not scored, ranked or traded that day.

## Warnings

Before a run, `bt` writes a `warning: ...` line on stderr for each traded column with no price at all in the
period, and for each run of missing prices after a stock's first price that is longer than `max_fill_gap`:

    warning: GARN has no price from 2024-10-08 to 2024-10-18 (9 days, more than max_fill_gap)

They are information for the desk; the run goes on. `python -m bt.tools.prices_info` shows the same gaps, and
more, before a file is used.

## Where the files come from

The nightly price file is built by the data team from the exchange's closing prices; the desk's sample files in
`tests/data/` and `examples/` are made-up data with the same layout.
