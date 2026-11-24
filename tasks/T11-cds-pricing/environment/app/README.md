# cdslib

The desk's pricer for standard single-name credit default swaps, to the market's standard model.

| Path | What it holds |
|---|---|
| `cdslib/` | the library. `cdslib/__init__.py` lists the entry points the desk's tools call; the modules behind them (`cdslib/dates.py`, `cdslib/curves.py`, `cdslib/legs.py`, `cdslib/pricing.py`) are laid out and documented, not yet written |
| `docs/desk-conventions.md` | the desk's conventions: the contracts, dates, curves, quotes, and the reference documents |
| `docs/reference/` | the reference documents, converted from PDF to text |
| `data/discount-curve.csv` | the curve service's discount curve for the trade date |
| `data/holidays.csv` | the desk's holidays |
| `data/tie-outs.csv` | contracts the desk has tied out, with the right answers |

The desk's tools copy the `cdslib/` package and the desk's files in `data/` (all but `data/tie-outs.csv`, which
is for checking) and nothing else, so everything the library needs belongs inside `cdslib/`. They import `cdslib`
from that copy and call the entry points with Python `datetime.date` values and plain numbers. The library reads
the desk's files from `data/` beside the package (`cdslib.dates.HOLIDAYS_FILE`), never from an absolute path. Python 3.12, with the standard library,
numpy and scipy.
