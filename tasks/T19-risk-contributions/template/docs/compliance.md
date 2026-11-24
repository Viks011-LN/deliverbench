# Investment-guideline compliance

`folio.compliance` checks the portfolio against the client's investment
guidelines after trading: the mandate the client signed, plus the client's
restricted list. It runs on the same data folder and the same valuation as
folio, but it is a separate tool (`python -m folio.compliance`) with its own
input files and its own words.

## How it differs from `check-limits`

| | `folio check-limits` | `python -m folio.compliance check` |
|---|---|---|
| Whose rules | the desk's own risk limits | the client's mandate |
| Where they live | folio settings, `[limits]` | `guidelines.toml` and `restricted.csv` in the data folder |
| Who changes them | the desk, any time, `--set` included | the client, by signing a new schedule |
| A failure is | a `BREACH` of a limit | a `VIOLATION` of a guideline |
| Code | `folio/limits/` | `folio/compliance/` |

The two overlap on purpose: on the sample the desk caps any one name at 8%
of NAV, the client at 7%. Neither tool reads the other's thresholds, and a
`--set limits...` never loosens the mandate. `--set report...` does apply,
for the number of decimal places.

## Input files

### guidelines.toml, the mandate

```toml
[mandate]
portfolio = "GBL-BAL"                       # must match positions.json
client = "Ellesmere Staff Pension Scheme"   # optional, for the mandate table

[guidelines.issuer_max_share]
value = 0.07                                # shares are fractions of NAV
note = "Schedule 2, para 1: any one issuer" # optional

[guidelines.max_positions]
value = 40
enabled = false                             # switched off, value kept on record
```

A guideline the file does not mention is not part of the mandate. One that
is switched off is skipped by `check`, which says so on standard error every
run (`folio-compliance: note: max_positions is switched off in guidelines.toml`).
The reader is strict: an unknown section, guideline or key, a value of the
wrong type (`"5%"` instead of `0.05`) or out of range, and a mandate for a
different portfolio are errors naming the file and the key. `--guidelines
FILE` reads another mandate instead, for example a draft schedule.

### restricted.csv, the restricted list

```
instrument,issuer,reason,from,until
TNSL,,Thermal coal over 10% of revenue,2026-10-01,
,MXTB,Trustee review of consumer lending,2026-06-15,2026-07-31
```

Each row names one instrument (its id in `instruments.csv`) or one issuer
(as in the `issuer` column there, or the id of an instrument without one),
never both. An issuer row covers everything the issuer has issued: `MXTB`
catches Maxtead Bank's shares and its bond. `from` and `until` are both
included; a blank `until` means until further notice. Names the book has
never held are fine. The file is only read when a compliance command needs it.

## Guidelines

Every comparison is on exact values and equal is compliant, so `7.0% > 7.0%`
can appear when a share is a hair over its limit.

| Guideline | Value | What it measures |
|---|---|---|
| `issuer_max_share` | max share | each issuer, shares and bonds together; government bonds and funds left out |
| `country_max_share` | max share | each country, direct holdings only (funds left out: their country is where they are domiciled); no country counts as `(no country)` |
| `fund_max_share` | max share | each fund on its own |
| `govt_min_share` | min share | bonds in the Government sector held directly; government bond funds do not count |
| `max_positions` | max count | open positions; cash balances are not positions |
| `min_cash_share` | min share | cash in all currencies together |
| `restricted_holdings` | no value | any holding caught by an entry of `restricted.csv` in force on the valuation date |

Headroom is how far the tightest subject of a guideline can move before it
violates: limit minus actual for a maximum, actual minus limit for a minimum.
`check --explain` also gives it in the base currency (headroom x NAV), which
is what can be bought or sold for cash before the guideline is violated, or
for a violation the trade that brings the book back inside.

## Commands

The common options are folio's: `--data-dir`, `--as-of`, `--config` and
`--set`, before or after the command. Exit status: 0 fine, 1 a guideline is
violated (`check` only), 2 bad input, a bad mandate or bad usage. Errors print
as `folio-compliance: error: ...`.

