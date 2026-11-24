# Stress scenarios

`python -m folio.scenarios` answers "what would we lose if...?" for the book
as it stands today. A scenario is a named set of shocks (equities down 20%,
the dollar down 12%, every yield 100 bp higher) or a replay of the worst
stretch in the price history. Every holding and cash balance is revalued
under it, and the P&L is reported in the base currency and as a share of NAV.

It takes the same data folder, settings and valuation date as `folio`, through
the same options (`--data-dir`, `--as-of`, `--config`, `--set`), so a scenario
always runs on the book that `folio value` shows. `--scenarios FILE` replaces
the default scenario file, `scenarios.toml` in the data folder. Plain `folio`
commands never read it.

| Command | What it prints |
|---|---|
| `list` | every scenario in the file, with its description |
| `run NAME [--by DIM]` | one scenario's P&L per group and in total; `--by` takes any breakdown `folio report` knows (default `sector`) |
| `compare` | every scenario's total P&L, worst first, with the line that loses most |
| `export [-o FILE]` | CSV, one row per holding per scenario |

## The scenario file

One TOML table per scenario under `[scenarios]`. The table name is what you
type after `run`, so it holds only letters, digits, `-` and `_`.

```toml
[scenarios.gilt-sell-off]
description = "Gilt yields up 150 bp and sterling down 7-8%; UK financials and private credit fall"
yield_bp = { GBP = 150 }
fx = { USD = 8, EUR = 7, JPY = 8 }
instrument = { MXTB = -15, TLLY = -12, PCRF = -5 }
```

Percentages are written as people say them (`-20` is a 20% fall), yield
shifts in basis points. A scenario may mix any of these keys, except
`historical`, which stands alone:

| Key | Shock |
|---|---|
| `kind` | price change of every instrument of a kind: `equity`, `bond` or `fund` |
| `sector` | price change of every instrument in a sector, shares, bonds and funds alike |
| `instrument` | price change of single instruments, by id |
| `fx` | change in what one unit of a currency is worth in the base currency |
| `yield_bp` | parallel yield shift: one number for every bond, or a table by currency |
| `historical` | `{ days = N, scope = "book" }` or `"instrument"`: see below |

`description` is optional. Shocks that hit the same holding compound: under
`kind = { equity = -20 }` and `sector = { Technology = -10 }` a technology
share ends at 0.8 x 0.9 = 0.72 of its price, a 28% fall, not 30%. No price
can fall by more than 100%.

With GBP as the base, `fx = { USD = -12 }` means a dollar buys 12% less
sterling; it moves every USD position and the USD cash. The base currency
itself cannot be shocked, so for a weaker pound raise the other currencies,
as `gilt-sell-off` does.

Before any command runs, sectors and instrument ids are checked against
`instruments.csv`: a misspelt name is an error with the closest name
suggested, because a shock that moves nothing looks like a harmless scenario.

**Historical scenarios** replay the worst N-business-day move in `prices.csv`
up to the valuation date. With `scope = "book"` (the default) every window
of N price dates is tried on today's holdings, with each instrument's price
move and each currency's FX move over the window, and the window that loses
most is replayed; its moves really happened together. With
`scope = "instrument"` each holding gets the worst move in its own history,
wherever it falls, and currencies stay put: harsher than any real window.
A date without a price keeps the previous price, and ties go to the earliest
window.

## From a yield shift to a bond price

A yield shift becomes a price change through the bond's modified duration,
from the same calculation as `folio risk` (`folio/calc/bonds.py`):

    price change = -modified duration x shift

UKT34 (UK Treasury 4.25% 2034) is priced at 99.524 on 2026-10-30, a yield of
4.42% and a modified duration of 6.21. Under `rates-up-100` its price falls
6.21% and its 1,000,216.20 GBP loses 62,133.80. Over all bonds this is the
"1.09 on NAV" duration of `folio risk`: the book loses 1.09% of NAV.

The estimate leaves out convexity, so it overstates the loss when yields rise
and understates the gain when they fall: for a seven-year bond, by about a
quarter of a percent of its price for 100 bp and four times that for 200 bp.
Shifts are limited to 1,000 bp. A bond fund has no duration here and does not
move with yields; give it an `instrument` shock if it should.

