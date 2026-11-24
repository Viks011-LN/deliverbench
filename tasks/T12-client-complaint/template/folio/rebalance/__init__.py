"""Rebalancing proposals: the trades that bring the book back to its model weights.

Reads two files of its own from the data folder, targets.csv (targets.py)
and trading.toml (dealing.py), next to the four that folio reads. drift.py
measures each target against the book, engine.py turns the targets outside
their band into trades, effect.py shows cash and weights after them, and
text.py and export.py print the result. cli.py is ``python -m folio.rebalance``.

Nothing in folio imports this package, so the files it reads are only needed
when one of its commands runs. See docs/rebalance.md.
"""
