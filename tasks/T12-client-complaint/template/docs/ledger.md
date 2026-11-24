# Trade ledger

`positions.json` says what the portfolio holds; the ledger says how it got
there. It reads every trade and every other movement of cash, and answers
what the positions alone cannot: what we dealt (`trades`), what we made on
what we sold and what the holdings paid us (`pnl`), where the cash came from
(`cash`), and whether the trades still agree with the booked positions
(`reconcile`).

It lives in `folio/ledger/` and runs as `python -m folio.ledger <command>`,
with folio's common options (`--data-dir`, `--as-of`, `--config`, `--set`).
`--as-of` is settled as folio settles it and is the last day the ledger
counts. The folio commands never read the two ledger files, so a data folder
without them still values. Exit status: 0 fine, 1 `reconcile` found a
difference, 2 bad input, settings or usage, printed as `folio-ledger: error: ...`.

## Input files

`trades.csv` has one row per trade, in the order the trades were done:

| Column | Meaning |
|---|---|
| `trade_id` | unique reference, such as `T0071` |
| `date` | trade date, a business day; dates must not go backwards down the file |
| `instrument` | an id from `instruments.csv` |
| `side` | `buy` or `sell` |
| `quantity` | always positive: units, or nominal for bonds |
| `price` | quoted like the instrument, per 100 nominal for bonds |
| `fees` | in the trade currency; blank for none |
| `currency` | must be the instrument's currency |

`cash_flows.csv` has every other movement of cash: `date`, `currency`,
`amount` (signed: positive in, negative out), `kind`, and optionally
`instrument` and a free-text `note`.

| Kind | Sign | Instrument |
|---|---|---|
| `subscription` | in | none |
| `redemption` | out | none |
| `dividend`, `coupon` | in | required, paid in its currency |
| `interest` | either | none |
| `fee` | out | optional |
| `fx` | either | none; a conversion is two rows, one per currency |

Every lot in `positions.json` appears in `trades.csv` (a negative lot is a
sale). The sample also has round trips that `positions.json` never booked:
FRXL, bought and sold between June and October 2026, and a second NYQV trade
after the August sale.

## Commands

`trades [--instrument ID] [--since DATE]` lists the trades with the cash
each one settled (a buy pays value plus fees, a sale receives value less fees):

    $ python -m folio.ledger trades --instrument FRXL --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Trades in FRXL up to 2026-10-30

    Date        Trade  Instrument  Side  Quantity   Price  Ccy    Fees   Settlement
    ----------  -----  ----------  ----  --------  ------  ---  ------  -----------
    2026-06-09  T0065  FRXL        buy        600  316.12  USD   94.84  -189,766.84
    2026-07-14  T0067  FRXL        buy        400  314.68  USD   62.94  -125,934.94
    2026-07-30  T0068  FRXL        buy        200  338.11  USD   33.81   -67,655.81
    2026-08-05  T0069  FRXL        sell       200  310.66  USD   31.07    62,100.93
    2026-08-25  T0071  FRXL        sell       700  357.12  USD  124.99   249,859.01
    2026-10-15  T0076  FRXL        sell       300  399.18  USD   59.88   119,694.12

    6 trades: 3 buys, 3 sales

`pnl [--since DATE] [--by instrument|sector]` shows realised P&L and income
(dividends and coupons) per instrument, or per sector in the base currency
only. `--since` picks the sales and payments, not the lots they close:

    $ python -m folio.ledger pnl --since 2026-10-01 --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Realised P&L (FIFO) and income from 2026-10-01 to 2026-10-30, in GBP

    Instrument  Ccy   Sold    Proceeds        Cost   Realised  Realised GBP  Income GBP  Total GBP
    ----------  ---  -----  ----------  ----------  ---------  ------------  ----------  ---------
    EQDF        USD                                                    0.00    7,061.68   7,061.68
    FRXL        USD    300  119,694.12   99,139.54  20,554.58     15,538.69        0.00  15,538.69
    GRBY        GBP                                                    0.00    4,629.50   4,629.50
    MXTB        GBP                                                    0.00    9,951.00   9,951.00
    NYQV        USD  8,000  170,964.47  148,874.40  22,090.07     16,677.66        0.00  16,677.66
    PCRF        GBP                                                    0.00   13,357.50  13,357.50
    PZLY        USD                                                    0.00    3,512.55   3,512.55
    ----------  ---  -----  ----------  ----------  ---------  ------------  ----------  ---------
    Total                                                         32,216.35   38,512.23  70,728.57

