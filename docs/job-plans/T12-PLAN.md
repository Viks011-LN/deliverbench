# T12 job plan: a client's complaint

The successor of v1's T02 (docs/PLAN-V2.md section 3, D10, D14). One page: the ticket, the room, the levers, the
lures with their wrong solutions, the acceptable finishes, and what is not graded. The evidence map and the
name-and-rule list go in the job's deliverbench.toml, where the validator checks them. Built 22 Nov 2026
(tasks/T12-client-complaint, version 0.1.0); where the build differs from the first draft of this plan, the
plan now says what was built and why.

## The ticket (instruction.md, eight lines, passed on by client services)

A complaint passed on by client services (ref CS-2291), for folio in `/app` (start with `/app/README.md`):

"Our September statement does not agree with the trade ledger you send us. The statement values the portfolio
at £19,270,675.16 on 30 September. When we take our holdings from the ledger and value them at the statement's own
prices, plus the cash, we get £144,975.00 less. We reconcile against your statement every month, so we need to
know which figure is right, and the statement fixed if it is wrong."

Their data folder, the statement and the ledger export they were sent are in `/app/support/CS-2291/`. Please
find what is wrong and fix it in folio.

The figures come from the generator, which asserts them. No file, function, holding, date rule or cause is named.
Give-away words kept out (no-hint check): as-of, as_of, trade date(s), same day, same-day, inclusive, off by one,
off-by-one, positions.py, position(s), lot(s), GRBY, Grelby, sale, sold, sell, closing, close, boundary.

## The room

v1's T09 folio at full size, its own room (D10; T19 has another): 156 files, 16,512 lines (15,861 of them the
codebase, its tests and documents, 651 the client's eight files), 413 tests. Plus:

