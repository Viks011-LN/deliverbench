# Solve notes: "Where the risk comes from"

## Files changed or added (all under `app/`)

| File | Change |
|---|---|
| `folio/calc/returns.py` | **Bug fix** in `daily_pnl_shares()`: it was off by one day (see "Trap" below). |
| `folio/calc/risk.py` | New `VolShares`, `vol_shares()` (Euler split of volatility by line), `VolGroup`, `vol_groups()` (sum by sector / issuer / any key, optional top-N fold). |
| `folio/report/text_report.py` | New `render_vol_shares()` for `report --by risk`. |
| `folio/report/csv_export.py` | New column `vol_share` just before `weight`; optional `vol_shares=` argument. |
| `folio/report/json_export.py` | New position field `vol_share` just before `weight`; optional `vol_shares=` argument. Cash entries unchanged. |
| `folio/limits/rules.py` | New rule `NameVolShare` (`name_vol_share`); `Rule.needs_vol_shares` flag; `measure/check/closest` take an optional `vol_shares`. |
| `folio/limits/checker.py` | `NameVolShare` appended to `RULES`; new `needs_vol_shares()`; `run_checks(..., vol_shares=None)`. |
| `folio/config/settings.py` | New field `LimitSettings.name_vol_max_share`; range message says "fraction of the portfolio's volatility" for it. |
| `folio/config/defaults.toml` | `name_vol_max_share = 0.20` with a comment. |
| `folio/cli.py` | `report --by risk`; `Context.vol_shares()` (cached); export always passes shares; check-limits computes them when the rule is on; `--since` with `--by risk` is a usage error. |
| `README.md`, `docs/ARCHITECTURE.md` | Command table, limits table, reports section. |
| `tests/test_vol_share.py` | **New** test file, 9 tests. No existing test was touched. |

## Decisions and where each one comes from

| Decision | Source in the repository |
|---|---|
| **Method**: Euler allocation, share_i = Cov(P&L share_i, r_p) / Var(r_p). | `docs/risk-notes.md`, "Shares of volatility" ("split with the Euler allocation of volatility, applied to the daily P&L shares"). |
| **Inputs are daily P&L shares, not weights x returns**: line P&L day to day / previous day's NAV. | `docs/risk-notes.md`, "Splitting a risk figure by line"; `calc/returns.daily_pnl_shares()` docstring ("Meant for splitting a risk figure by line or by group"); `calc/risk.tail_losses()` does the same for ES. |
| **Return basis: simple returns**, not the log returns `folio risk` uses for its volatility. | `docs/risk-notes.md`, "The series behind every risk figure" ("Anything that splits a risk figure works on the simple returns instead"). |
| **Window**: last `risk.var_lookback_days` daily returns, same as `summarise_risk()`; refuse below `risk.min_observations` (RiskError, same message as `summarise_risk`). | `docs/risk-notes.md` (same section); `calc/risk.summarise_risk()`. Checked in tests: start/end/observations equal the RiskSummary's. |
| **Series**: today's holdings revalued at historical prices and FX. | `docs/risk-notes.md`; `calc/returns.line_values()/history_dates()`. |
| **Lines**: every position plus every cash balance; base-currency cash has share 0, foreign cash moves with FX. All shares add up to 100%. | `docs/risk-notes.md`, "Splitting a risk figure by line" and "Shares of volatility". |
| **Divisor**: n - 1 (`statistics.covariance` / `statistics.variance`, as `benchmark/tracking.py` does); it cancels. | `docs/risk-notes.md` first bullet. |
| **No annualisation** of shares. | `docs/risk-notes.md` ("annualisation does not come into it"). |
| **Sector share** = sum of its lines' shares; cash is a separate `Cash` row, as in the sector report; the row only shows when `report.show_cash` is on. | `docs/risk-notes.md` second bullet; `text_report.render_breakdown()`; `defaults.toml` `[report] show_cash`. |
| **Sector ordering / folding**: largest first, ties by key (`aggregate/rollup.rollup`), `report.top_n` folds into "Other" like the exposure breakdown. | `aggregate/rollup.py` docstring; `calc/exposure.breakdown()`; `defaults.toml` `top_n`. |
| **Holding rows**: largest vol share first, ties by id, then cash balances in currency order (`CASH` / `Cash XXX` rows as in `folio value`). | `ARCHITECTURE.md` "Conventions" (sorted output); `text_report.render_valuation()` (cash rows after positions). |
| **Percent format in the report**: `format_pct` with `report.percent_places`, same as Weight. | `text_report.py`, `report/tables.py`. |
| **Export placement**: `vol_share` just before `weight`; CSV written like weight (`quantize` to 6 places, plain); JSON like weight (`round(float, 6)` number). Only positions get it; cash entries don't. | Ticket; `csv_export.py` (`WEIGHT_PLACES`), `json_export._weight()`. |
| **Limit rule**: by issuer (`Instrument.issuer_key`), shares and bonds together, cash not a name; breach strictly above, compared on exact Decimals; standard `BREACH name_vol_share X: a% > b%` line. | `docs/risk-notes.md` third bullet; `limits/rules.NameShare` and module docstring; ticket for name and setting. |
| **Setting**: `limits.name_vol_max_share`, default 0.20, in `defaults.toml` + `LimitSettings` (both must list it). | Ticket; `config/settings.py` docstring; `tests/test_config.py::test_defaults_file_and_dataclasses_list_the_same_keys`. |
| **Rule order**: appended last in `RULES`, so every existing breach line keeps its place. | `limits/checker.RULES` ("in the order their breaches are printed"). |

