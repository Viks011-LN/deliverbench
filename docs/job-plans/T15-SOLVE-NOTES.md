# t15 solve notes: weekly digest for Friday 13 November 2026

Delivered: `app/digest/2026-11-13/digest.json` (the digest) and `app/digest/2026-11-13/digest.md` (prose copy).
Finish: status `done`, `missing` empty. Q17 is answered `not in the notes`, which TEMPLATE.md says is the right
answer for such a question and leaves the digest complete.

Method: read every note in `notes/` (all dated 1 Oct to 12 Nov 2026, so all are available on 13 Nov). Took
each figure at its latest revision and cited the source note, never a weekly wrap that repeats it. Did the
arithmetic in Python with Decimal and rounded only the final answer (half-up). A build script checked that every
quote is an exact substring of its note, has at least 5 words and at most 300 characters, and has no ellipsis.
`calls.json` is generated from the files on disk and matches them byte for byte.

## Answers

| id | value | how |
|---|---|---|
| Q01 | 0.70 | Valdoria Q3 GDP q/q. First estimate 0.4% (30 Oct), revised to **0.7%** in the second estimate (5 Nov). No third estimate in the notes. Cited only the 5 Nov note. |
| Q02 | 0.30 | Valdoria Sept retail sales m/m. First estimate **-0.2%** ("fell 0.2%", 7 Oct), latest **+0.1%** (second estimate, 21 Oct). 0.1 - (-0.2) = 0.30. |
| Q03 | 0.3 | Valdoria Sept trade balance. First estimate a deficit of EUR 1.8bn = **-1.8** (15 Oct), revised to a deficit of EUR 1.5bn = **-1.5** in the second estimate (12 Nov October-trade note). -1.5 - (-1.8) = +0.3. |
| Q04 | 3.42 | Valdorian 10-year yield "ended October at 3.42%" (2 Nov month-end note). |
| Q05 | 0.10 | Kestria Q3 GDP q/q. First = flash **0.9%** (14 Oct); second 1.1% (28 Oct); latest = third estimate **1.0 per cent** (11 Nov). 1.0 - 0.9 = 0.10. The second estimate is not used, so not cited. |
| Q06 | 3.25 | Kestrian central bank "kept its policy rate at 3.25%" (5 Nov). |
| Q07 | 7.55 | Norrland Industrial revenue: Q2 **3,920** EUR m (8 Oct capital goods table, the only note with Q2 revenue), Q3 **4,216** EUR m (22 Oct results). 4216/3920 - 1 = 7.551%. |
| Q08 | 0.80 | Norrland Industrial adj. EBITA margin: Q2 **11.6%** (19 Oct preview, a reported past figure; the 8 Oct table states it too), Q3 **12.4%** (22 Oct). 12.4 - 11.6 = 0.80. |
| Q09 | raised, 0.3 | Norrland Industrial 2026 revenue guidance: before = **EUR 16.5bn to 17.0bn** (kept on 22 Oct; midpoint 16.75), latest = **EUR 16.9bn to 17.2bn** (5 Nov capital markets day; midpoint 17.05). +0.30 EUR bn. |
| Q10 | 1.53 | Corvo Telecom Q3 2026 margin = EBITDA 496 / revenue 1,284 = 38.629% (23 Oct results; the note gives profit and revenue, not the margin). Q3 2025 margin **37.1%** (13 Oct preview). 38.629 - 37.1 = 1.529. |
| Q11 | raised, 0.75 | Corvo 2026 EBITDA margin guidance: before **37.5% to 38.5%** (13 Oct, midpoint 38.0), latest **38.0% to 39.5%** (23 Oct, midpoint 38.75). +0.75 pp. |
| Q12 | 4.67 | Bellamy Foods revenue: Q2 **1,349** EUR m (20 Oct preview; also the 6 Oct staples table), Q3 **1,412** EUR m from the 5 Nov correction (the 4 Nov note said 1,421). 1412/1349 - 1 = 4.670%. Cited the correction, not the 4 Nov note. |
| Q13 | lowered, -20.0 | Bellamy Foods 2026 operating profit guidance: before **EUR 410m to 440m** (20 Oct preview, midpoint 425), latest **EUR 385m to 425m** (4 Nov, midpoint 405). -20.0 EUR m. The 5 Nov correction says the rest of the 4 Nov note is unchanged, so the guidance quote there still stands. |
| Q14 | 6.64 | Pellmark Retail sales: Q2 restated to **2,575** EUR m (28 Oct restatement, from 2,610), Q3 **2,746** EUR m (11 Nov). 2746/2575 - 1 = 6.641%. |
| Q15 | unchanged, 0.00 | Pellmark like-for-like growth guidance: before **2% to 4%** (8 Oct), latest reiterated **2% to 4%** (11 Nov). Midpoint change 0. |
| Q16 | -1.30 | Sorvik Energy operating margin: Q2 **15.2%** (9 Oct preview), Q3 **13.9%** (2 Nov results). |
| Q17 | not in the notes | Kestria's October CPI is published Monday 16 November, after this digest (9 Nov week-ahead, 12 Nov preview). The notes have only the desk's forecast (2.6%) and the consensus (2.5%), and neither is a published figure. No citations. |
| Q18 | lowered, -200.0 | Sorvik 2026 capex guidance: before **EUR 1.8bn to 2.0bn** (9 Oct, midpoint 1.9bn), latest **EUR 1.5bn to 1.9bn** (2 Nov, midpoint 1.7bn). -0.2bn = -200.0 EUR m. |
| Q19 | 4600.0 | Norrland Industrial Q3 "Order intake was EUR 4.6bn" (22 Oct) = 4,600.0 EUR m. |
| Q20 | 3.40 | Pellmark Q3 like-for-like sales "rose 3.4% year on year" (11 Nov). |