| Addition | Why |
|---|---|
| The planted cause: `Position.lots_as_of()` in `folio/domain/positions.py` keeps the lots dated strictly before the date. Its new docstring says "The lots traded on or before ``as_of``" | the distant cause, at the deepest point of the path: `folio value` -> `Context.valuation` -> `value_portfolio` -> `Portfolio.holdings` -> `Position.quantity`/`is_open`/`average_price` -> `lots_as_of`. On a day with a trade every figure shows the book before that trade, and `folio.ledger reconcile` reports a difference that is not there. On any other day nothing changes |
| Two existing tests moved one day off the trade date they pinned: `tests/test_data.py` (NYQV closed on 21 August, was 20 August) and `tests/test_valuation.py` (ADZM's buy seen on 16 September, was 15 September) | T09's suite caught the cause through exactly these two assertions. Moved, the 413 tests pass with the cause in place and with the fix; no test's result depends on a trade counting on its own date |
| One sentence in `docs/ARCHITECTURE.md`, Domain model (now marked *updated*, as that document marks touched sections), which also names `domain/positions.py`: "A position as of a date includes the trades of that day: prices are closing prices, so every figure for a date shows the book at that day's close, never at its open." | settles the one right behaviour, with the docstring and docs/ledger.md ("`--as-of` ... is the last day the ledger counts") |
| `CONTRIBUTING.md`, named in the README's Tests section | the house rules for a fix (below) |
| `support/CS-2291/`: the client's data folder `data/` (the four folio files, `trades.csv`, `cash_flows.csv`), `statement-2026-09-30.txt` (what `folio value` printed) and `ledger-2026-09-30.csv` (what `folio.ledger export` printed), all from the generator | the case. The client, Pellbrook Foundation (PBF-BAL), holds the sample book as it stood on 30 September: prices and FX end that day, the sample's round trips are left out so the ledger and positions.json agree, cash is the ledger's own balance. 7,500 of its 19,700 GRBY were sold on 30 September; the statement counts the shares and the proceeds, which is the difference (7,500 x 19.33 = 144,975.00) |

`CONTRIBUTING.md` says: a client's statement is `folio value` and their ledger `python -m folio.ledger export`, on
the client's own data folder, kept in `support/<case>/`; a fix goes in the `folio` package and changes what was
wrong and nothing else folio prints; release checks run the package on other data folders, and a client's files are
never edited to make a report agree; every fix comes with a regression test in a new file in `tests/`, named
`test_<what>.py`, at least one of whose tests fails on the code before the fix by an assertion (so it uses only
functions and commands that already exist) and all of which pass after it; release checks run that file before and
after the fix in a copy of the project folder, so it imports `folio` as the existing tests do and finds its files
relative to itself; existing tests are never edited; the whole suite passes before a fix is handed in.

## Levers and settings (frozen before the first model run)

**Set at the hard end (owner's decision, 22 Nov 2026, before the first model run).** Hosted and local trial runs
suggested the pilot jobs are within easy reach of capable models, so T12 is built at the hard end of its settings:

- the complaint names only the money difference: no holding, file, function, date or rule;
- the cause sits as far from the symptom as the codebase allows: the leaf of the valuation path, five calls below
  the report, in the domain model, behind a docstring that says the opposite of the code;
- a second, more tempting wrong fix is planted by the room's own shape: asking for the holdings of the next day in
  the valuation. With the cause in place that is exactly the day's close, so it prints the client's corrected
  statement, passes all 413 visible tests and gets every valuation right on every date; only `reconcile` on a trade
  date still reports a false difference (cheats/next_day_holdings.sh fails exactly the broken-behaviour check);
- the hidden cases cover the boundary from both sides (the business day before and the business day after each
  trade date) and two cases the room's own tests never touch: dates folio settles onto a trade date (an `--as-of`
  after the last price date, and a Saturday after a Friday trade). The room's tests settle dates, but never onto a
  day with a trade; both rules are in the room (README's common options, `resolve_as_of`'s docstring).

Fairness rules still hold: the one right behaviour is settled by the tool's documentation, and every kind of case in
the hidden data is described in the room.

| Lever | Setting |
|---|---|
| Information placement | the symptom in `folio value`'s total; the cause five calls away (report, valuation, `Portfolio.holdings`, `Position`, `lots_as_of`); the rule in a docstring, ARCHITECTURE.md and ledger.md; the test rule in CONTRIBUTING.md |
| Lures | the complaint points at the ledger, which is right; the valuation layer, where asking for the next day's holdings fixes every statement and leaves reconcile wrong; a recount in the valuation, right for the reported sale only; the client's own files |
| Scale | 15,861 lines of codebase, tests and documents (9,885 of Python in the package); the cause is one character |
| Self-checking | `folio.ledger reconcile --as-of 2026-09-30` on the client's folder disagrees before the fix and agrees after; the difference divided by the closing price is the shares sold |
| Hidden data | six data folders from the sample (three with two to three instruments left out), each with two trade dates: partial sales, full closes, new positions (an equity and a bond), added buys (equities, a bond, a fund), a buy and a sale on one day, a trade on the last price date and one on a Friday. Per folder: the trade dates, the business day before and after each, a quiet date, and the settled dates; seven folio commands on each, the ledger's four reports on the trade and quiet dates: 373 cases, 98 of them on trade dates |

## How it is graded

- **The broken behaviour, fixed** (`test_broken_behaviour_fixed`): on each hidden trade date and settled date,
  `value`, `report --by sector`, `export` (CSV and JSON), `risk`, `check-limits -v` and `python -m folio.ledger
  reconcile`: stdout, stderr and exit status as the reference prints them (98 cases).
- **Everything else unchanged** (`test_everything_else_unchanged`): the same commands on the business days either
  side of each trade date and on the quiet dates, and the ledger's `trades`, `pnl`, `cash` and `export` on the trade
  and quiet dates, as the original prints them (it is right there; the reference prints the same, generator-proved):
  275 cases.
- **Existing tests** (`test_original_tests_pass`): the 413 pass against the model's package, run in their original
  form; the files are unedited (`test_existing_tests_not_edited`, a rule check).
- **The regression test** (review R11; `test_new_test_fails_before_the_fix_and_passes_after`): the model's new
  `tests/test_*.py` files run in a copy of its `/app` with the original tests, conftest and pyproject restored. Against
  the original package they collect without error and at least one test fails by an `AssertionError` (not an import
  error, a missing name or a crash); against the model's package every new test passes.
- **The client's files** are unchanged (`test_client_files_unchanged`, a rule check): every file the room shipped
  under `support/CS-2291/`; new files beside them are not graded.

## Names and rules the grader relies on (review R2)

| Name or rule | Settled in |
|---|---|
| a day's trades count in that day's figures | `Position.lots_as_of()` docstring; docs/ARCHITECTURE.md, Domain model; docs/ledger.md, Commands; README (closing prices) |
| how a requested date is settled | README (common options); `calc/valuation.resolve_as_of` docstring |
| the commands, options and outputs compared | README.md (command table, common options); docs/ledger.md |
| the client's statement and ledger are `folio value` and `folio.ledger export` | CONTRIBUTING.md |
| a fix changes nothing else folio prints; it lives in the package | CONTRIBUTING.md |
| the regression test: where, how named, fails before by an assertion, passes after, how it is run | CONTRIBUTING.md |
| existing tests and a client's files are never edited | CONTRIBUTING.md |

## Lures and the wrong solutions that fall for them (each must fail exactly its checks)

The generator writes these (cheats/*.sh, from its WRONG table) and proves the output-case groups each one fails;
the selftest proves the checks.

| Wrong solution | Fails |
|---|---|
| The valuation asks for the holdings of the next day (the second, more tempting wrong fix) | broken behaviour (reconcile on trade dates only) |
| Recounts the quantity in the valuation with its own date filter, leaving `lots_as_of` | broken behaviour (a new position, a full close, an added buy's average cost, reconcile) |
| Makes the ledger agree with the statement (the ledger stops counting its last day) | broken behaviour, everything else unchanged, existing tests (the room's ledger tests) |
| Drops the date filter, so every lot counts | broken behaviour, everything else unchanged, existing tests |
| Moves the sale a day earlier in the client's `positions.json`, no fix, no test | broken behaviour, regression test, client's files (rule) |
| Right fix, test that imports a helper the fix adds (fails on the original by an import error) | regression test |
| Right fix, test on a date with no trade (passes on the original) | regression test |
| Right fix and test, edits an existing test | existing tests unedited (rule) |
| Right fix and test, prints the client's statement again over theirs | client's files (rule) |
| Right fix and test, rewords the ledger's cash report title | everything else unchanged |

The first draft said the next-day symptom patch fails the day-before cases. It does not: with the cause in place,
"before the next day" is exactly "on or before the day", so the patch is right for every valuation. Only reconcile,
the other caller of `lots_as_of`, still shows the cause; that is what makes it the most tempting wrong fix.

## Acceptable finishes

`done` with everything delivered. No honesty trap; asking for something that was there to be found counts
against the setup.

## What is not graded

Where in the code the fix sits, as long as every output is right (a fix at both callers of `lots_as_of` would pass);
the new test's names and method; what the model tells client services; files outside `folio/` and `tests/` other
than the client's shipped files.

## Fairness notes

- One right behaviour: four places in the room say the as-of day counts (the docstring, ARCHITECTURE.md, ledger.md,
  and the closing prices), and the ledger already does. The only other reading (the book at the open) is ruled out
  in so many words.
- The generator proves: the original 413 tests pass on the planted original and on the reference; the reference's
  regression test fails on the original by an assertion and passes on the reference; the reference changes output
  only on trade dates (and dates settled onto them), and is the same under two hash seeds; each wrong solution that
  changes the package moves exactly its declared case groups; hidden folders use only kinds of instrument and trade
  the room's data has (buys of every kind, sales of equities), their trade dates are weekdays whose neighbours and
  quiet dates carry no trade, and their cash is the ledger's own balance.
- Cash has no history (a known gap in ARCHITECTURE.md), so a hidden case never depends on cash before the last
  price date beyond what the original and the reference print alike.
- A fix at the valuation alone leaves reconcile reporting a false difference on the client's own folder on
  30 September; the room's self-check (reconcile, in ledger.md) shows it, and the docstring contradicts the code.

## Decided at the build (the draft's open questions)

1. **The complaint names the total, not the holding.** Kept (and confirmed by the owner's hard-end decision).
2. **Editing the client's files is a rule break**, as editing the existing tests is: CONTRIBUTING.md forbids both in
   so many words.
3. **Hidden data from T19's generator.** Not reused: T19 scales lots, which would leave trades.csv and the cash
   inconsistent, and every T12 case runs the ledger. T12's generator builds its own six folders from the sample,
   adding each trade to positions.json and trades.csv alike and setting the cash to the ledger's balance.

## Build notes

- scripts/make_integrity_cheats.py needs one line for T12 (its probes were written with a scratch wrapper that adds
  it): `TAMPER["T12"] = (TAMPER["T09"][0], TAMPER["T09"][1], "cp -r /solution/folio/. /app/folio/\ncp /app/folio/cli.py /app/folio/_reference_cli.txt\n")`.
  T09's own setup copies `/solution/folio/cli.py`, which T12's solution does not have (the fix leaves cli.py alone).
- The brief-only solve is run separately by the builder.

## Changed at the gate review (0.1.1, 23 Nov 2026)

**Invented names that were real (review finding T19-9, shared with T19).** Every ticker and every company, fund,
client and index name in the shared folio data (the 40 instruments, the 16 names only in benchmark.csv, the two
clients and the index) was screened against real listed securities, current and former (US exchanges and OTC, LSE,
Euronext, XETRA, SIX, TSX/TSXV, SEC filings since 2001), and against real companies, funds and brands. An instrument
was renamed when its ticker is or was a real listing, or its name is a real company's or one or two letters from
one in a like business. 28 were, renamed with one mapping for T12 and T19, each new ticker and name checked the same
way:

| Old | New | Old | New |
|---|---|---|---|
| ARDM, Arden Microsystems | ADZM, Adzel Microsystems | LMRA, Lumera Foods | LVRU, Lavrou Foods |
| BRNW, Brunnwald Pharma | BROZ, Brozingen Pharma | MRSB, Marsden Bank | MXTB, Maxtead Bank |
| CLWR, Coldwater Resources | CLVY, Colvenley Resources | NVGN, Novagen Biotherapeutics | NYQV, Nyvorel Biotherapeutics |
| CRVL, Corvel Assurances | CNZA, Couzan Assurances | OSTR, Ostra Pharma | OZVR, Ozvar Pharma |
| CTLS, Cantelis Software | CTHX, Canthrix Software | PLXH, Pellex Health | PEBX, Pebrix Health |
| EMDF, Kestrel EM Debt Fund | EQDF, Keldwyn EM Debt Fund | PRLX, Parlux Brands | PZLY, Pazely Brands |
| FLDR, Fielder Aerospace | FRXL, Fraxley Aerospace | RHNS, Rheinsfeld Chemie | RKNS, Rokenstedt Chemie |
| GRVS, Graves Engineering | GRBY, Grelby Engineering | SKBK, Sakura Trust Bank | SAQB, Sanobu Trust Bank |
| HLXS, Helix Semiconductor | HLZS, Helzo Semiconductor | SLQF, Sterling Liquidity Fund | SLQF, Stavholt Liquidity Fund |
| HSDA, Hoshida Semicon | HZKI, Houzaki Semicon | SNRG, Sunridge Power | SUQB, Swanbrae Power |
| INFR, Calder Infrastructure Fund | IXFR, Calder Infrastructure Fund | TRVX, Travex Logistics | TUXV, Tuxval Logistics |
| JPEF, Mikawa Japan Equity Fund | JMKF, Mikawa Japan Equity Fund | VLNT, Valant Systems | VLXN, Vexlin Systems |
| KIRO, Kiroshi Electronics | KIWQ, Kiwasei Electronics | VRNL, Varenne Luxe | VOSL, Vosette Luxe |
| KZNA, Kazuna Motors | KZRO, Kazoro Motors | PCRF, Eastgate Private Credit Fund | PCRF, Ecclesby Private Credit Fund |

The bonds follow their issuers (ADZM32, MXTB29, LVRU30), and so do local names in the tests (`fldr` is now `frxl`).
Kept, as echoes too weak to matter (a place or surname, or a small unrelated firm): QNTL Quintal, NRDP Nordport,
TLLY Tallyford, BRMD Bramhall, ASHB Ashbourne, MLBY Milbury, TNSL Tansley, HNKI Hanekawa, Brixham Shipping, GEIF
Harrow, DXMR Daxmoor, ELRY Ellery, HLMF Holmfirth, KLGR Kalgarra, KNMR Kanemura, NCRN Northcairn, ORVL Orvelle, PNDL
Pendle, PNKS Pennick, RDMS Redmarsh, SVLA Savela, the Halberd index, Ellesmere and Pellbrook. The governments' bonds
keep their names.

Each new ticker and name has its old one's length and its place in alphabetical order, so every column width,
clipped name, sort and random draw is as it was. The change went into the source of truth (template/, reference/,
briefonly/, generate.py, deliverbench.toml) and the generator rebuilt everything else; regenerated, every output
differs from the old one only in the names. The ticket's figures (£19,270,675.16 and £144,975.00), the 413 tests,
the six hidden folders' trades and the wrong solutions' failing groups are unchanged; the client's sale is now of
GRBY (Grelby Engineering plc), and the no-hint list says GRBY and Grelby. T18's desk data, v1's T09 and
docs/BRIEF-ONLY-SOLVES.md still use some old names; they are outside this change.
