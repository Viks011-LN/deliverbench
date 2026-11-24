# SOLVE-NOTES: t11, standard single-name CDS pricer (`cdslib`)

## What I built

All of `app/cdslib/` (four modules). `__init__.py`, the data files and the docs are unchanged.

| Module | What it does |
|---|---|
| `dates.py` | Business days come from `HOLIDAYS_FILE`, which is read at call time and cached per path. Also `next_business_day`, `add_business_days`, `trade_dates`, `accrual_periods` (the raw (start, end, pay) triples) and `payment_schedule`. |
| `curves.py` | `DiscountCurve(curve_date, pillar_dates, zero_rates)`: continuously compounded Act/365F rates with flat forwards, the first rate flat back to the curve date, and the last forward carried on. `load_discount_curve`. `CreditCurve(trade_date, node_dates, hazard_rates)`: a piecewise-flat hazard, with `survival(date)` meaning survival to the end of that date. |
| `legs.py` | `protection_leg` and `premium_leg` per dollar at the trade date, valued exactly piece by piece. Pieces split at every discount pillar, credit node and period boundary. Each piece uses the numerical fix note's exact formula, or its 4th-order series when \|Λ+F\| < 1e-4 (Λ and F are the piece's totals). |
| `pricing.py` | `upfront_from_quoted_spread`, `quoted_spread_from_upfront`, `credit_curve` (bootstrap) and `price_off_curve`. Root finding is scipy `brentq` on a hazard rate, with xtol 1e-15. |

My check scripts sit outside the repo, in `t11-solve/checks/`:
- `tieout.py` ties out against the desk's file;
- `sensitivity.py` switches conventions off one at a time;
- `probe.py` tries distressed curves and edge dates;
- `test_cdslib.py` holds 12 pytest checks, all passing.

## Where each convention and calculation came from

| Convention / calculation | Source in the room |
|---|---|
| Business days are Mon–Fri less `data/holidays.csv` | desk-conventions.md, "Dates" bullet 1; README (read via `cdslib.dates.HOLIDAYS_FILE`) |
| Step-in is T+1 calendar; protection runs from the end of the trade date to the end of the maturity date | "Dates" bullet 3 |
| Cash settlement is the 3rd business day after T; the upfront is paid then | "Dates" bullet 4 |
| Coupon dates are 20 Mar/Jun/Sep/Dec, moved forward to a business day (Following, not Modified Following) | "Dates" bullet 5 |
| Accrual starts at the latest coupon date on or before T, moved, so the first coupon is paid whole | "Dates" bullet 6 |
| Periods run [moved coupon date, next moved coupon date), paid on the next coupon date. The last period runs through the maturity date (`accrual_end` = maturity + 1 day) and is paid on the maturity date, moved. The maturity itself is never moved. | "Dates" bullets 7–8; "The contracts" bullet 3 |
| Coupon = notional × rate × days / 360 | "The premium" bullet 1 |
| A coupon counts if the name survives to the end of the last accrual day | "The premium" bullet 2 |
| Premium accrued at default: from the start of the period's first day, plus half a day; first period counts defaults only from step-in | "The premium" bullet 3; the integral is in O'Kane–Turnbull §5 [page 8] |
| Accrued premium of an upfront: days from the period's first day through T, Act/360, paid back undiscounted at cash settlement | "The premium" bullet 4; "Prices and quotes" bullet 1 |
| Protection pays (1−R) at the moment of default | "The contracts" bullet 4; O'Kane–Turnbull §6, eq. (6) [pages 9–10] |
| Time is calendar days from T over 365 | "Curves" bullet 1 |
| Discount curve: CC zero rates, Act/365F; flat forwards between pillars and from the curve date to the first pillar; last forward carried on. Uses the file's `maturity` column, not the tenor. | "Curves" bullet 2; `data/discount-curve.csv` |
| Hazard rate flat between quote maturities, last rate carried on; survival on a date means to the end of that day | "Curves" bullet 3; O'Kane–Turnbull §4 eq. (3) [page 7], §9 [pages 13–14] |
| Bootstrap shortest first, each piece set so the contract at coupon = quote is worth nothing clean | "Curves" bullets 4–5; O'Kane–Turnbull §9 [page 14] |
| Exact per-piece integrals, not the paper's shortcuts (M points a year, half-coupon accrual) | "Valuation" bullet 1 |
| Accrual-on-default formula and series | Numerical fix note [pages 2–3]: A = Λ S0 D0 [((t0 + Δt/(Λ+F))/(Λ+F)) − ((t1 + Δt/(Λ+F))/(Λ+F)) e^−(Λ+F)]; series (t0+t1)/2 − (t0+2t1)/6 X + (t0+3t1)/24 X² − (t0+4t1)/120 X³ + (t0+5t1)/720 X⁴ |
| Protection formula and series | Numerical fix note [page 3]: (1−R) Λ/(Λ+F) S0 D0 (1 − e^−(Λ+F)); series (1−R) Λ S0 D0 [1 − X/2 + X²/6 − X³/24 + X⁴/120] |
| Series used when \|Λ+F\| < 1e-4, both as totals over the piece | Numerical fix note [page 6]; "Valuation" bullet 2 |
| Upfront = value at T carried to cash settlement on the discount curve | "Valuation" bullet 3 |
| Points = clean value % of notional; cash = notional × points/100 − accrued | "Prices and quotes" bullet 1 |
| Quoting convention: one flat hazard from the quoted spread, using the contract's own dates and recovery; then revalue at the real coupon. The inverse works the other way. | "Prices and quotes" bullet 2 |
| Off-curve price: par spread = coupon with zero clean upfront on the full curve; quoted spread = the quoting convention applied to the upfront | "Prices and quotes" bullet 3 |