`cash` rebuilds each balance from nothing: trades at their value, fees (on
trades and in `cash_flows.csv`), income, capital and conversions. On the
sample the balances are exactly the cash in `positions.json`, and the GBP
total is the cash line of `folio report`. `--currency CCY` lists every
movement in CCY with the balance after it; within a day, cash flows come
before trades.

    $ python -m folio.ledger cash --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Cash by currency on 2026-10-30, from the trades and cash flows

    Ccy           Trades      Income        Fees        Capital              FX     Balance  Balance GBP
    -----  -------------  ----------  ----------  -------------  --------------  ----------  -----------
    EUR    -3,699,310.70   69,304.50   -1,262.49           0.00    3,692,518.69   61,250.00    56,125.55
    GBP    -7,436,147.98  136,943.52  -41,717.88  18,407,623.43  -10,611,701.09  455,000.00   455,000.00
    JPY     -433,819,630   6,223,100    -143,027              0     427,739,557           0         0.00
    USD    -7,047,357.94   89,541.90   -2,962.20           0.00    7,143,178.24  182,400.00   136,741.88
    -----  -------------  ----------  ----------  -------------  --------------  ----------  -----------
    Total                                                                                     647,867.44

`reconcile` rebuilds the open lots from the trades and from the lots in
`positions.json`, and prints a `DIFF` line for each instrument open on one
side only, each different open quantity, each open lot (date, quantity,
price) on one side only and each cash balance that differs. On 30 September
both round trips were open, and `positions.json` never booked them:

    $ python -m folio.ledger reconcile --as-of 2026-10-30
    OK: 40 instruments and 4 cash balances agree with positions.json on 2026-10-30

    $ python -m folio.ledger reconcile --as-of 2026-09-30
    DIFF FRXL: 300 open from trades.csv, no position in positions.json
    DIFF NYQV: open quantity 8,000 from trades.csv, 0 in positions.json
    DIFF NYQV: open lot 2026-09-10 8,000 @ 18.60 in trades.csv only
    folio-ledger: note: cash not compared: positions.json holds current balances and the ledger runs to 2026-10-30

Cash is only compared when nothing in the ledger is dated after `--as-of`:
`positions.json` has today's balances, not a history.

`export [--output FILE]` writes one CSV row per trade. `settlement` is the
signed cash; `cost`, `realised`, `fx_rate` and `realised_base` are filled for
sales only:

    $ python -m folio.ledger export --as-of 2026-10-30 | grep -e trade_id -e T0070
    portfolio,trade_id,date,instrument,side,quantity,price,currency,fees,settlement,cost,realised,fx_rate,realised_base
    GBL-BAL,T0070,2026-08-20,NYQV,sell,10000,22.29,USD,111.45,222788.55,207528.71,15259.84,0.733245,11189.21

## How realised P&L is matched (FIFO)

Every buy opens a lot whose cost is what the buy paid, fees included. A sale
closes the oldest open lots of its instrument first, taking part of a lot
when it needs only part, and then the same fraction of that lot's cost. Its
proceeds are its value less its fees, and realised P&L is proceeds less the
cost of the lots it closed. FRXL, in USD:

| Sale | Lots closed | Cost | Proceeds | Realised |
|---|---|---:|---:|---:|
| 5 Aug, 200 @ 310.66 | 200 of T0065 (600 bought for 189,766.84) | 63,255.61 | 62,100.93 | -1,154.68 |
| 25 Aug, 700 @ 357.12 | the other 400 of T0065, 300 of T0067 | 220,962.43 | 249,859.01 | 28,896.58 |
| 15 Oct, 300 @ 399.18 | the last 100 of T0067, all 200 of T0068 | 99,139.54 | 119,694.12 | 20,554.58 |

The rows are rounded to the cent; the total, 48,296.47, is added up before
rounding. In GBP each sale is converted at the FX rate of its own date, so
the gain is what it was worth when it was made (36,022.79 for FRXL); the FX
move on the cost between buying and selling is not split out. Income is
converted at the rate of its payment date, so non-GBP sales and payments
need a fixing in `fx.csv`.

folio itself costs a holding at average cost. The two methods agree when a
sale closes the whole position or there is only one lot, as for both sales
in `positions.json` (NYQV and MXTB).
