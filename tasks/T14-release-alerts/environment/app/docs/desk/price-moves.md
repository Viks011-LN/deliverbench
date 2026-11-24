# Price moves

An alert when an instrument the desk trades moves further than the desk wants to miss.

## The events

Kind `price_move`, from the pricing service, one event per instrument when it moves:

| Field | Meaning |
|---|---|
| `instrument` | the instrument's code, e.g. `ORVK` |
| `quoted_at` | when the price was quoted (UTC) |
| `last` | the latest price, or yield in percent |
| `reference` | the price or yield the move is measured from (the previous close) |
| `measure` | `pct` for a price, measured in percent of the reference; `bp` for a yield, measured in basis points |

## The rules

- A move of at least `price_move.threshold_pct` percent (a price) or `price_move.threshold_bp` basis points (a
  yield) is a `warning`; at least `price_move.critical_multiple` times that threshold, `critical`. A smaller move
  is not worth an alert.
- The reason is `move`.
- A quote older than `price_move.stale_after_minutes` when alertd sees it is stale.
- The key is `price_move:<instrument>`.

## Messages

    WARNING ORVK: price down 3.12% (last 41.27, from 42.60)
    CRITICAL QMB10: yield up 21bp (last 3.682, from 3.472)

Prices are written with two decimals and yields with three.
