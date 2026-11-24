"""The trade and cash ledger behind positions.json.

positions.json says what the portfolio holds; the ledger says how it got
there. It reads two more files from the data folder, trades.csv and
cash_flows.csv, and answers what the positions cannot: what we made on what
we sold (matched first in, first out), where the cash came from, and whether
the trades still add up to the booked positions.

Run it with ``python -m folio.ledger <command>``; see docs/ledger.md. The
folio commands never read the ledger files.
"""
