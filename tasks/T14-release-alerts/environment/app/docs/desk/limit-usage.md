# Limit usage

An alert when a desk uses a large share of one of its risk limits.

## The events

Kind `limit_usage`, from the risk system after each measurement:

| Field | Meaning |
|---|---|
| `desk` | the desk, e.g. `rates` |
| `limit` | the limit's name, e.g. `VAR` or `CS01` |
| `used` | how much of the limit is used, in millions |
| `limit_amount` | the limit, in millions |
| `measured_at` | when the risk was measured (UTC) |

## The rules

- The usage is `used` as a percentage of `limit_amount`.
- From `limit_usage.info_at_pct` it is `info`, from `limit_usage.warn_at_pct` a `warning`, and from
  `limit_usage.critical_at_pct` `critical`. Below the first, it is not worth an alert.
- The reason is `usage`; when `used` is above the limit itself, `breach` follows it.
- A measurement older than `limit_usage.stale_after_minutes` when alertd sees it is stale.
- The key is `limit_usage:<desk>:<limit>`.

## Messages

    WARNING rates VAR: 88.3% of limit used (10.6m of 12.0m)
    CRITICAL credit CS01: 104.2% of limit used (2.5m of 2.4m)
