# T11 tick list: every choice the reference makes, and where the room settles it

T11's first build step (docs/PLAN-V2.md section 3, docs/job-plans/T11-PLAN.md). The reference is ISDA's own code for
the CDS Standard Model, C code v1.8.3 (`isda_cds_model_c_v1.8.3.zip`, sha256 bee02772...0db0), its licence accepted
by the owner by hand. It is built in the git-ignored cache (`.cache/isda/`) as a shared library with the makefile's
own flags plus `-fPIC` (and `-Wno-error` for 2009-era C under a current gcc; the one implicit declaration it warns
about returns `int`, so nothing changes), and called through ctypes by `tasks/T11-cds-pricing/isda/driver.py`, our
code. `generate.py --isda` writes its answers to `isda/answers.json`; `isda/measure.py` measures the readings below.

The library prices; it takes the contract's dates, calendar and conventions from its caller. The driver sets those
by the standard contract's rules, so they are choices too, ticked like the library's own.

Sources: **C** = `docs/desk-conventions.md` (section named), **P** = the methodology paper (O'Kane and Turnbull 2003,
page of the converted text), **N** = ISDA's 2012 numerical-fix note (page).

## The tick list

| # | Choice the reference makes | How it makes it | Settled by |
|---|---|---|---|
| 1 | Premium day count Actual/360 | `paymentDcc = ACT_360` in every leg | C "The premium" (first bullet); P p.17 (Figure 12: "Basis Actual 360") |
| 2 | Coupon dates the 20th of March, June, September, December | the driver's dates; the library rolls back from the maturity every 3 months (`f/s` stub; standard maturities are always on the cycle, so no stub arises) | C "Dates" (coupon dates); C "The contracts" (maturities on the 20th) |
| 3 | Coupon dates move forward to the next business day | `badDayConv = 'F'` | C "Dates"; P p.17 (Figure 12's rolled dates, e.g. "Mon 22 Sep 2003") |
| 4 | Business days: Monday to Friday less the desk's holidays | the driver loads `data/holidays.csv` into the library as its holiday file (`JpmcdsHolidayLoadFromDisk`) | C "Dates" (first bullet); `data/holidays.csv` |
| 5 | Accrual start: the latest coupon date on or before the trade date, moved to a business day | driver | C "Dates" |
| 6 | Step-in date: the calendar day after the trade date | driver | C "Dates" |
| 7 | Cash settlement: three business days after the trade date (on the desk's calendar) | driver, `JpmcdsDateFromBusDaysOffset` | C "Dates" |
| 8 | Each period accrues between coupon dates as moved; paid on the period's end | `JpmcdsCdsFeeLegMake` | C "Dates" (coupon periods) |
| 9 | The last period ends the day after the maturity date (the maturity date accrues); paid on the maturity date as moved; the maturity itself never moved | `protectStart = TRUE` in `JpmcdsCdsFeeLegMake` | C "Dates" (last bullet); C "The contracts" |
| 10 | Protection from the start of the step-in date (the end of the trade date) to the end of the maturity date | `protectStart = TRUE`: the contingent leg starts the day before the step-in, observed at the end of a day | C "Dates" (step-in) |
| 11 | A coupon is paid if the name survives to the end of the period's last accrual day; discounted from the payment date | `obsStartOfDay`: survival at the accrual end less one day | C "The premium" |
| 12 | Premium accrued at default is paid, at the default | `payAccOnDefault = TRUE` | C "The premium"; P p.7 ("It also includes the payment of premium accrued...") |
| 13 | Accrued time at default measured from the start of the period's first day, plus half a day (the half-day adjustment); first period counts defaults from the step-in date on, accrued from the period's start | `JpmcdsAccrualOnDefaultPVWithTimeLine`: start and end shifted one day back, `+ 0.5` day in both times | C "The premium" (third bullet). N p.2 gives the formula without the half day, so the conventions state it |
| 14 | Accrued at default in proportion to the period's coupon (coupon rate times days over 360) | the period's amount spread over its days | C "The premium" (first bullet) |
| 15 | Both legs integrated exactly in continuous time, piece by piece between the dates where either curve has a knot | `JpmcdsRiskyTimeLine`; closed forms on each piece | C "Valuation"; N p.2-3 (the per-piece formulas). P p.8 and pp.10-11 offer shortcuts (half the coupon; monthly points); C says the standard does not use them |
| 16 | The numerical fix: the series where the hazard plus forward over a piece is under 1e-4 in absolute value, for accrued at default and the protection leg | `fabs(lambdafwdRate) > 1e-4` | N p.3 and p.6 ("the criteria we set to use the expansion is..."); C "Valuation" |
| 17 | Time in days from the trade date over 365, for discounting and survival | `JpmcdsZeroPrice`: (date - base date) / 365 | C "Curves" (first bullet) |
| 18 | Discount curve: continuously compounded zero rates, Actual/365 Fixed, from the curve date; flat forwards between pillars; the first pillar's rate before it; the last segment carried on after the last pillar | `JpmcdsMakeTCurve(..., CONTINUOUS, ACT_365F)`; `JpmcdsZeroRate` | C "Curves" (second bullet) |
| 19 | Credit curve: hazard rate flat between the quotes' maturity dates (unmoved), from the trade date, and after the last at the last piece's rate; survival observed at the end of a day | `JpmcdsCleanSpreadCurve`: nodes at the end dates, flat forwards, base date the trade date | C "Curves" (third bullet); P p.13-14 (piecewise flat, "Beyond this, it is often assumed that the hazard rate is flat") |
| 20 | Fitted one maturity at a time: each benchmark a contract traded today (same accrual start, step-in, cash settlement), clean value zero at a coupon equal to its quote | `JpmcdsCleanSpreadCurve` (`isPriceClean = 1`, value at cash settlement) | C "Curves" (fourth and fifth bullets); P p.14 ("It starts with taking the shortest maturity contract...") |
| 21 | Recovery: the name's rate; (1 - R) of notional paid at the moment of default | `recoveryRate`; pay at default (`PROT_PAY_DEF`) | C "The contracts"; P p.10 ("we typically assume that this payment is made immediately") |
| 22 | Upfronts valued at the cash settlement date | `valueDate = cash settlement`: value at the trade date over the discount factor to it | C "Valuation" (last bullet) |
| 23 | Points are the clean value; accrued premium is the current period's days to the step-in date (through the trade date), Actual/360; cash is the dirty value | `isPriceClean`; `FeeLegAI` at the step-in date | C "The premium" (last bullet); C "Prices and quotes" |
| 24 | Quoting convention: one flat hazard rate fitted to the contract itself, coupon set to the quoted spread, on the contract's own dates (the flat curve's benchmark starts on the contract's accrual start) | `JpmcdsCdsoneUpfrontCharge` / `JpmcdsCdsoneSpread`, `benchmarkStartDate` = the accrual start (driver) | C "Prices and quotes" (second bullet) |
| 25 | Par spread off a curve: the coupon at which the contract's clean value at cash settlement is zero (the definition the curve's quotes meet) | driver: from `JpmcdsCdsPrice` at coupons 0 and 1 | C "Curves" (last bullet); C "Prices and quotes" (last bullet) |
| 26 | Quoted spread off a curve: the quoting convention's spread for the curve's clean upfront | `JpmcdsCdsoneSpread` on the curve's clean price | C "Prices and quotes" (last bullet) |
| 27 | Root finding: Brent; bootstrap to 1e-10 in rate and value; quoted spread to 1e-8 | the library's settings | not settled; measured below (any tight solver agrees) |

## What the documents settle, and what the conventions add

- **The documents settle the model**: a deterministic hazard rate, survival as its exponential, the premium leg with
  premium accrued at default, the protection leg with recovery paid at default, the piecewise flat hazard rate
  fitted one maturity at a time and flat beyond the last quote (P pp.6-14); the exact per-piece formula for premium
  accrued at default, its series and the threshold, and the protection leg's series (N pp.2-6, readable after the
  char_map below).
