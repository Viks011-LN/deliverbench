# Examples

`strategies/channel.py` is a strategy written for the slot in `docs/design/strategy-slot.md`. Once the slot is
built, copy it into `bt/strategies/` and run, from the repo root:

    python -m bt --prices examples/prices.csv --config examples/channel.json --equity equity.csv
    python -m bt --prices examples/prices.csv --config examples/channel.json --format text

`expected/` holds what these print: `report.json` is the first command's stdout, `equity.csv` the equity curve
it writes, and `summary.txt` the second command's stdout. Neither prints anything on stderr. A build of the slot
prints exactly these, byte for byte.
