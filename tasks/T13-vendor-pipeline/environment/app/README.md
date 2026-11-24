# Macro desk: data jobs

The scripts the macro desk's scheduler runs to pull data from vendors and build the desk's tables.

## How the scheduler runs a job

- A job is one script at the root of this repo. The scheduler runs it as `python <job>.py`, from the repo root.
- A job takes its settings from environment variables. Each has a default, used when the variable is not set:

| Variable | Default | What it is |
|---|---|---|
| `MACRO_API_URL` | `http://localhost:8090` | the base address of the macro data vendor's API |
| `REGIMES_OUT` | `output/regimes.csv` | where the regime table is written; a relative path is taken from the repo root |

- A job exits with status 0 only when its output is written. Any other exit status raises an alert on the desk.
- Each run fetches its data from the vendor afresh.
- A job writes only its output, to the path in its output variable (for the regime table, `REGIMES_OUT`), and keeps
  nothing between runs.
- A job keeps working, unchanged, when the vendor's figures change: it hard-codes no figure, and it names each series
  only by the id its ticket gives.
- Jobs use the Python standard library and the packages installed on the scheduler's machine (`pip list` shows
  them). Nothing else can be installed.

## Vendors

| Vendor | What the desk takes | Its document |
|---|---|---|
| Woodgrove Macro Data | monthly macroeconomic series | `docs/vendor/macro-api.md` |

## Layout

| Path | What it holds |
|---|---|
| `docs/vendor/` | the vendors' API documents |
| `output/` | the jobs' outputs |
