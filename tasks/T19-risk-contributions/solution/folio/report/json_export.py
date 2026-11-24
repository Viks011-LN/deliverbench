"""JSON export of a valuation.

Amounts, prices and quantities are strings so that no consumer reads them as
floats and loses pennies. Weights are plain numbers rounded to six places,
because the dashboards only ever chart them; so is each position's
vol_share, its share of the portfolio's volatility (null when the shares
were not measured).

    {
      "portfolio": {"code": "GBL-BAL", "name": "Global Balanced"},
      "as_of": "2026-10-30",
      "base_currency": "GBP",
      "nav": "20345678.90",
      "positions": [{"instrument": "ADZM", ...}, ...],
      "cash": [{"currency": "GBP", ...}, ...]
    }
"""

from __future__ import annotations

import json
from typing import Any, TextIO

from folio.calc.risk import VolShares
from folio.calc.valuation import CashValue, PositionValue, Valuation
from folio.domain.money import quantize

FX_PLACES = 6


def _weight(value) -> float:
    return round(float(value), 6)


def position_entry(line: PositionValue, money_places: int, vol_share: float | None = None) -> dict[str, Any]:
    instrument = line.instrument
    entry = {
        "instrument": instrument.id,
        "name": instrument.name,
        "kind": instrument.kind,
        "sector": instrument.sector,
        "currency": instrument.currency,
        "quantity": str(line.quantity),
        "price": str(line.price),
        "price_date": line.price_date.isoformat(),
        "stale_price": line.stale,
        "local_value": str(quantize(line.local_value.amount, money_places)),
        "fx_rate": str(quantize(line.fx_rate, FX_PLACES)),
        "base_value": str(quantize(line.base_value.amount, money_places)),
        "vol_share": None if vol_share is None else _weight(vol_share),
        "weight": _weight(line.weight),
    }
    return entry


def cash_entry(cash: CashValue, money_places: int) -> dict[str, Any]:
    return {
        "currency": cash.local_value.currency,
        "amount": str(quantize(cash.local_value.amount, money_places)),
        "fx_rate": str(quantize(cash.fx_rate, FX_PLACES)),
        "base_value": str(quantize(cash.base_value.amount, money_places)),
        "weight": _weight(cash.weight),
    }


def valuation_document(valuation: Valuation, money_places: int = 2, shares: VolShares | None = None) -> dict[str, Any]:
    """The whole export as plain dicts and lists, ready for json.dump()."""
    return {
        "portfolio": {"code": valuation.portfolio_code, "name": valuation.portfolio_name},
        "as_of": valuation.as_of.isoformat(),
        "base_currency": valuation.base_currency,
        "nav": str(quantize(valuation.nav.amount, money_places)),
        "positions": [position_entry(line, money_places, shares.positions[index] if shares is not None else None)
                      for index, line in enumerate(valuation.positions)],
        "cash": [cash_entry(cash, money_places) for cash in valuation.cash],
    }


def write_json(valuation: Valuation, out: TextIO, money_places: int = 2, shares: VolShares | None = None) -> int:
    """Write the document to ``out``; return the number of positions."""
    json.dump(valuation_document(valuation, money_places, shares), out, indent=2)
    out.write("\n")
    return len(valuation.positions)
