"""The data folder: the four input files, loaded together and checked against each other.

Each adapter checks its own file. This module checks what no single file can:

* every position is in an instrument that instruments.csv knows;
* every position still open has prices;
* fx.csv can convert every currency we hold, and the base currency.

Those are errors. Two things are only warnings, because they are usually
harmless: price columns for instruments nobody has set up yet (a new listing
being priced ahead of time), and day-on-day price moves larger than
JUMP_WARNING (a corporate action, or now and then a typo in the file).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from folio.data.fx_csv import FxRates, load_fx
from folio.data.instruments_csv import load_instruments
from folio.data.positions_json import load_portfolio
from folio.data.prices_csv import PriceHistory, load_prices
from folio.domain.instruments import Universe
from folio.domain.portfolio import Portfolio
from folio.errors import DataError

FILES = {
    "instruments": "instruments.csv",
    "positions": "positions.json",
    "prices": "prices.csv",
    "fx": "fx.csv",
}

JUMP_WARNING = Decimal("0.4")  # a 40% move in one day is worth a second look


@dataclass
class DataFolder:
    """Everything read from one data folder, plus the warnings cross_check() found."""

    path: Path
    universe: Universe
    portfolio: Portfolio
    prices: PriceHistory
    fx: FxRates
    warnings: list[str] = field(default_factory=list)


def load_folder(path, *, base_currency: str, pivot: str = "USD", max_rate_age_days: int | None = None) -> DataFolder:
    """Load and cross-check the files in ``path``. Raises DataError on the first real problem."""
    folder = Path(path)
    if not folder.is_dir():
        raise DataError(f"data folder not found: {folder} (use --data-dir)")
    absent = [name for name in FILES.values() if not (folder / name).is_file()]
    if absent:
        raise DataError(f"data folder {folder} has no {', '.join(absent)}")
    data = DataFolder(
        path=folder,
        universe=load_instruments(folder / FILES["instruments"]),
        portfolio=load_portfolio(folder / FILES["positions"]),
        prices=load_prices(folder / FILES["prices"]),
        fx=load_fx(folder / FILES["fx"], pivot=pivot, max_age_days=max_rate_age_days),
    )
    data.warnings.extend(cross_check(data, base_currency))
    return data


def cross_check(data: DataFolder, base_currency: str) -> list[str]:
    """Raise DataError for problems that would break a run; return warnings for the rest."""
    positions, instruments, prices = FILES["positions"], FILES["instruments"], FILES["prices"]
    unknown = data.portfolio.unknown_instruments(data.universe)
    if unknown:
        raise DataError(f"{positions} holds instruments missing from {instruments}: {', '.join(unknown)}")

    unpriced = sorted(
        instrument_id for instrument_id, position in data.portfolio.positions.items()
        if position.is_open() and instrument_id not in data.prices
    )
    if unpriced:
        raise DataError(f"{prices} has no prices for {', '.join(unpriced)}, which {positions} holds")

    needed = {base_currency} | set(data.portfolio.cash)
    needed |= {data.universe[instrument_id].currency for instrument_id in data.portfolio.positions}
    missing = sorted(needed - set(data.fx.currencies()))
    if missing:
        raise DataError(f"{FILES['fx']} has no rates for {', '.join(missing)}")

    warnings = []
    strays = sorted(set(data.prices.instruments()) - set(data.universe.ids()))
    if strays:
        warnings.append(f"{prices} has prices for instruments not in {instruments}: {', '.join(strays)}")
    for instrument_id, day, move in data.prices.jumps(JUMP_WARNING):
        warnings.append(f"{instrument_id} moved {move * 100:+.0f}% on {day}; check {prices}")
    return warnings