- **The conventions add everything the standard contract fixes and the documents do not**: the 2009 contract (fixed
  coupons, upfronts, a whole first coupon, the accrued premium paid back), every date rule (rows 2 to 9), the
  desk's calendar, the observation rules (rows 10, 11, 13: start or end of a day), the half-day adjustment, the
  discount curve's basis and interpolation, the value date, points and cash, the quoting convention and the two
  meanings of par and quoted spread. The paper predates the standard contract: its Figure 12 example has no extra
  day at maturity and a running spread with no upfront, and it offers shortcuts the standard does not take. The
  conventions say the note wins where they differ (C, opening paragraph).
- **Nothing graded rests on reading an equation**: the paper's equations converted badly, so every rule is stated in
  words in C; the fix note's formulas read correctly after the char_map, and C states its threshold in words too.

## The fix note's conversion

pypdf turns the note's mathematics into unrelated letters (its font maps codes to Syriac, Oriya, Tamil, Telugu,
Kannada, Malayalam and Ethiopic letters). The char_map in `deliverbench.toml` maps each back by its place in the
formulas: 57 codes, for full-size letters (S, D, F, R, A, t, f, lambda), subscripts and powers, small-script
letters inside fractions, operators (+, -, =, <, x) and brackets. Read after mapping: the formula for A on page 2,
the definitions of t0, t1, S, D, lambda and f, the expansion on page 3, the protection leg's expansion and the
threshold sentence on page 6 all read correctly (fractions come out with numerator and denominator on their own
lines, as in any text conversion). No code is left unmapped. The converted texts' checksums are recorded
(`text_sha256`).

## What stays open, measured