## Assumptions

- I assumed the digest date is Friday 13 November 2026, saved as `digest/2026-11-13/`, in the same date format as
  `digest/2026-11-06/`.
- I assumed every note in the folder counts as available. The latest is dated 12 Nov, so nothing is after the digest date.
- I assumed the value is a JSON number, written like last week's digest (2.9 rather than "2.90"). Q17's value is the
  string `not in the notes` with `"citations": []`, which I took to mean "no citations".
- I assumed the guidance before the latest is the guidance in force just before the change. For Norrland that is the
  16.5 to 17.0 range confirmed on 22 Oct, which is the same range as in the 8 Oct table, so the answer is the same either way.
- I assumed Pellmark's Q3 sales (2,746) exclude the Kestrian stores, which were sold on 30 June. That makes them like
  for like with the restated Q2 figure (2,575), which is the latest revision of Q2.
- For "latest less first", I treated a fall or a deficit as negative before subtracting (Q02: -0.2; Q03: -1.8 and -1.5).
- Where a figure was in two notes from its source (Q2 margin 11.6%, Bellamy Q2 revenue 1,349), I cited one note
  and chose the prose sentence over a table.

## Ambiguities

- **Q07 quote from a table.** Norrland Industrial's Q2 revenue (3,920) appears only in a table row of the 8 Oct capital
  goods review. I quoted the whole row exactly, including the runs of spaces (6 tokens, so at least 5 words). If a
  checker collapses whitespace, it still matches.
- **Q09 quote spans a line break.** The 5 Nov capital-markets-day sentence is wrapped after "EUR 16.9bn". I copied it
  exactly, with the newline, so both ends of the range are in the quote. A strict substring check and a
  whitespace-normalising check both accept it.
- **Q03 sign.** The deficit narrowed from 1.8 to 1.5. Taking "latest less first" on the balance (deficit negative)
  gives +0.3. A reader who thinks in terms of the deficit could write -0.3. I followed the template's sign rule.
- **Q15 value 0.** The midpoint change is 0, so the value is 0.0 with direction `unchanged`.
- **Q08:** the 19 Oct preview is a preview note, but its 11.6% is the reported Q2 actual, not a forecast. The 8 Oct
  table gives the same figure, so the source does not change the answer.

## Possible traps

- Q01: the 6 Nov weekly wrap table still shows Valdoria GDP at 0.4% (the first estimate). The second estimate is 0.7%.
- Q02/Q03: the 9 Oct, 16 Oct and 23 Oct wraps repeat the first estimates (-0.2%, -1.8). Repeats are not revisions.
  The September trade revision is only one sentence in the October trade note.
- Q04: the 30 Oct wrap says the 10-year "closed at 3.39% on Thursday" (29 Oct). That is not the month-end close; the
  month-end figure is 3.42%.
- Q05: there are three estimates. The answer must not use the second (1.1), so it is 1.0 - 0.9, not 1.1 - 0.9.
- Q06: the consensus expected a cut to 3.00%. The bank held at 3.25%.
- Q07/Q08/Q19: Norrland **Industries** (Kestria: Q2 1,102, Q3 1,184, orders 1.3bn, margin 10.1%) is a different
  company from Norrland **Industrial**. The 4.15bn Q3 revenue is a consensus figure.
- Q09: the 2028 targets (19bn to 20bn) are not 2026 guidance.
- Q10/Q11: Corvus Telecom (Kestria: 352/864, 39.0% a year earlier) is not Corvo Telecom. Corvo's 488m consensus
  EBITDA is not a published figure. The Q3 margin has to be worked out from EBITDA and revenue.
- Q12: the 4 Nov note and the 6 Nov wrap give 1,421. The 5 Nov correction makes it 1,412 (4.67% instead of 5.34%).
  Bellamy **Farms** (Q2 408, Q3 391) is a different company.
- Q13: the desk's forecast cut (380 to 410) is not guidance. Bellamy Farms' guidance cut (60-66 to 52-58) belongs to a different company.
- Q14: Q2 must be the restated 2,575, not 2,610 / 2.61bn. The unrestated figure gives 5.21%.
- Q17: the forecast of 2.6% and the consensus of 2.5% are not published figures, so the answer is "not in the notes".
- Q18/Q19: guidance and orders are given in EUR bn, but the questions ask for EUR million.
- Q20: 5.1% is total sales growth. Like-for-like growth is 3.4%.