I rebuilt the garbled typesetting of the note's formulas from the surrounding text and the series. Two checks confirm the rebuild:
- Expanding the exact form reproduces the note's series term by term.
- The note's own test case [page 5] gives A = 7.886e-6. With λ and f as rates and Λ = λ(t1−t0), that is the value the note's plot shows. This is a pytest check.

## Tie-out against `data/tie-outs.csv`

Method: for each row I ran `upfront_from_quoted_spread` from the quoted spread and compared points, accrued and cash. I then fed the row's points into `quoted_spread_from_upfront` and compared the spread that came back.

| Maturity | Quoted (bp) | My points | CSV points | Cash diff ($) | Spread back diff (bp) |
|---|---|---|---|---|---|
| 2029-12-20 | 45 | −1.594443324 | −1.5944433 | +0.0010 | +8.0e-7 |
| 2031-12-20 | 72 | −1.260007576 | −1.2600076 | −0.0043 | −5.3e-7 |
| 2030-06-20 | 118 | 0.586206271 | 0.5862063 | +0.0002 | +8.9e-7 |
| 2031-12-20 | 160 | 2.605516273 | 2.6055163 | +0.0013 | +6.4e-7 |

Largest errors:
- **points:** 2.9e-8. The CSV has 7 decimals, so ±5e-8 is rounding.
- **dollars:** $0.0043 on cash and $0.0033 on accrued. The CSV is to the cent, so ±$0.005 is rounding.
- **quoted spread:** 8.9e-7 bp. This floor comes from the CSV's rounded points.

All residuals are inside the CSV's own rounding. Row 2 also shows that the desk computes cash from unrounded points and unrounded accrued, then rounds the result. Rounded inputs would give −142,667.43, against the desk's −142,667.42. So I return unrounded floats.

How hard the tie-outs pin each convention (`checks/sensitivity.py` and `checks/probe.py`; worst cash error with that one convention switched off, against $0.004 baseline):

| Convention switched off | Worst cash error |
|---|---|
| No premium accrued at default | $1,678 |
| Value at the trade date instead of at cash settlement | $262 |
| Last period without the extra (maturity) day | $220 |
| First-period accrual measured from step-in instead of the period's first day | $43 |
| Coupon survival observed at the accrual end instead of the last accrual day | $37 |
| Flat hazard solved clean at the trade date instead of at cash settlement | $25 |
| No half-day adjustment | $18 |

All of these are confirmed by the desk's numbers. The tie-outs do **not** exercise:
- the bootstrap or pricing off a curve;
- inverted or distressed curves, 500bp coupons, or 20–25% recovery;
- the series branch;
- holiday-moved coupon dates, or trades on or next to coupon dates.

I checked those separately in `checks/test_cdslib.py`:
- the bootstrap reprices every quote to 1e-8 bp and zero points, for an IG curve and for an inverted 2400→1100bp curve at R = 25% and 20%;
- upfront and quoted spread round-trip from 1bp to 8000bp at both coupons, to 1e-9 relative;
- the protection leg agrees with a daily brute-force integral to 1e-6;
- the series is continuous with the exact formula across the threshold;
- the date edge cases hold;
- a 10-quote 30-year bootstrap plus pricing runs in well under a second.

## What I assumed

