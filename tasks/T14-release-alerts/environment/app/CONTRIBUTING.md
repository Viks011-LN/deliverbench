# Contributing to alertd

alertd decides what reaches the desk while it is trading, so changes are small, reviewed and tested.

## Before you hand in a change

- The whole suite passes: `python -m pytest`.
- Existing tests are not edited to make a change pass. If a test is wrong, say so in the review and change it in
  a change of its own.
- What alertd prints is part of its interface: the desk reads the messages, the morning note reads the digest, and
  the support team reads `explain`. A change that alters what an existing alert prints says so in its title.
- `docs/CHANGELOG.md` gets a line for anything a user of alertd would notice.

## Code

- Standard library only; Python 3.11 or later.
- Kinds are independent of each other: a change for one kind does not touch another kind's rule or settings.
- Shared behaviour (the suppressions, the house style, the settings rules) lives in one place each:
  `alertd/suppress.py`, `alertd/format.py`, `alertd/config.py`. A change there changes every kind, and is reviewed
  as such.
- Times are UTC everywhere (`alertd/timeutil.py`).

## Settings

- Every setting is declared, with its default, in `alertd/defaults.toml`; `docs/settings.md` describes it.
- Settings are renamed or moved only with the desk's agreement, since the desk's own config (and the copies of it
  in other teams' tools) would stop loading.

## Desk pages

The rules for each kind of alert are the desk's, in `docs/desk/`. The code follows the page. Where the page leaves
something open, ask the desk; do not decide it in code.
