"""Composition guidelines: the shape of the whole book rather than any one name.

Each of these reads exactly one figure for the whole portfolio:

* ``govt_min_share``: government bonds held directly must be at least the
  limit of NAV. Government bond funds do not count; the client wants a floor
  of bonds it can see, not a fund's word for it. A government bond is a bond
  in the Government sector (guideline.GOVERNMENT_SECTOR).
* ``max_positions``: no more open positions than the limit, so that every
  line in the book still gets looked at. Cash balances are not positions.
* ``min_cash_share``: cash in all currencies together must be at least the
  limit of NAV, so that the client's withdrawals can be paid without selling
  in a hurry.
"""

from __future__ import annotations

from decimal import Decimal

from folio.aggregate.rollup import share
from folio.compliance.guideline import MAX_COUNT, MIN_SHARE, Guideline, is_government_bond

GOVERNMENT_BONDS = "government bonds"
POSITIONS = "positions"
CASH = "cash"


class GovtMinShare(Guideline):
    """Government bonds held directly must be at least the limit of NAV."""

    key = "govt_min_share"
    kind = MIN_SHARE
    title = "government bonds held directly"

    def measure(self, valuation):
        total = sum((line.base_value.amount for line in valuation.positions
                     if is_government_bond(line.instrument)), Decimal(0))
        return [self.reading(GOVERNMENT_BONDS, share(total, valuation.nav.amount))]


class MaxPositions(Guideline):
    """No more than the limit of open positions; cash balances do not count."""

    key = "max_positions"
    kind = MAX_COUNT
    title = "open positions"

    def measure(self, valuation):
        return [self.reading(POSITIONS, Decimal(len(valuation.positions)))]


class MinCashShare(Guideline):
    """Cash, all currencies together, must be at least the limit of NAV."""

    key = "min_cash_share"
    kind = MIN_SHARE
    title = "cash, all currencies"

    def measure(self, valuation):
        return [self.reading(CASH, share(valuation.cash_total.amount, valuation.nav.amount))]
