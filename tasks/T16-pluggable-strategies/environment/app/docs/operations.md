# Operations

How the operations team runs `bt`, and what it relies on.

## The nightly runs

Every desk config in production is run each night on the day's price file:

    python -m bt --prices prices/latest.csv --config configs/<desk>.json --equity out/<desk>-equity.csv \
        --trades out/<desk>-trades.csv > out/<desk>-report.json

The report, the equity curve and the trade log are archived as they are. Reports are parsed by position (the
order of the sections and of the keys inside them is fixed) and the equity curves and trade logs by column order.
The morning meeting gets `--format text` for the main desks.

A run that exits with status 2 is a problem with its inputs: the message on stderr goes to the desk that owns the
config. Any other non-zero status is a bug in `bt` and goes to the quant team. `warning: ...` lines on stderr are
read but do not stop anything.

## The messages

Operations matches the messages below, word for word, to route a failure. `<path>` is the config file's path as
given on the command line; the first problem found is the one reported, in the order of `bt/config/validate.py`.

| Message | Cause |
|---|---|
| `error: <path>: not valid JSON (<reason>, line <n>)` | the config file does not parse |
| `error: <path>: the config must be a JSON object` | it parses, but not to an object |
| `error: <path>: unknown setting '<key>'` | a key that is not a setting (a typo, or a 3.x config: see `bt.tools.migrate`) |
| `error: <path>: signal must be a JSON object` | `signal` is not a section |
| `error: <path>: unknown signal type '<type>'` | no signal of that type |
| `error: <path>: signal: <type> has no parameter '<name>'` | a parameter that signal does not have |
| `error: <path>: signal.<name> must be ...` | a signal parameter with a value the signal cannot use |
| `error: <path>: <setting> must be ...` | a setting with a value the engine cannot use |
| `error: benchmark '<name>' is not a column of <prices>` | the benchmark is not in the price file |
| `error: <prices>:<line>: ...` | a problem in the price file |
| `error: fewer than two days between <start> and <end>` | the `--start`/`--end` window is too short |
| `error: cannot open <file>: <reason>` | a file that cannot be read or written |

## Checking a change

A change to `bt` that is not meant to change any output (a refactor, a speed-up) is checked before it is
released, on the golden files (`pytest`) and on the desk's configs:

1. run the released version and the changed one on the same price file and configs, with every output;
2. compare each pair of reports with `python -m bt.tools.compare OLD.json NEW.json` (no tolerance), and the equity
   curves, trade logs and summaries byte for byte (`cmp`);
3. include the configs the golden files never use: every setting away from its default, invalid configs, short
   windows, files with gaps.

Nothing may differ, not even in the last digit.
