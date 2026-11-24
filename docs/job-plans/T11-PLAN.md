# T11 job plan: price standard CDS to the market standard

The successor of v1's T01 (docs/PLAN-V2.md section 3, D11 as decided). One page; the evidence map and the
name-and-rule list go in the job's deliverbench.toml.

## The ticket (about six lines)

The desk needs a small pricer for standard single-name CDS that agrees with the market: build the credit curve
from the quotes, convert between upfront and quoted spread both ways, and price to the ISDA CDS Standard Model. The
library's functions are already laid out and documented; the desk's notes and the reference documents are in the
repo, with a few cases the desk has tied out.

Give-away words kept out: hazard, bootstrap, accrual, half-day, ACT/360, IMM, step-in.

## The room

| Path | What it holds |
|---|---|
| `cdslib/` | the library: empty, documented functions (dates, schedule, curve, legs, conversion) |
| `docs/reference/` | fetched, never committed (house rule 4): the methodology the standard is built on (O'Kane and Turnbull, "Valuation of Credit Default Swaps", 2003) and the standard's own notes, among them its 2012 note on a numerical fix. Converted to text with page markers by `dbench documents`; the fix note's mathematics needs a character map (its font maps symbols to unrelated letters) |
| `docs/desk-conventions.md` | the desk's choices, in plain words, no formulas: contracts, standard coupons, recovery, day counts, dates, the version of the standard, and everything the documents leave open (for example the half-day adjustment to accrual paid on default) |
| `data/discount-curve.csv` | the desk's discount curve as zero rates, from the curve service (the model does not build it: owner's answer to R1) |
| `data/holidays.csv` | the desk's holidays (business days are Monday to Friday less these) |
| `data/tie-outs.csv` | a few contracts with the right answers, to the cent: plain cases only (see "Levers and settings") |

## First build step, before anything else (about half a day)

1. **The owner accepts ISDA's code licence once by hand** on the publisher's download page (the plan: accepted
   by hand, its notice kept). The builder does not click a licence on the owner's behalf.
2. Compile the reference (the standard's C code) outside the room.
3. List every choice it makes on the planned hidden cases.
4. Tick each against a sentence in a fetched document or in the desk conventions, one evidence line each.
5. Write what cannot be ticked into the desk conventions, or cut it.
6. Measure that whatever stays open moves the answers by far less than 0.5bp.

Done on 22 Nov 2026: docs/job-plans/T11-TICKLIST.md (27 choices, each settled by a page of a document or a sentence
of the desk conventions; what stays open moves an answer by 0.04bp at most on the hidden cases as revised below).

## Levers and settings (decided with the owner on 22 Nov 2026, before the first model run)

The owner's decision: build T11 at the **hard end** of its settings. Hosted and local trial runs of the pilot jobs
suggest they are within easy reach of capable models.

- **Tie-outs: a few, plain only.** Four quoted-spread conversions on investment-grade names (100bp coupon, 40%
  recovery, maturities before the 2033 holiday roll). No high-yield name, and no contract priced off a name's term
  structure, among them.
- **Hidden cases at the hard end.** High-yield names up to about 1,000bp (upfronts up to about 21 points); steep and
  inverted curves (two inverted high-yield names, one peaking at 900bp); contracts between, on, before and after a
  name's quote maturities; dates that cross a holiday roll (Juneteenth observed on Monday 20 June 2033, a coupon
  date: contracts past it, one maturing on it, one trade accruing from it).
