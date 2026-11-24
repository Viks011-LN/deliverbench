"""Stress scenarios: what would the book lose if prices, currencies or yields moved?

``python -m folio.scenarios`` reads named what-if scenarios from
scenarios.toml in the data folder, revalues today's book under each one and
shows the P&L by sector, currency or kind, compares the scenarios with each
other or exports them line by line. See docs/scenarios.md.

The package sits on top of the core and only its own command imports it:
plain ``folio`` commands never read the scenario file.
"""
