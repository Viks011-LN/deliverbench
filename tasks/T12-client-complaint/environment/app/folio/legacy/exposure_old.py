"""Sector exposure as folio 0.3 computed it.

DEPRECATED: use folio.calc.exposure.by_sector. Kept because the quarterly
reconciliation script compares old and new numbers until Q1 2027.

The differences are deliberate and are why the numbers do not match:

* it sums local-currency values with no FX conversion;
* shares are of gross invested value (absolute values, no cash), not NAV;
* bond prices are treated like equity prices (no per-100 quoting);
* the result is a plain dict, in no particular order.
"""

import warnings


def exposure_by_sector(quantities, prices, sectors):
    """Share of gross invested value per sector.

    quantities: {instrument_id: quantity}
    prices:     {instrument_id: price}
    sectors:    {instrument_id: sector}
    """
    warnings.warn(
        "folio.legacy.exposure_old is deprecated; use folio.calc.exposure.by_sector",
        DeprecationWarning,
        stacklevel=2,
    )
    gross = {}
    for instrument_id, quantity in quantities.items():
        if instrument_id not in prices:
            raise KeyError("no price for %s" % instrument_id)
        sector = sectors.get(instrument_id, "Unknown")
        gross[sector] = gross.get(sector, 0.0) + abs(float(quantity) * float(prices[instrument_id]))
    total = sum(gross.values())
    if total == 0:
        return {}
    return dict((sector, value / total) for sector, value in gross.items())


def max_share_breaches(shares, max_share):
    """Sectors above ``max_share`` (the v1 single limit), largest first."""
    over = [(sector, share) for sector, share in shares.items() if share > max_share]
    return sorted(over, key=lambda item: (-item[1], item[0]))