- **No distressed names** (owner's decision, 22 Nov, option (a), after the first build measured them): the first
  build had three distressed contracts each way (2,600 to 6,000bp) and an inverted distressed curve (2,800 down to
  1,100bp). There the half-day adjustment alone moved answers by up to 6.6bp, so the 0.5bp tolerance graded the
  standard's smallest detail. They were replaced by high-yield cases up to 1,000bp, and generate.py now asserts the
  plan's premise on every hidden case: a careful pricer that skips the half-day adjustment still passes.
- **Tolerance kept** at 0.5bp of spread, the upfront within what 0.5bp is worth on its contract; the accrued premium
  and every coupon to the cent; schedules' dates exactly.
- **Fairness rule:** every kind of situation the hidden cases use is written in the room (the desk conventions or
  the documents), even where the tie-outs do not exercise it, and the tick list closes. This replaces the earlier
  note that hidden cases use only conventions the tie-out cases exercise (docs/PLAN-V2.md section 3 still says so).

| Setting | Value |
|---|---|
| trade date (every priced contract; the curve's date) | 2026-11-19 |
| tie-outs | 4, plain (above) |
| hidden schedules | 10, on 6 trade dates |
| hidden quoted spread to upfront | 16: 6 IG, 10 HY (up to 1,000bp) |
| hidden upfront to quoted spread | 16: 7 IG, 9 HY (up to 979bp) |
| hidden names priced off their curves | 6 (3 steep, 2 inverted, 1 sparse), 18 contracts |
| highest spread in any hidden case | 1,000bp |
| tolerance | 0.5bp; upfront within what 0.5bp is worth; accrued and coupons to the cent |

Where the half-day line falls (T11-TICKLIST.md): skipping the half-day adjustment moves a contract at the 500bp
coupon by 0.5bp of spread only at about 1,800bp (6 months to 2 years, 40% recovery), 2,000bp (25% or 20% recovery,
or 5 years) and 2,500bp (10 years). At 1,000bp it moves 0.11bp at most; on the hidden cases 0.09bp at most. No
high-yield case had to be lowered for the half day. One case was lowered to stay under the 1,000bp cap: an upfront
of 16.5 points on the 5-year contract read as 1,026bp, so it is 15.25 points (978bp).

## How it is graded

Hidden contracts and quotes on the given curve, both directions: the quoted spread within 0.5bp of the reference,
the upfront within what 0.5bp is worth on that contract; payment schedules exactly. Hidden cases include
high-yield names, where accrual on default is large enough to matter. Each run's largest error is recorded as a
diagnostic (bp and dollars), shown, never scored.

## Lures and wrong solutions

| Wrong solution | Fails |
|---|---|
| A single flat hazard rate where the desk prices off the name's term structure (or a term structure where the quoting convention uses a flat one) | conversion or pricing |
| ACT/365 for the premium | pricing |
| Payment dates not rolled to business days, or the wrong first date | schedules |
| No accrual on default | pricing on high-yield cases |
| The credit-triangle shortcut (spread / (1 - recovery)) | pricing |
| The desk's holidays ignored (added with the hard-end settings) | schedules |

As built (cheats/, deliverbench.toml): the flat hazard rate fails both term-structure checks; the reverse lure is
the curve's par spread reported as the quoted spread (fails the quoted spread off the curve); unrolled dates also
fail the upfront checks, since the accrued premium is a day off. Without distressed names, no accrual on default
and ACT/365 no longer move a quoted spread off a curve by 0.5bp (0.12bp and 0.16bp at most), so neither fails that
check; high-yield cases still catch no accrual on default in three checks (by up to 8bp).

## Acceptable finishes

`done`. No honesty trap.

## Decided with the owner (22 Nov 2026): the documents and the reference code

- **The methodology paper** is the owner's own copy of O'Kane and Turnbull's 2003 Lehman note, declared as a local
  document (`local_source` in the manifest; sha256 d82afbcc...0e0c): the paper has no stable public address, and the owner
  chose to put the copy the desk works from in the room. Anyone rebuilding T11 adds their copy once with
  `dbench documents --add <file>`, and the checksum proves it is the same file.
- **ISDA's numerical-fix note** is fetched from cdsmodel.com (sha256 e544d384...ad69, the same file as the owner's copy),
  with a web-archive backup.
- **The reference code**: ISDA CDS Standard Model C code v1.8.3 (`isda_cds_model_c_v1.8.3.zip`, sha256
  bee02772...0db0), its licence accepted by the owner on the publisher's page on 22 Nov. Kept in the git-ignored
  cache, never in the repo or the room; its `license.txt` notice is kept with it.

Conversion: the ISDA fix note's mathematics comes out of the PDF as unrelated characters (its font's codes); a
char_map per document repairs them (`dbench documents`). The methodology paper's prose converts well but its
equations come out jumbled, so the desk conventions must not rely on an equation being readable.

## Fairness notes

- The tick list, not the solver's log, proves the room is enough: a builder-family solver may know the standard
  from memory (review R1).
- Every kind of situation the hidden cases use is written in the room, even where the tie-outs do not exercise it
  (owner's decision, 22 Nov; it replaces "hidden cases use only conventions the tie-out cases exercise").
- If the solver cannot tie out from the room alone, the scope is cut before any model run, not after.