- I assumed the accrual start is literally "the latest coupon date on or before the trade date", even when the step-in date is itself a coupon date (a trade on the business day before one, e.g. T = Tue 19 Sep 2028). The trade then accrues from the previous quarter (92 days accrued). Its first period ends on, and is paid on, the step-in date with survival 1. Every price stays internally consistent: coupon = spread gives zero points.
- I assumed the last `Period.accrual_end` is maturity + 1 day. The docstring makes `accrual_end` exclusive, and the last period includes the maturity date.
- I assumed amounts, accrued and cash are returned unrounded, as floats; the desk rounds only the final cash (see the tie-out above).
- I assumed `CreditCurve.survival` returns 1 for dates on or before the trade date.
- I assumed that if a discount curve's date ever differed from the trade date, discounting should be forward from the trade date: DF(d)/DF(T). The desk says they always match, so this never changes a result.
- I assumed weekends only after 2040, where the holiday file ends.
- I assumed quotes may arrive in any order. I sort them by maturity and reject duplicate maturities.
- I assumed that if a quote ever needed a negative hazard, it should be allowed down to the rate where survival to that maturity reaches 1. The desk says this never happens.
- I assumed an invalid input should raise `ValueError`: maturity on or before the trade date, an upfront no non-negative flat hazard can produce, or a spread no finite hazard fits.
- I assumed the series applies strictly below 1e-4 ("less than"). Exactly 1e-4 uses the exact formula; the two agree to about 1e-9 there.
- I assumed a non-business trade date (the desk says this never happens) accrues from the latest *moved* coupon date on or before it. I do not validate the trade date.
- I assumed a maturity off the 20th of a coupon month (the desk says this never happens) still works: the last period runs from the last coupon date before it.

## Ambiguities

1. **Accrual start when T+1 is a coupon date.** The desk says "on or before the trade date"; I followed that. Some descriptions of the market standard phrase the rule relative to the step-in date (T+1). This is the one place a reference built on "on or before T+1" would differ. The accrued would be 0 instead of a full quarter, so cash differs by that quarter's coupon. Points would differ only by the first coupon discounted over the 2 days between step-in and cash settlement: about 6e-5 points, or roughly $6 on $10M at 100bp. It only arises for trades on the business day before an unmoved coupon date.
2. **"Worth nothing clean" in the bootstrap.** Clean at the trade date or at cash settlement? I used the clean upfront at cash settlement: "no upfront before accrued premium", with upfronts being values at cash settlement. The same choice in the flat-curve quoting convention is confirmed by the tie-outs ($25 otherwise). The bootstrap uses the identical objective, but no tie-out tests it directly.
3. **What a "piece" is for the 1e-4 test.** I split at every discount pillar, credit node and integration bound (period boundaries for the accrual-on-default leg). Any refinement of the pillar partition gives the same integral to about 1e-12, so this cannot move a price by a cent.
4. **The note's garbled equations.** Rates versus totals: the note's series is in totals Λ and F, and the desk says "each taken as its total". I used totals throughout. The note's test case confirms this (see above).

## Things that looked like traps

- **The paper's shortcuts.** These are default only at M points a year, premium accrued taken as half a coupon, and the bootstrap example's frequencies. The desk forbids them, and the exact integrals are needed: dropping premium accrued at default alone costs $1.7k.
- **20 Sep 2026 is a Sunday.** Accrual therefore starts Mon 21 Sep: 60 days, $16,666.67 accrued, not 61 days.
- **The last period's extra day ($220),** the half-day adjustment ($18), and the first-period accrual counted from the period's first day while only post-step-in defaults count ($43).
- **Upfront at cash settlement,** not the trade date ($262). The accrued is subtracted undiscounted at cash settlement.
- **Survival for a coupon** is taken at the end of the last accrual day, not at the payment date or accrual end ($37).
- **Discount-curve pillars** sit on moved dates (2Y = 2028-11-20, 7Y = 2033-11-21). Use the `maturity` column, not the tenor arithmetic.
- **Quoted spread ≠ par spread** off a non-flat curve. They are different numbers in `CurvePrice` (e.g. 1200bp par vs 1149bp quoted on the inverted test curve).
- **Tie-outs are only investment grade at 40% recovery.** The desk warns the same model must hold for distressed, inverted, 500bp-coupon and 20–25% recovery names. The bootstrap search therefore expands up to very high hazards, and was tested on such a curve.
- **Holidays that land on coupon dates:** e.g. 20 Jun 2033 (Juneteenth observed) moves that coupon date to the 21st. Christmas and New Year observed in 2027 and 2032 affect cash settlement around year end.
- **Following, never Modified Following** ("even into the next month").
- **The README requires reading holidays relative to the package** (`HOLIDAYS_FILE`), never an absolute path. Mine is looked up at call time, so a test can repoint it.
