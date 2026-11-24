# Benchmark comparison

The model portfolio is measured against a market index, the Halberd Global
Balanced 60/40 index (code `HGB6040`; the sample is fictional). `python -m
folio.benchmark` shows how the book differs from it: where it is over- or
underweight, how much of it is the index at all, and how far its returns have
strayed and why. It uses the data folder, settings and valuation date of
`folio`, plus two files of its own that the core commands never read. The
code is in `folio/benchmark/`, the tests in `tests/test_benchmark_*.py`.

| Command | What it prints |
|---|---|
| `active [--by DIM]` | active weight of every holding, or of every group (sector, currency, kind...) |
| `tracking [--window DAYS] [--by DIM]` | relative return, tracking error and beta; `--by` adds the allocation/selection split |
| `overlap [--top N]` | active share and the N largest over- and underweights (default 5) |
| `export [-o FILE]` | CSV of active weights, one row per holding |

The common options work as for `folio`, before or after the command:
`--data-dir`, `--as-of`, `--config`, `--set`. `--benchmark FILE` and
`--levels FILE` replace the two files below. `--by` takes the names of
`folio report --by`, including any breakdown added to `calc/exposure.py`
later. Errors print as `folio-benchmark: error: ...` with exit status 2.

## Input files

`benchmark.csv` lists the constituents with their weights as fractions:

    id,weight,name,kind,sector,country,currency
    ADZM,0.0310,,,,,
    ORVL,0.0300,Orvelle Networks Inc,equity,Technology,US,USD

`id` and `weight` are required. Weights must add up to 1 within 0.001
(published weights are rounded) and are then scaled to exactly 1. An id that
instruments.csv knows needs nothing more: instruments.csv is the reference,
and a kind, sector, country or currency here that disagrees gets a note. Other
ids may carry a name, kind, sector, country and currency so they can be
grouped; anything missing is grouped as `Unknown`. Comment rows (`#...`),
blank lines and other columns are ignored. The sample has 53 constituents: 29
the book holds, two it does not (FRXL, NYQV) and 22 that only the index has,
in sectors (Materials, Utilities) and currencies (AUD, CAD, CHF) the book
has none of.

`benchmark_levels.csv` (`date,HGB6040`, then rows such as
`2026-06-01,2150.00`) has the index's daily closing level in the base
currency, normally on the dates of prices.csv, in a column named after the
index. A blank cell or a missing date uses the latest earlier level, as a
price gap does for the book.

## Definitions

* **Active weight**: book weight minus index weight. Book weights are shares
  of NAV, cash included; the index holds no cash, so active weights add up to
  zero. Cash is a row of its own, except by currency, where a balance is
  exposure to its currency, as in `folio report`.
* **Active share**: half the sum of the absolute active weights, cash
  included. 0% is the index itself, 100% nothing in common. *In common* is
  the rest: the sum of the smaller of the two weights, holding by holding.
* **Relative return**: the book's return over the window minus the index's,
  a plain difference. The book's return is that of `folio risk`: today's
  holdings at each day's prices and FX.
* **Tracking error**: the standard deviation of the daily return differences,
  times the square root of `risk.annualisation_days`. The window defaults to
  `risk.var_lookback_days` returns and needs `risk.min_observations`.
  **Beta** is the covariance of book and index returns over the index's variance.
* **Allocation / selection**: a two-way Brinson split of the relative return
  by group, with book weights at the start of the window and index weights
  from benchmark.csv:

      allocation = (book weight - index weight) x (index return in group - index return)
      selection  = book weight x (book return in group - index return in group)

  Interaction counts as selection. A group's index return comes from its
  constituents with prices in prices.csv; unpriced ones are taken to have done
  what the priced ones in their group did, and a group with none priced what
  the whole index did. A group the index lacks (funds, cash) is all allocation.
* **Residual**: allocation plus selection explains the book's return minus
  the index return rebuilt from the constituents. The residual is the gap from
  there to the levels: unpriced names, weights drifting in the window, index
  fees. The more of the index is unpriced, the larger it tends to be.

## Examples on the sample data

    $ python -m folio.benchmark active --by kind --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Active weights by kind against benchmark.csv (53 constituents)
    Kind    Held  In index     Book    Index   Active
    ------  ----  --------  -------  -------  -------
    equity    24        40   54.30%   60.00%   -5.70%
    bond       8        13   23.28%   40.00%  -16.72%
    fund       6         0   19.17%    0.00%  +19.17%
    Cash                      3.25%    0.00%   +3.25%
    ------  ----  --------  -------  -------  -------
    Total     38        53  100.00%  100.00%    0.00%

Without `--by` it lists the 62 instruments held or listed, largest overweight
first, then the cash balances.

    $ python -m folio.benchmark overlap --top 2 --as-of 2026-10-30
    ...
    Active share  48.45%
    In common     51.55%
    Book          38 instruments, 29 of them in the index
    Index         53 constituents, 29 of them held

    Largest overweights
    Instrument  Name                            Kind   Book  Index  Active
    ----------  ------------------------------  ----  -----  -----  ------
    GEIF        Harrow Global Equity Index ...  fund  6.02%  0.00%  +6.02%
    PCRF        Ecclesby Private Credit Fund    fund  3.41%  0.00%  +3.41%

    Largest underweights
    ...
    UST28       US Treasury 4.25% 2028   bond  0.00%  3.80%  -3.80%
    UKT29       UK Treasury 4.125% 2029  bond  0.00%  3.60%  -3.60%

    $ python -m folio.benchmark tracking --by kind --as-of 2026-10-30
    ...
    Tracking against HGB6040
    Window                 2026-08-07 to 2026-10-30, 60 daily returns
    Book return            +7.96%
    Index return           +9.81%
    Relative return        -1.86%
    Tracking error (ann.)  2.78%
    Beta                   0.92
    Worst relative day     -0.45%  2026-09-30
    Best relative day      +0.34%  2026-10-20

    Relative return by kind, 2026-08-07 to 2026-10-30
    Kind    Book wt  Index wt  Book ret  Index ret  Allocation  Selection   Total
    ------  -------  --------  --------  ---------  ----------  ---------  ------
    equity   52.05%    60.00%   +12.63%    +14.94%      -0.41%     -1.21%  -1.61%
    bond     24.36%    40.00%    +3.18%     +2.97%      +1.07%     +0.05%  +1.12%
    fund     20.11%     0.00%    +2.89%                 -1.39%      0.00%  -1.39%
    Cash      3.48%     0.00%    +0.83%                 -0.31%      0.00%  -0.31%
    ------  -------  --------  --------  ---------  ----------  ---------  ------
    Total   100.00%   100.00%    +7.96%    +10.15%      -1.04%     -1.15%  -2.20%

    Allocation + selection  -2.20%
    Residual                +0.34%  (index rebuilt from constituents +10.15%, levels +9.81%; 60.70% of the index priced)
    Relative return         -1.86%

The funds and the equity underweight cost more than the bond underweight
earned, and the book's equities trailed the index's. The total row's index
return is the rebuilt one, so every row reads as book minus index.

`export` writes one row per instrument in id order, then one per cash balance
(`CASH`), with its own columns, separate from `folio export`:
`portfolio, as_of, instrument, name, kind, sector, currency, book_weight,
index_weight, active_weight`. Weights are plain fractions to six decimals:

    GBL-BAL,2026-10-30,ADZM,Adzel Microsystems Inc,equity,Technology,USD,0.042147,0.031000,0.011147