## Assumptions

- I assumed the **holdings table includes cash balances** (so the table adds up to 100%), and that `report.show_cash` applies only to the sector table, because the setting's comment says "the sector and kind breakdowns".
- I assumed **`report.top_n` folds the sector table** too, since it is a breakdown and the sector report folds.
- I assumed **`--since` makes no sense with `--by risk`** and made it a usage error (exit 2, before any data is read) rather than silently ignoring it.
- I assumed **`export` should refuse to run** (RiskError, exit 2) when there is too little history for the shares, because folio "refuses the figure rather than guess" and check-limits/risk already behave this way. The shares are computed before the output file is opened, so no half-written file is left.
- I assumed that **when the portfolio did not move at all** over the window, every share is 0 (the precedent is `tail_losses()` with a zero total), rather than an error.
- I assumed the **JSON cash entries do not get `vol_share`** (ticket says "each position's share"; an existing test checks the cash entries exactly).
- I assumed **library callers** of `write_csv`/`valuation_document` without shares get a blank cell / `null`, so the CSV column list stays fixed (the module says the risk team reads columns by name).
- The report also prints the window (`start to end, N daily returns`), worded as `folio risk` does.

## Ambiguities

- **The report's format** is not specified. I used two tables: by holding (Instrument, Name, Sector, Weight, Vol share) and by sector (Sector, Positions, Weight, Vol share), with the standard header.
- **Rules needing shares without shares given.** The existing tests call `run_checks(valuation, rules)` and `run_checks(valuation, rules, risk)` with no price history, and `test_disabled_rules` requires `needs_risk()` to be False once `var_share` is off. So the new rule uses a separate `needs_vol_shares` flag, and `run_checks` skips it when no shares are passed (it is still listed in `result.rules`). Calling the rule directly without shares raises ValueError, as `VarShare` does without a risk summary. The CLI always passes the shares when the rule is enabled.
- **Inevitable output changes:** `check-limits` now says `OK: 5 rules checked`, `-v` prints an extra `ok name_vol_share ...` line, the export has one more column/field, and `report --help` lists `risk`. Short-history data folders now fail `export` and `check-limits` unless `name_vol_share` is disabled. Nothing else changes: all 413 existing tests pass unchanged.
- **Wording of the range error** for the new setting: the generic check says "a fraction of NAV", which is wrong for a share of volatility, so for this one key it says "a fraction of the portfolio's volatility". The existing message for the other keys is unchanged.

## Trap found, and how I checked the numbers

**Trap: `calc/returns.daily_pnl_shares()` was off by one day.** It is the helper the risk notes point to for this job, but it is not used anywhere. `simple_returns()` dates `returns[t]` by `days[t+1]`, yet the function took the P&L from `days[t-1]` to `days[t]` over `navs[t-1]`. So each row's shares were the *previous* day's P&L and never added up to that row's return (all 60 of 60 rows were wrong on the sample). With a lookback at least as long as the history, `values[t-1]` at t=0 would even wrap round to the last day. Used as shipped, the "shares" summed to about -14% instead of 100%. I fixed the indexing (`values[t] -> values[t+1]` over `navs[t]`), and a new test checks the shares add up to each day's return.

Other checks:
- **Independent exact computation.** A scratch script (outside `app/`) rebuilt every line's P&L shares from `line_values()` with my own indexing, in exact `Fraction` arithmetic. It compared the CLI's CSV and JSON `vol_share`, the report's window line, and the `check-limits` breach list for 4 cases: as-of 2026-10-30 with lookbacks 60 and 30, as-of 2026-09-30 with 40, and as-of 2026-10-15 with 200 (the whole history, 77 returns). There were 0 mismatches.
- **Hand-checkable book (in the tests).** Line B's P&L is always -0.5 x line A's, which gives exact Euler shares of A = 200%, B = -100%, cash = 0. The calculation, report, CSV and JSON all reproduce these.
- **Sample-data sanity.** Shares add up to 100% for lines and for sectors + Cash. The window equals `folio risk`'s (2026-08-07 to 2026-10-30, 60 returns). The largest issuer is ADZM at 8.7% (shares 8.2% + bond 0.5%), so the default 20% limit does not breach. The existing CLI tests that pin exact `check-limits` output still pass. Technology is 16.4% of NAV but 31.2% of the volatility; Government is 21.1% of NAV but 1.6% of the volatility.
- **Edge runs.** `--since` with `--by risk` exits 2. `risk --by risk` is still an invalid choice. Short history makes export/report/check-limits exit 2 with the `min_observations` message. Thresholds of 0 or 1.5 are refused. `limits.disabled=name_vol_share` gives `OK: 4 rules`. `top_n` and `show_cash=false` fold and drop the Cash row. `percent_places=2` works.
- **Test suite:** 422 passed (413 existing, unmodified, plus 9 new).
