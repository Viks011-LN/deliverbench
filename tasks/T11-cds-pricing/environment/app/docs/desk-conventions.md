# Desk conventions: standard single-name CDS

The desk prices standard single-name credit default swaps the way the market does: to the ISDA CDS Standard Model,
as in version 1.8.3 of ISDA's published code (the version with the 2012 numerical fix). The standard's code is not
on the desk's machines. It is built on the methodology in the reference documents below, and this note settles
everything they leave open. Where a reference document and this note differ, this note wins: the methodology paper
was written in 2003, before the standard contract of 2009 (fixed coupons, an upfront payment, a full first coupon),
and it uses shortcuts the standard does not (see "Valuation").

## The reference documents

Both are in `docs/reference/`, converted from PDF to text; `[page N]` marks the start of each page.

- `okane-turnbull-2003.txt`: Valuation of Credit Default Swaps (O'Kane and Turnbull, Lehman Brothers, 2003). The
  model the standard is built on: a hazard rate for default, the premium leg with premium accrued at default, the
  protection leg, and a credit curve built one maturity at a time from par spreads. Its prose converted well; its
  equations did not, so read each one through the text around it.
- `isda-numerical-fix-2012.txt`: ISDA CDS Standard Model: Proposed Numerical Fix (Markit, 2012). The standard's
  formula for premium accrued at default over one piece of time, and the series that replaces it, and the
  protection leg's formula, when the hazard rate and the forward rate over the piece add up to almost nothing.

## The contracts

- Standard single-name contracts, valued from the protection buyer's side.
- The coupon is fixed: 100bp or 500bp a year on the notional.
- Every contract matures on a 20 March, 20 June, 20 September or 20 December. The maturity date is never moved,
  even when it is not a business day.
- Every quote comes with the recovery rate the desk uses for the name: usually 40% for senior unsecured debt, and
  20% or 25% for subordinated or distressed names. At a default the protection pays the notional times one minus
  the recovery rate, at the moment of default.

## Dates

- Business days are Monday to Friday, except the desk's holidays in `data/holidays.csv`.
- The trade date is the day the trade is done; it is always a business day.
- The step-in date is the calendar day after the trade date. Protection starts at the start of the step-in date
  (the moment the trade date ends) and ends at the end of the maturity date.
- The cash settlement date is the third business day after the trade date. The upfront is paid on it.
- Coupon dates are every 20 March, 20 June, 20 September and 20 December. A coupon date that is not a business day
  moves to the next business day: always forward, even into the next month.
- A new trade accrues from the latest coupon date on or before the trade date (moved to the next business day if it
  is not one), so the buyer pays a whole first coupon.
- Each coupon period starts on a coupon date, as moved, and accrues up to the next coupon date, as moved, which is
  the next period's first day and is not part of the period. The coupon is paid on that next coupon date.
- The last period runs through the maturity date itself, so it accrues one day more than the days from its first
  day to the maturity date. It is paid on the maturity date, moved to the next business day if it is not one.

## The premium

- The premium accrues on an Actual/360 basis: a period's coupon is the notional times the coupon rate times the
  period's days over 360.
- A coupon is paid on its payment date if the name survives to the end of the period's last day of accrual.
- If the name defaults during a period, the buyer pays the premium accrued since the period's first day, at the
  moment of default. The standard measures the time accrued from the start of the period's first day to the moment
  of default, and adds half a day: the standard's half-day adjustment. In the first period, only defaults from the
  step-in date on count, but the premium accrued still runs from the period's first day.
- Because the buyer pays a whole first coupon, the seller pays back at cash settlement the premium accrued from the
  start of the current period up to the step-in date: the days from the period's first day through the trade date,
  on the same Actual/360 basis. This is the accrued premium of an upfront.

## Curves

- Time, for discounting and for survival, is counted in calendar days from the trade date, over 365.
- The discount curve is the curve service's file `data/discount-curve.csv`: continuously compounded zero rates, on
  an Actual/365 Fixed basis, from the curve date to each pillar's date. The forward rate is flat between pillars and
  from the curve date to the first pillar; after the last pillar the last forward rate carries on. The curve is for
  the trade date of the contracts priced with it.
- A name's credit curve has a hazard rate that is flat between the maturity dates of the name's quotes: from the
  trade date to the first quote's maturity, from each quote's maturity to the next, and after the last quote's
  maturity at the last piece's rate. Survival observed on a date means survival to the end of that day.
- The curve is fitted one maturity at a time, shortest first: each piece's hazard rate is set so that a contract
  traded today to that quote's maturity, at a coupon equal to the quote, is worth nothing clean, with the earlier
  pieces held fixed. The desk's quotes never need a negative hazard rate.
- A name's quotes are par spreads at standard maturities. A par spread is the coupon at which a contract traded
  today to that maturity would have no upfront before accrued premium, so the fitted curve gives back each quote
  exactly. Curves slope either way: a distressed name's curve is usually inverted, its short maturities quoted wider
  than its long ones.

## Valuation

- The standard values both legs exactly in continuous time. It does not use the paper's shortcuts (default only at
  a few points a month, premium accrued taken as half the coupon): between the dates where the hazard rate or the
  forward rate changes, both are flat, and each piece of the protection leg and of the premium accrued at default
  is valued exactly, as in the numerical fix note's formulas.
- The numerical fix: over a piece where the hazard rate and the forward rate add up to less than 1e-4 in absolute
  value (each taken as its total over the piece), the standard uses the note's series instead of the exact formula,
  for the premium accrued at default and for the protection leg.
- Upfronts are values at the cash settlement date: the value at the trade date carried forward to the cash
  settlement date on the discount curve.

## Prices and quotes

- An upfront is from the protection buyer's side, positive when the buyer pays. It is quoted in points: the clean
  value (before accrued premium) in percent of notional. The cash the buyer pays at cash settlement is the notional
  times the points, less the accrued premium the seller pays back.
- The quoting convention: a quoted spread stands for an upfront through one flat hazard rate, the rate at which the
  same contract, with its coupon replaced by the quoted spread, is worth nothing clean. The contract is then valued
  at its real coupon on that flat curve. Converting an upfront to a quoted spread goes the other way. The flat curve
  uses the contract's own dates (accrual start, step-in, cash settlement and maturity) and the name's recovery rate.
- Pricing off a name's curve: the desk values a contract off the name's full credit curve, built from all its
  quotes. The contract's par spread is the coupon at which it would have no clean upfront on that curve. Its quoted
  spread is the quoting convention's spread for its upfront; it differs from the par spread whenever the curve is
  not flat.

## Tie-outs

`data/tie-outs.csv` has contracts the desk has tied out against the standard, to the cent: trade date, maturity,
coupon (bp), recovery, notional, quoted spread (bp), and the upfront in points (percent of notional), the accrued
premium and the cash amount, in dollars. They are plain investment-grade contracts; the desk expects the same model
to hold for every name and curve it trades.
