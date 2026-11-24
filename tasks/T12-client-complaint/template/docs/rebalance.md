# Rebalancing proposals

`python -m folio.rebalance` compares the book with its model weights and
proposes the trades that bring it back. It reads the same data folder as
folio, plus two files of its own, and changes nothing: the output is a report
and a trade list for the desk to check before anything is sent.

| Command | What it prints |
|---|---|
| `drift` | each target with its current weight, model weight, band and drift |
| `propose [--cash-buffer SHARE] [--min-ticket AMOUNT]` | the trades, what was left out, cash and weights after |
| `export [--cash-buffer SHARE] [--min-ticket AMOUNT] [-o FILE]` | the trades as CSV, one row per order |

The book is loaded and valued exactly as `folio value` does it, so
`--data-dir`, `--as-of`, `--config` and `--set` mean the same here, before or
after the command. `--targets FILE` and `--rules FILE` replace the two input
files below; folio's own commands never read them. Errors go to standard
error as `folio-rebalance: error: ...`, notes as `folio-rebalance: note: ...`.
Exit status: 0, or 2 for bad input, settings or usage; `drift` exits 0
whatever it finds. The code is in `folio/rebalance/`.

## targets.csv

One row per target. Weights and bands are fractions of NAV, and the weights,
cash included, add up to 1. Lines starting with `#` are comments.

    scope,key,weight,band
    sector,Technology,0.15,0.010
    instrument,GEIF,0.05,0.005
    cash,,0.04,0.010

| Column | Meaning |
|---|---|
| `scope` | `instrument` (one holding), `sector` (every holding in it) or `cash` (all balances) |
| `key` | the instrument id or the sector; empty for cash |
| `weight` | the model weight |
| `band` | how far either way the weight may drift before it trades |

The reader refuses weights that do not add up to 1, instruments and sectors
that instruments.csv does not know, a second row for the same target, a file
without a cash row, and an instrument with its own target inside a sector
that also has one. Every holding must be covered by a target; to sell one
out, give it a weight of 0.

## trading.toml

The dealing rules. Every key is optional.

| Key | Default | Meaning |
|---|---|---|
| `min_ticket` | 0 | trades worth less than this, in the base currency, are left out |
| `cash_buffer` | 0 | share of NAV that must stay in cash after the trades |
| `bonds_in_nominal_multiples` | true | false: bonds deal in any whole amount of nominal |
| `[lots]` | 1 | round lot per kind (`equity`, `bond`, `fund`); bond lots are nominal |
| `[instrument_lots]` | | round lots for single instruments, e.g. `KIWQ = 100` |

The sample file sets a ticket of GBP 25,000, a 1% buffer, bonds in multiples
of 1,000 nominal, Tokyo shares in 100s and the JGB in 1,000,000 of nominal.

## How a proposal is built

1. Only targets outside their band trade (a drift exactly on the band does
   not), and they trade all the way back to the model weight.
2. An instrument target trades that instrument, and may buy one not held
   yet. A sector target is spread over the sector's holdings in proportion
   to their current weights; it never buys a new name.
3. Each trade is rounded to the nearest round lot. A weight of 0 sells the
   whole holding, odd lot and all.
4. Trades under the minimum ticket are left out.
5. Sells come first and pay for the buys. If cash would end below the
   buffer, every buy is cut by the same factor and rounded down to lots.
   Nothing extra is sold to raise cash.

Trades are valued at the valuation's prices and FX rates and costs are left
out, so NAV does not change. Cash moves in each trade's own currency: a
balance that ends below zero needs an FX trade before settlement, which the
report points out but does not propose. The cash target is never traded; it
is where the trades leave cash, shown against its model weight.

## drift

    $ python -m folio.rebalance drift --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Drift from the model weights
    Target       Scope       Holdings    Now  Model  Band  Drift  Status
    -----------  ----------  --------  -----  -----  ----  -----  -------
    Technology   sector             6  16.4%  15.0%  1.0%  +1.4%  outside
    Health Care  sector             3   7.7%   9.0%  1.0%  -1.3%  outside
    Government   sector             6  21.1%  20.0%  1.0%  +1.1%  outside
    GEIF         instrument         1   6.0%   5.0%  0.5%  +1.0%  outside
    JMKF         instrument         1   2.0%   3.0%  0.5%  -1.0%  outside
    Consumer     sector             5   9.7%  10.0%  1.0%  -0.3%
    Financials   sector             6  14.9%  15.0%  1.0%  -0.1%
    Industrials  sector             6  10.9%  11.0%  1.0%  -0.1%
    Energy       sector             4   7.9%   8.0%  1.0%  -0.1%
    Cash         cash                   3.3%   4.0%  1.0%  -0.7%

    5 of 10 targets outside their band.

Largest drift first, cash last. Status is decided on exact weights, so a
drift printed as +0.5% against a band of 0.5% can still be outside.

## propose

    $ python -m folio.rebalance propose --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Proposed trades (minimum ticket GBP 25,000.00, cash buffer 1.0% of NAV)
    Side  Instrument  Kind    Ccy  Quantity    Price  Value (GBP)  Before  After  Target
    ----  ----------  ------  ---  --------  -------  -----------  ------  -----  -----------
    sell  GEIF        fund    GBP    59,382   3.4303   203,698.07    6.0%   5.0%  GEIF
    sell  ADZM        equity  USD       533   185.15    73,982.27    4.2%   3.8%  Technology
    ...
    buy   JMKF        fund    JPY     1,895    20067   197,712.10    2.0%   3.0%  JMKF
    buy   PEBX        equity  USD       797   165.33    98,784.02    3.0%   3.5%  Health Care
    ...

    Sells GBP 685,072.48, buys GBP 451,219.79, net cash +233,852.69; 5.7% of NAV traded.

    Left out
    Instrument  Side   Quantity  Value (GBP)  Target      Reason
    ----------  ----  ---------  -----------  ----------  ------------------------
    JGB30       sell  4,000,000    20,964.04  Government  under the minimum ticket

    Cash after the trades
    ...
    Cash after: 4.4% of NAV (model 4.0%, buffer 1.0%).
    JPY ends below zero: buy it against another currency before the trades settle.

    Weights after the trades
    ...
    Every target is inside its band.

Rows are cut where the example shows `...`. The cash table has a row per
currency (now, sells, buys, after, after in GBP), and the weights after keep
the order of the drift table. With `--cash-buffer 0.05` the buys no longer
fit, and the report adds
`Buys cut to 74.6% of their size to keep 5.0% of NAV in cash.`

## export

    $ python -m folio.rebalance export --as-of 2026-10-30 -o trades.csv
    folio-rebalance: note: wrote 16 trades to trades.csv

One row per trade in the order `propose` prints them, with its own column
list (`folio/rebalance/export.py`), separate from `folio export`:

    portfolio,as_of,side,instrument,name,kind,currency,quantity,price,local_value,fx_rate,base_value,weight_before,weight_after,target_scope,target
    GBL-BAL,2026-10-30,sell,GEIF,Harrow Global Equity Index Fund,fund,GBP,59382,3.4303,203698.07,1.000000,203698.07,0.060224,0.050000,instrument,GEIF
