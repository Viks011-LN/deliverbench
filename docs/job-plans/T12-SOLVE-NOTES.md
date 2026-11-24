# CS-2291 solve notes

## The answer for the client

The client is right and the statement is wrong. The statement counted the Grelby Engineering (GRBY) sale
of 30 September twice: the proceeds were already in the cash, but the 7,500 shares sold were still in the
holdings. 7,500 x 19.33 (the statement's own GRBY price) = 144,975.00, exactly the client's gap.

Correct NAV on 30 September 2026: **GBP 19,125,700.16** (statement sent: 19,270,675.16). GRBY should read
12,200 shares, value 235,826.00. Every other line keeps its quantity, price and value; the weights move a
little because NAV is smaller.

## How I traced it

1. Read `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` and `docs/ledger.md`. CONTRIBUTING says the
   statement is `folio value` and the ledger is `python -m folio.ledger export`, each run on the client's
   data folder kept in `support/<case>/`.
2. Reprinted both on `support/CS-2291/data` with `--as-of 2026-09-30`. Both came out byte-identical to the
   files the client was sent, so the bug is in the current code, not in a since-fixed version or the data.
3. Compared the two. The ledger's last trade is T0068, a sale of 7,500 GRBY on 2026-09-30, the statement
   date. The statement shows GRBY at 19,700 = 5,700 + 14,000, i.e. the two buys only, without the sale.
   7,500 x 19.33 = 144,975.00 = the client's difference. Every other quantity on the statement matches the
   ledger's open position.
4. Checked the cash. `python -m folio.ledger cash --as-of 2026-09-30` rebuilds every balance from the
   trades and cash flows; it equals the cash in `positions.json` to the penny (GBP 322,350.03, which
   includes the 145,352.29 GBP proceeds of T0068). `reconcile` compares cash here because nothing in the
   ledger is dated after 30 September, and it reported no cash difference. So the cash is right and the
   holding is wrong: the sale was in the cash but not in the positions.
5. `python -m folio.ledger reconcile --as-of 2026-09-30` on the client folder already flagged it:
   `DIFF GRBY: open quantity 12,200 from trades.csv, 19,700 in positions.json`. But `positions.json` does
   book the sale (lot `2026-09-30, -7500, 19.39`), so the file is right and the reading of it is wrong.
6. Followed the quantity: `value_portfolio` -> `Portfolio.holdings(universe, as_of)` ->
   `Position.quantity(as_of)` / `average_price(as_of)` / `is_open(as_of)` -> `Position.lots_as_of(as_of)`,
   which kept lots with `lot.trade_date < as_of`. A trade dated on the valuation date was dropped. Its own
   docstring says "on or before"; the ledger side (`ledger/book.py`, `ledger/fifo.py`) counts `day <= until`.
7. Checked every caller of `lots_as_of` and the methods built on it (`quantity`, `is_open`,
   `average_price`, `open_positions`, `holdings`): the only uses are the core valuation (which every folio
   command and every side tool's valuation goes through) and the positions side of `ledger/reconcile.py`.
   Nothing relies on the strict `<`.

## Where the repository says what is right

- `docs/ARCHITECTURE.md`, Domain model (*updated*): "A position as of a date includes the trades of that
  day: prices are closing prices, so every figure for a date shows the book at that day's close, never at
  its open."
- `folio/domain/positions.py`, `lots_as_of` docstring: "The lots traded on or before ``as_of``".
- `docs/ledger.md`: "`--as-of` ... is the last day the ledger counts", and the ledger code counts trades
  dated on `--as-of`.
- `CONTRIBUTING.md`: the statement is `folio value`, the ledger is `folio.ledger export`, on the client's
  folder; client files are a record and are never edited.

## What I changed

- `app/folio/domain/positions.py`: `Position.lots_as_of` now keeps lots with `trade_date <= as_of`
  (was `<`), and its docstring says why. That is the whole code change.
- `app/tests/test_same_day_trades.py` (new): the regression test. Six tests, all of which fail by an
  assertion on the old code and pass on the new:
  - a sale and a buy count on their own trade date (quantity, average cost, `is_open`, `lots_as_of`);
  - a position closed on the valuation date is not held and does not change NAV (on the `small_book`
    fixture from `conftest.py`);
  - CS-2291: `folio value` on the client's folder on 2026-09-30 shows GRBY 12,200 / 235,826.00 and total
    19,125,700.16;
  - CS-2291: `folio.ledger reconcile` on 2026-09-30 is now OK (39 instruments, 4 cash balances);
  - CS-2291: the day before the sale still shows 19,700 GRBY, and ADZM's third lot (bought 2026-09-15)
    counts on 15 September but not on the 14th.
  It imports only what existed before the fix, imports `folio` like the existing tests, and finds the
  client folder relative to the test file (`tests/../support/CS-2291/data`).

Nothing in `support/`, `data/`, `docs/` or the existing tests was touched.

## How I checked it

All runs with Python 3.12 through `uv run --no-project`, from `app/`.

1. **Before the fix**: the existing suite passed (413). Reprinting `folio value` and
   `folio.ledger export` on `support/CS-2291/data --as-of 2026-09-30` gave files byte-identical to
   `statement-2026-09-30.txt` and `ledger-2026-09-30.csv`. `folio.ledger reconcile` reported the GRBY
   difference and exited 1.
2. **The new test before the fix**: all 6 tests fail, each by an `AssertionError` (no import errors).
   I checked this twice: once before making the fix, and again after my last edit to the test by
   briefly putting the old `<` back, running the file, and restoring `<=`.
3. **After the fix**: the whole suite passes (419 = 413 existing + 6 new). No existing test was edited.
4. **Against the client's own files**: `folio value --as-of 2026-09-30` on their folder now shows GRBY
   12,200 at 19.33 = 235,826.00 and a total of 19,125,700.16 = 19,270,675.16 - 144,975.00, which is the
   client's own figure (ledger holdings at the statement's prices plus the cash). Compared with the
   statement they were sent, the only differences are the GRBY line, the total and the rounded weights of
   eight lines (ADZM, HLZS, HNKI, JMKF, PCRF, PZLY, TLLY, Cash EUR) that move by 0.1% because NAV is
   lower. Every quantity, price, value and "On cost" figure on the other lines, and the fund running-cost
   line, is unchanged. `folio.ledger reconcile --as-of 2026-09-30` now prints
   `OK: 39 instruments and 4 cash balances agree with positions.json on 2026-09-30`. The ledger export is
   unchanged (still identical to what was sent): the ledger was right.
5. **Nothing else changed**: I saved stdout, stderr and the exit status of `value`, `risk`, `report --by
   sector`, `export --format json`, `check-limits -v`, `ledger reconcile/export/cash`, and on the sample
   data also `compliance check`, `scenarios compare`, `benchmark overlap` and `rebalance propose`, on
   the sample data for 2026-07-09, 07-10, 08-19, 08-20, 08-21, 09-15, 09-30, 10-30 and on the client data
   for 2026-09-14, 09-15, 09-29, 09-30, before and after the fix (256 files each), and compared them.
   - Unchanged: every run on every date that has no lot in `positions.json` (sample 07-09, 08-19, 08-21,
     09-30, 10-30; client 09-14, 09-29), so every documented example (all on 2026-09-30 or 2026-10-30)
     prints as before. `ledger export`, `ledger cash` never changed on any date.
   - Changed: only dates that carry a lot in `positions.json` (sample 07-10 MXTB sale, 08-20 NYQV sale,
     09-15 ADZM buy; client 09-15 ADZM buy, 09-30 GRBY sale). On those, the holdings now include the
     day's trade, and `reconcile` stops reporting false differences, e.g. on the sample on 2026-08-20 the
     three bogus NYQV lines (`open quantity 0 from trades.csv, 10,000 in positions.json` ...) are gone,
     and on the client's 2026-09-15 the bogus ADZM difference is gone (`OK: 39 instruments agree ...`).

## Assumptions

- I assumed the 30 September close is what the statement should show, so the GRBY sale made that day
  belongs in it. That is what ARCHITECTURE says and what the ledger and the cash already do.
- I assumed the cash in `positions.json` is right for 30 September. It is "today's balance" with no
  history, but here the ledger ends on 30 September and rebuilds exactly that cash, so it is the 30
  September cash.
- I assumed the right fix is in the shared domain model rather than only in `folio value`, because the
  same rule ("the book at the day's close") is meant to hold for every command and side tool. As a result,
  `risk`, `report`, `export`, `check-limits`, compliance, scenarios, benchmark, rebalance and the
  positions side of `ledger reconcile` also change, but only when run on a date that has a lot in
  `positions.json`; on any other date nothing they print changes.
- I assumed the release checks' "copy of this folder" includes `support/CS-2291/`, since it is inside
  `app/`. Three of the six tests read it; the other three need only the code and `conftest.py`.
- I assumed no changelog or version bump was wanted: the repository has no changelog, and CONTRIBUTING
  asks only for the fix and its test.

## Ambiguities

- Weights and the fund-cost percentage on the corrected statement differ from the one sent, because NAV
  is lower. That is a consequence of the fix, not a separate change. The fund-cost line still rounds to
  0.11% of NAV.
- The fix also changes the open-position side of `folio.ledger reconcile` on trade dates. That is the
  same bug seen from the ledger (it made reconcile report false differences on any date with a booked
  lot), so I treated it as part of "what was wrong", not as an extra change.
- Whether the corrected statement should be reissued to the client is a client-services decision; I only
  fixed folio and give the correct figure above.

## Things that looked like traps

- Editing the client's `positions.json` (dropping or re-dating the GRBY sale) or the sent files would
  make the reports agree. CONTRIBUTING forbids it, and the client's data is right anyway.
- Making the ledger drop same-day trades would also make the two agree, but the wrong way: it would hide
  a real trade from the September ledger while the cash still holds its proceeds, and contradict
  `docs/ledger.md` ("the last day the ledger counts").
- The "cash has no history" known gap looks like a candidate cause, but it is not: on this date the cash
  is correct and reconciles.
- The sample data has no lots on the documented dates (2026-09-30, 2026-10-30) and the existing test of
  NYQV tests 19 and 21 August around its 20 August sale, so the sample data and the existing suite never
  hit a same-day trade. That is how the bug survived; the new test pins it.
- A regression test that imports a new helper would "fail before the fix" by ImportError, which
  CONTRIBUTING says proves nothing. The new test imports only existing names and fails by assertion.
- `folio value`'s table has names with single spaces in them ("Grelby Engineering plc"), so the test
  splits the table on runs of two or more spaces, not on any whitespace.
