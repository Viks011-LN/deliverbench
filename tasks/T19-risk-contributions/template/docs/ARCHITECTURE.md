# folio architecture

Last full review: folio 0.3 (March 2026). Sections marked *updated* were
touched since then; the rest describe 0.3 and may lag behind the code.

## What folio does

folio answers four questions about one portfolio on one date:

1. What is it worth, line by line and in total (NAV)?
2. How risky is it (volatility, historical VaR, expected shortfall)?
3. Where is the money (by sector, currency, instrument kind)?
4. Is it inside its limits?

Everything is read from files in a data folder, computed in memory and
printed as text, CSV or JSON. There is no database and no network access.

## Data flow

```
data/instruments.csv --> data/instruments_csv.py --+
data/positions.json  --> data/positions_json.py  --+--> calc/valuation.py --> Valuation
data/prices.csv      --> data/prices_csv.py      --+          |
data/fx.csv          --> data/fx_csv.py          --+          |
                                                              v
                     calc/returns.py --> calc/risk.py     calc/exposure.py
                              |               |                 |
                              v               v                 v
                       report/text_report.py, report/csv_export.py, report/json_export.py
                                              |
                                              v
                                       limits/checker.py --> BREACH lines, exit status
```

`cli.py` wires this together: it loads the settings and the four files once
per run, values the portfolio and hands the Valuation to whichever command
was asked for.

## Packages

| Package | Role |
|---|---|
| `folio/domain/` | Plain data: `Instrument` and its kinds, `Lot`, `Position`, `Portfolio`, `Money`. No I/O. |
| `folio/data/` | One reader per input file, plus business-day helpers. Readers raise `DataError` with file and line. |
| `folio/calc/` | Valuation, returns, risk, exposure and fees. Pure functions over domain objects. |
| `folio/report/` | Fixed-width text tables and the CSV/JSON exports. Formatting only, no maths. |
| `folio/limits/` | Limit rules and the checker. |
| `folio/legacy/` | Settings (`settings_v1.py`) and the first exposure calculation. |
| `folio/cli.py` | Argument parsing and the commands. |
| `folio/ledger/` | Side tool: trades and cash flows, FIFO P&L, reconciliation (`docs/ledger.md`). |
| `folio/compliance/` | Side tool: the client's investment guidelines (`docs/compliance.md`). |
| `folio/scenarios/` | Side tool: stress scenarios (`docs/scenarios.md`). |
| `folio/benchmark/` | Side tool: comparison with the benchmark index (`docs/benchmark.md`). |
| `folio/rebalance/` | Side tool: drift and rebalancing proposals (`docs/rebalance.md`). |

## Domain model

* An **Instrument** is immutable reference data: id, name, sector, currency,
  optional country and issuer. Three kinds: `Equity`, `Bond` (coupon rate,
  maturity; prices are quoted per 100 nominal) and `Fund` (expense ratio).
  `Instrument.market_value(quantity, price)` hides the per-100 quoting.
* A **Position** is the list of **Lots** (trades) in one instrument. Buys are
  positive, sells negative. Quantity and average cost are always computed as
  of a date, so the same file values any past date. Shorts are rejected.
* A **Portfolio** maps instrument ids to positions and holds cash balances by
  currency. Cash has no history yet: earlier dates use today's balances.
* **Money** is a Decimal amount with a currency. Adding two currencies raises
  `CurrencyMismatch`.

All amounts are `Decimal`. Floats appear only in the risk statistics, where
returns go through `math` and `statistics`.

## Input files

`instruments.csv` has required columns `id, name, kind, sector, currency`.
Bond rows need `maturity` and may have `coupon_rate`; fund rows may have
`expense_ratio`. Columns folio does not know are ignored.

`positions.json` holds one portfolio:

```json
{"portfolio": "GBL-BAL", "name": "Global Balanced",
 "cash": {"GBP": "455000.00"},
 "positions": [{"instrument": "ADZM",
                "lots": [{"date": "2025-03-14", "quantity": "2270", "price": "199.05"}]}]}
```

`prices.csv` is wide: a `date` column, then one column per instrument id. An
empty cell means no price that day; lookups use the latest earlier price.

`fx.csv` is wide too, one column per pair (`EURUSD` = USD per EUR). Crosses
go through USD.

## Valuation

`value_portfolio()` takes the open positions on the valuation date, the
latest price on or before it and that day's FX rate. NAV is positions plus
cash; each line's weight is its base-currency value over NAV. Prices older
than `stale_price_days` are flagged, not refused. Bonds are valued clean.

## Risk

`returns.nav_series()` revalues today's holdings at every historical price
date, so trades never show up as jumps. `risk.summarise_risk()` takes the
last `var_lookback_days` daily returns and reports:

* annualised volatility from log returns;
* historical VaR at 95% over one day, as a fraction of NAV and in GBP;
* expected shortfall (the average loss beyond VaR);
* maximum drawdown, best and worst day.

Percentiles interpolate linearly, like Excel's `PERCENTILE.INC`.

## Exposure

`calc/exposure.py` has one function per breakdown: `exposure_by_sector`,
`exposure_by_currency`, `exposure_by_kind`. Each loops over the valuation's
positions, adds base values into a dict keyed by the label, sorts the result
by value and divides by NAV. Cash is reported separately except in the
currency breakdown, where a GBP balance is GBP exposure.

## Reports

`report/tables.py` renders fixed-width tables from strings; callers format
numbers first with `format_money` and `format_pct`. It also has `bucket()`,
which counts values into half-open histogram bins for the risk histogram.

`text_report.py` has one renderer per command. `csv_export.py` writes one row
per position with a fixed column list; `json_export.py` writes the same
fields plus cash and NAV, with amounts as strings.

## Limits *updated*

Each rule in `limits/rules.py` measures something as a share of NAV and
reports a breach when it is strictly above its threshold:

| Rule | Measures | Threshold |
|---|---|---|
| `sector_share` | each sector | `max_share` |
| `name_share` | each issuer (shares and bonds together) | `max_share` |
| `currency_share` | each non-base currency, cash included | `currency_max_share` |
| `var_share` | historical VaR | `var_max_share` |

`check-limits` prints one line per breach,
`BREACH sector_share Technology: 31.2% > 25.0%`, and exits with status 1 if
there is any. Rules listed in `limits.disabled` are skipped.

## Settings

Settings are read by `folio/legacy/settings_v1.py` from `folio.ini` in the
working folder, on top of built-in defaults:

```ini
[general]
base_currency = GBP

[limits]
max_share = 0.20
var_limit = 0.03
```

`max_share` applies to sectors and single names alike. A TOML-based loader
with per-rule thresholds is planned in `folio/config/`.

## Conventions

* Determinism: anything that reaches output is sorted (instruments by id,
  table rows by value then name). No randomness; the only clock read is the
  default for `--as-of`.
* No third-party dependencies.

## Errors and exit status

Errors the user can fix derive from `FolioError` (`folio/errors.py`):
`ConfigError` for settings, `DataError` for input files (with file and line),
`MissingPriceError`, `ValuationError` and `RiskError`. The CLI prints them as
`folio: error: ...` without a traceback and exits with status 2. Anything
else is a bug and should crash loudly.

Notes that do not stop a run (a stale price, the valuation date moved to the
last price date) go to standard error as `folio: note: ...`, so standard
output stays clean for files and pipes.

## Glossary

| Term | Meaning here |
|---|---|
| NAV | Positions plus cash, in the base currency, on the valuation date |
| Weight / share | A value divided by NAV |
| Base currency | The reporting currency, GBP for the model portfolio |
| Stale price | A price older than `stale_price_days` business days |
| Issuer | Whoever we lose money to on default; a company's shares and bonds share one |
| Lot | One trade; a position is the sum of its lots |

## Adding a breakdown

1. Add `exposure_by_<thing>(valuation)` to `calc/exposure.py`, copying
   `exposure_by_sector`.
2. Add an `elif args.by == "<thing>"` branch in `cli.py` and a matching
   column title in `report/text_report.py`.
3. Add a test in `tests/test_exposure.py`.

## Adding a limit

1. Subclass `Rule` in `limits/rules.py` with a `name` and a `check()` method.
2. Add it to the list in `limits/checker.py`.
3. Give it a threshold in the settings file.

## Testing

`tests/` has one file per layer. Most tests run on the sample data in
`data/`; `conftest.py` also builds a three-line book with round numbers for
exact assertions. The whole suite runs in a few seconds.

<!-- side tools -->
## Side tools *updated*

The packages `folio/ledger/`, `folio/compliance/`, `folio/scenarios/`, `folio/benchmark/` and `folio/rebalance/`
are separate tools (`python -m folio.<tool>`), each documented in `docs/<tool>.md`. They borrow the core's
loading (`cli.load_context` and the common options), its valuation and its table helpers, but the core never
imports them: nothing under `folio/calc/`, `folio/report/` or `folio/limits/` depends on a side tool, and the
`folio` commands never read the side tools' files. Grouping in scenarios and benchmark follows
`calc/exposure.DIMENSIONS`. Compliance is not the limits package: limits are the desk's own risk limits
(`check-limits`), compliance is the client's mandate, with its own file and wording.
<!-- /side tools -->

## Known gaps

* Bonds are valued clean; accrued interest is missing.
* Cash has no history (see Domain model).
* One portfolio per data folder.