`python tasks/T11-cds-pricing/isda/measure.py` runs the reference solution with one reading changed on every hidden
case against ISDA's answers. Largest errors on the hidden cases as revised on 22 Nov 2026 (no distressed names;
every spread at or under 1,000bp):

| Reading | Status | Largest effect on a hidden answer | Fails | Tie-outs (cash) |
|---|---|---|---|---|
| the series never used (closed form everywhere) | open (detail of row 16) | 0.0000bp, $0.00 | none | $0.00 |
| par spread valued at the step-in date (ISDA's own `JpmcdsCdsParSpreads`) | open (row 25) | 0.04bp on a par spread, nothing else | none | $0.00 |
| root-finder tolerances (row 27) | open | under 1e-8bp and $1e-8 (reference solution against ISDA) | none | $0.00 |
| no half-day adjustment | settled (row 13) | 0.09bp (an HY upfront, $237; an HY quoted spread, 0.085bp) | none | $0.77 to $18.06 |
| accrued time from the end of the period's first day | settled (row 13) | 0.005bp | none | $0.01 to $0.32 |
| the flat curve's benchmark from the step-in date | settled (row 24) | 0.39bp on an HY quoted spread | none | $19.93 to $136.29 |
| survival to the payment date | settled (row 11) | 0.19bp | none | $1.51 to $38.63 |
| value at the trade date | settled (row 22) | 0.33bp | none | $14.95 to $262.41 |
| protection from the end of the step-in date | settled (row 10) | 0.65bp on the par spread of the shortest curve contract | 1 curve contract | $0.85 to $21.36 |
| no extra day at maturity | settled (row 9) | 2.2bp-equivalent; every schedule | every check | $19.41 to $219.65 |
| the desk's holidays ignored | settled (row 4) | 4 of 10 schedules; prices by $2.52 | schedules | $0.00 |

**Result.** What the room leaves open moves the answers by 0.04bp at most, far under the 0.5bp threshold. The
standard's smallest details decide nothing: a careful pricer that skips the half-day adjustment passes every hidden
case (generate.py asserts it on every run), as does one that takes the closed form everywhere.

**Where the half-day line falls.** On the room's curve, at the 500bp coupon, skipping the half-day adjustment moves
a contract by 0.5bp of quoted spread (and its upfront by what 0.5bp is worth) at about 1,800bp for 6-month to
2-year contracts at 40% recovery, about 2,000bp at 20% or 25% recovery or at 5 years, and about 2,500bp at 10 years.
At 1,000bp it moves 0.11bp at most. The first build's distressed names (2,600 to 6,000bp, where it moved up to
6.6bp) were above the line; the owner chose to drop them (option (a), 22 Nov) rather than grade the half day. No
high-yield case had to be lowered for the half day; one upfront was lowered from 16.5 to 15.25 points only to keep
its quoted spread under the 1,000bp cap.

The one-day observation rules (rows 9 to 11, 22, 24) are not the smallest details: each is a rule of the standard
contract, written in C, and each moves the plain tie-outs by a cent or more. Two of them still decide hidden cases
on their own (the extra day at maturity; protection from the end of the step-in date, on one short contract).

## What the hidden data never touches

- A trade date on the day before a coupon date (the 19th of March, June, September, December): the market's rules
  are read two ways there (the latest coupon date on or before the trade date, or before the step-in date). C
  states one; no hidden trade date is on such a day.
- A maturity off the quarterly cycle (no stubs).
- A quote that would need a negative hazard rate (C says the desk's quotes never do).
- A discount curve other than the room's: every priced contract trades on the curve's date, 19 November 2026.
- A spread above 1,000bp (no distressed name).

## The lures, measured

| Wrong solution | Fails (cases out of tolerance) |
|---|---|
| one flat hazard rate where the desk prices off a name's curve | pricing off the curve 16/18, quoted spread off the curve 16/18 (by up to 24bp) |
| the curve's par spread reported as the quoted spread | quoted spread off the curve 13/18 (by up to 10bp) |
| Actual/365 premium | schedules 10/10, upfronts 16/16, quoted spreads 13/16, curve pricing 18/18; not the quoted spread off a curve (0.16bp at most) |
| coupon dates and the accrual start not moved to business days | schedules 9/10, upfronts 16/16 and curve pricing 18/18 (the accrued premium is a day off) |
| the desk's holidays ignored | schedules 4/10 |
| no premium accrued at default | upfronts 9/16, quoted spreads 8/16, curve pricing 10/18 (high-yield cases, by up to 8bp); not the quoted spread off a curve (0.12bp at most) |
| the credit-triangle shortcut | upfronts 13/16, quoted spreads 14/16, curve pricing 18/18, quoted spread off the curve 17/18 |
| the paper's shortcuts (monthly points, half the coupon at default) | upfronts 3/16, quoted spreads 2/16 (by up to 0.85bp); not made a cheat |