`check [--guidelines FILE] [--explain]` prints one line per violation, in
guideline order, or `OK: N guidelines checked`:

    $ python -m folio.compliance check --as-of 2026-10-30
    VIOLATION restricted_holdings TNSL: 0.9% held, restricted since 2026-10-01 (Thermal coal over 10% of revenue)

    $ python -m folio.compliance check --as-of 2026-09-30
    OK: 7 guidelines checked

With `--explain` the violations are followed by the headroom of every guideline:

    $ python -m folio.compliance check --explain --as-of 2026-10-30
    VIOLATION restricted_holdings TNSL: 0.9% held, restricted since 2026-10-01 (Thermal coal over 10% of revenue)

    Headroom (tightest subject of each guideline)
    Guideline            Tightest          Actual      Limit  Headroom       In GBP
    -------------------  ----------------  ------  ---------  --------  -----------
    issuer_max_share     ADZM                6.2%   max 7.0%      0.8%   156,588.12
    country_max_share    US                 26.4%  max 30.0%      3.6%   721,373.96
    fund_max_share       GEIF                6.0%  max 10.0%      4.0%   792,523.30
    govt_min_share       government bonds   15.6%  min 15.0%      0.6%   110,558.36
    max_positions        positions             38     max 40         2
    min_cash_share       cash                3.3%   min 2.0%      1.3%   249,378.99
    restricted_holdings  TNSL                0.9%  none held     -0.9%  -180,010.00

`restricted` lists the holdings restricted on the valuation date, then those
an entry starting later will catch, so they can be sold in good time:

    $ python -m folio.compliance restricted --as-of 2026-10-30
    Global Balanced (GBL-BAL)
    Valued 2026-10-30 in GBP

    Restricted holdings
    Instrument  Name                Weight  Listed as  From        Reason
    ----------  ------------------  ------  ---------  ----------  --------------------------------
    TNSL        Tansley Mining plc    0.9%  TNSL       2026-10-01  Thermal coal over 10% of revenue

    Coming onto the list
    Instrument  Name                        Weight  Listed as                From        Reason
    ----------  --------------------------  ------  -----------------------  ----------  -----------------------------
    BRXS30      Brixham Shipping 7.5% 2030    1.8%  issuer Brixham Shipping  2026-11-16  Fleet emissions not disclosed

    restricted.csv on 2026-10-30: 5 entries, 3 in force, 1 lifted, 1 not yet in force

`mandate [--guidelines FILE]` shows the mandate as the tool reads it:

    $ python -m folio.compliance mandate --as-of 2026-10-30
    Mandate for Global Balanced (GBL-BAL)
    Client: Ellesmere Staff Pension Scheme
    From guidelines.toml: 7 guidelines, 7 in force

    Guideline            Covers                                     Limit  Status    Note
    -------------------  -------------------------------------  ---------  --------  -----------------------------------------
    issuer_max_share     each issuer but governments and funds   max 7.0%  in force  Schedule 2, para 1: any one issuer
    country_max_share    each country, direct holdings          max 30.0%  in force  Schedule 2, para 2: country of the issuer
    fund_max_share       each fund                              max 10.0%  in force  Schedule 2, para 3: any one fund
    govt_min_share       government bonds held directly         min 15.0%  in force  Schedule 3, para 1: government bond floor
    max_positions        open positions                            max 40  in force  Schedule 3, para 2
    min_cash_share       cash, all currencies                    min 2.0%  in force  Schedule 3, para 3: cash for withdrawals
    restricted_holdings  names on restricted.csv                none held  in force  Schedule 4: trustees' exclusion list

## Adding a guideline

`folio/compliance/` has a reader per input file (`mandate.py`,
`restricted_list.py`), one module per family of guidelines (`concentration.py`,
`composition.py`, `restricted.py`), the registry, the checker, the text output
and the CLI. To add a guideline, subclass `Guideline` (`guideline.py`) in its
family module with a `key`, a `kind` and `measure()`, add it to `GUIDELINES`
in `registry.py`, and give it a `[guidelines.<key>]` table in the client's
`guidelines.toml`.
