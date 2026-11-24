# Changes

The desk's record of what changed in `bt`, newest first.

## 4.7.3

- `stop_loss`, `max_turnover` and `min_history`. The report's `positions` section.
- `--format html`, for e-mail.
- `bt.tools.batch`, `bt.tools.walkforward` and `bt.tools.settings` (with `bt/config/descriptions.py`).

## 4.7.2

- The summary's risk line names the volatility window and the leverage cap.
- `bt.tools.compare`, for checking that a change to the code moved nothing.

## 4.7.1

- `benchmark`: a column of the price file the book is measured against (`bt/metrics/benchmark.py`).
- `exclude`: a restricted list of symbols that are never held.
- `cash_rate`: interest on the cash balance.
- `--trades`: the trade log. The report lists the three worst drawdowns and the average number of names held; the
  summary shows them, with a calendar of monthly returns.

## 4.7.0

- `--format text`: the one-page summary for the morning meeting.
- Gap warnings on stderr before a run (`bt/data/quality.py`).

## 4.6.0

- `min_price`: names below a price floor are left out of the ranking.
- The report gains a `capital` section and echoes every setting that shapes the book.

## 4.5.0

- The report echoes the signal with its parameters' defaults filled in (`SIGNAL_DEFAULTS` in
  `bt/config/defaults.py`), so a report says exactly what ran.
- Checks on the signal parameters' values, with their own messages.

## 4.4.0

- The volatility of each name for the volatility scale is worked out as the risk desk's spreadsheet does it,
  newest return first, so that the two agree to the last digit. Reversion keeps its own rolling statistics.

## 4.1.0

- `bt.tools.migrate` and `bt/legacy/config_v3.py`: 3.x configs in the 4.x layout. `bt.tools.sweep` and
  `bt.tools.prices_info`.

## 4.0.0

- The single-file backtest split into the `bt` package. The 2021 runner moved to `bt/legacy/runner.py` and the
  reconciliation test (`tests/test_legacy.py`) proves the two agree on the sample, day by day.
- `python -m bt` replaces `python backtest.py`.

## 3.x

- Mean reversion; weekly rebalancing; the drawdown control; forced exits beyond the fill gap.