## Commands on the sample data

    $ python -m folio.scenarios list --as-of 2026-10-30
    8 scenarios in data/scenarios.toml

    Scenario          Description
    ----------------  -----------------------------------------------------------------------------------
    dollar-slide      The dollar loses 12% against sterling
    energy-spike      Oil price spike: energy up 20%, industrials down 12%
    equity-sell-off   Equities fall 20%, the diversified equity funds 15%
    gilt-sell-off     Gilt yields up 150 bp and sterling down 7-8%; UK financials and private credit fall
    rates-up-100      Every bond yield 100 bp higher
    tech-rout         Technology shares fall 25-40%; the Adzel bond loses 6%
    worst-month-each  Every holding's own worst 20-day move, all at once
    worst-week        The book's worst five-day stretch in the price history, replayed

    $ python -m folio.scenarios run energy-spike --by kind --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Scenario energy-spike: Oil price spike: energy up 20%, industrials down 12%
    Shocks: sector Energy +20%, sector Industrials -12%

    P&L by kind
    Kind    Positions    Value (GBP)       Stressed         P&L  Of NAV
    ------  ---------  -------------  -------------  ----------  ------
    equity         24  10,818,431.09  10,969,047.00  150,615.91  +0.76%
    bond            8   4,638,867.10   4,595,837.36  -43,029.74  -0.22%
    fund            6   3,819,256.81   3,766,462.65  -52,794.16  -0.26%
    Cash                  647,867.44     647,867.44        0.00   0.00%
    ------  ---------  -------------  -------------  ----------  ------
    Total          38  19,924,422.44  19,979,214.45   54,792.01  +0.27%

    NAV after the scenario: GBP 19,979,214.45 (+0.27%)

Rows come worst first unless the breakdown has a fixed order, as kind does.
Cash has its own row except `--by currency`, where it joins its currency. A
historical scenario's `Shocks:` line names the window it replayed.

    $ python -m folio.scenarios compare --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Scenario P&L, worst first; NAV before GBP 19,924,422.44
    Scenario              P&L (GBP)   Of NAV      NAV after  Largest loss
    ----------------  -------------  -------  -------------  -----------------
    equity-sell-off   -2,403,676.29  -12.06%  17,520,746.15  GEIF -179,987.84
    worst-month-each  -1,680,048.29   -8.43%  18,244,374.15  ADZM -139,693.64
    tech-rout         -1,013,668.32   -5.09%  18,910,754.12  ADZM -293,916.43
    dollar-slide        -707,097.55   -3.55%  19,217,324.88  UST31 -107,886.27
    worst-week          -558,869.73   -2.80%  19,365,552.70  HLZS -72,683.96
    rates-up-100        -217,332.98   -1.09%  19,707,089.46  UKT34 -62,133.80
    energy-spike          54,792.01   +0.27%  19,979,214.45  GRBY -52,906.32
    gilt-sell-off        639,321.68   +3.21%  20,563,744.12  MXTB -95,987.02

`gilt-sell-off` makes money: about 60% of the book is in foreign currencies,
and a weaker pound lifts them by more than gilts and UK financials lose.

    $ python -m folio.scenarios export --as-of 2026-10-30 | head -3
    scenario,portfolio,as_of,instrument,name,kind,sector,currency,base_value,price_change,fx_change,stressed_value,pnl,pnl_share,window_start,window_end
    dollar-slide,GBL-BAL,2026-10-30,ADZM,Adzel Microsystems Inc,equity,Technology,USD,839761.23,0.000000,-0.120000,738989.88,-100771.35,-0.005058,,
    dollar-slide,GBL-BAL,2026-10-30,ADZM32,Adzel Microsystems 4.5% 2032,bond,Technology,USD,398360.22,0.000000,-0.120000,350557.00,-47803.23,-0.002399,,

The export has its own column list, separate from `folio export`. Positions
come by id, then one `CASH` row per balance, so a scenario's `pnl` column adds
up to its total. Changes and shares are fractions; the window columns are
filled for historical scenarios only.

Exit status is 0 on success and 2 on any error (bad data, settings or
scenario file, an unknown scenario, bad usage). Errors print as
`folio-scenarios: error: ...` and name the file, scenario and key, e.g.
`scenarios.toml: scenario oops: sector 'Technlogy' is not in instruments.csv
(did you mean Technology?)`. Notes go to standard error as
`folio-scenarios: note: ...`.
