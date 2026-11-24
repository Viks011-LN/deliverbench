# folio

Valuation, risk and limit checks for the desk's model portfolio. Reads four
files from a data folder, values the book in the base currency and prints
plain-text reports. Standard library only; Python 3.11 or later.

## Running it

From this folder, with no install:

    python -m folio value
    python -m folio report --by sector
    python -m folio check-limits

Or install it (`pip install -e .`) and use the `folio` command. Every
command reads `./data` unless you pass `--data-dir DIR`.

| Command | What it prints |
|---|---|
| `value [--sort weight]` | every holding with price, value in base currency, weight and return on cost |
| `risk [--histogram] [--by DIM]` | volatility, historical VaR and expected shortfall, drawdown, bond duration |
| `report --by {sector,currency,kind} [--since DATE]` | exposure table, optionally with contribution to return |
| `export --format {csv,json} [-o FILE]` | one row (or object) per position |
| `check-limits [-v]` | one `BREACH ...` line per limit breach; exit status 1 if there is any |

Common options go before or after the command: `--as-of YYYY-MM-DD` (default
today; a date after the last price becomes the last price date), `--config FILE`
and `--set section.key=value` (repeatable).

Exit status: 0 fine, 1 a limit is breached (`check-limits` only), 2 bad input,
bad settings or bad usage.

Example, on the sample data:

    $ python -m folio report --by kind --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Exposure by kind
    Kind    Positions   Market value  Weight
    ------  ---------  -------------  ------
    equity         24  10,818,431.09   54.3%
    bond            8   4,638,867.10   23.3%
    fund            6   3,819,256.81   19.2%
    Cash                  647,867.44    3.3%
    ------  ---------  -------------  ------
    Total          38  19,924,422.44  100.0%

    $ python -m folio check-limits --set limits.sector_max_share=0.2
    BREACH sector_share Government: 21.1% > 20.0%

<!-- side tools -->
## Other tools

Five smaller tools share folio's data folder, settings and common options. Each
reads its own files next to the four below and has its own page in `docs/`.
The folio commands never read these files, and each tool needs only its own.

| Tool | What it does | Its files |
|---|---|---|
| `python -m folio.ledger` | trades and cash flows: realised P&L (FIFO), cash by currency, reconciliation with positions.json | `trades.csv`, `cash_flows.csv` |
| `python -m folio.compliance` | the client's investment guidelines and restricted list (not the desk's own limits) | `guidelines.toml`, `restricted.csv` |
| `python -m folio.scenarios` | what-if stress tests: price, FX and yield shocks, and historical windows | `scenarios.toml` |
| `python -m folio.benchmark` | active weights, active share and tracking error against the benchmark index | `benchmark.csv`, `benchmark_levels.csv` |
| `python -m folio.rebalance` | drift from the model weights and a proposed trade list | `targets.csv`, `trading.toml` |
<!-- /side tools -->

## Data folder

| File | Content |
|---|---|
| `instruments.csv` | one row per instrument: id, name, kind (equity, bond, fund), sector, currency, and kind-specific columns; other columns are ignored |
| `positions.json` | the portfolio: lots per instrument (negative quantity = sale) and cash per currency |
| `prices.csv` | closing prices, one column per instrument; blank = no price that day |
| `fx.csv` | FX fixings, one column per pair such as `EURUSD` |

The sample data is a fictional 38-line balanced portfolio, June to October 2026.

## Settings

Settings live in `folio/config/defaults.toml`, which lists every key with its
default and a comment. Override them in `./folio.toml` (same layout, only the
keys you change) or for one run:

    python -m folio check-limits --set limits.sector_max_share=0.30

Unknown keys are errors. `folio/legacy/` is deprecated and no longer read; it
stays only for old scripts that import it.

## Tests

    python -m pytest

The suite runs in a few seconds and needs only pytest.

See `docs/ARCHITECTURE.md` for how the pieces fit together, and `docs/risk-notes.md`
for how the desk measures risk.
