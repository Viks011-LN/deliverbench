"""Shared fixtures.

Most tests run on the sample data folder that ships with folio. Tests that
need exact numbers use ``small_book``: three instruments and some cash with
round values (NAV 25,000 GBP on 2026-10-30).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.calc.valuation import value_portfolio
from folio.config.loader import load_settings
from folio.data.fx_csv import FxRates, load_fx
from folio.data.instruments_csv import load_instruments
from folio.data.positions_json import load_portfolio
from folio.data.prices_csv import PriceHistory, PricePoint, load_prices
from folio.domain.instruments import Bond, Equity, Fund, Universe
from folio.domain.portfolio import Portfolio
from folio.domain.positions import Lot, Position

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 30)
DAY_BEFORE = date(2026, 10, 29)


@pytest.fixture(scope="session")
def settings():
    # cwd=DATA_DIR: there is no folio.toml there, so only the defaults apply.
    return load_settings(cwd=DATA_DIR)


@pytest.fixture(scope="session")
def universe():
    return load_instruments(DATA_DIR / "instruments.csv")


@pytest.fixture(scope="session")
def portfolio():
    return load_portfolio(DATA_DIR / "positions.json")


@pytest.fixture(scope="session")
def prices():
    return load_prices(DATA_DIR / "prices.csv")


@pytest.fixture(scope="session")
def fx():
    return load_fx(DATA_DIR / "fx.csv", pivot="USD", max_age_days=5)


@pytest.fixture(scope="session")
def valuation(universe, portfolio, prices, fx):
    return value_portfolio(portfolio, universe, prices, fx, AS_OF, base_currency="GBP", stale_after_days=3)


@pytest.fixture
def small_book():
    """(universe, portfolio, prices, fx) for a three-line book.

    On 2026-10-30: AAA 1,000 x 12 = 12,000 GBP; BBB 10,000 nominal x 100 / 100
    = 10,000 USD = 8,000 GBP at GBPUSD 1.25; CCC 2,000 x 2 = 4,000 GBP;
    cash 1,000 GBP. NAV 25,000. The day before, AAA was at 10.
    """
    universe = Universe([
        Equity("AAA", "Alpha plc", "Technology", "GBP"),
        Bond("BBB", "Beta 5% 2030", "Government", "USD", issuer="Beta",
             coupon_rate=Decimal("0.05"), maturity=date(2030, 1, 1)),
        Fund("CCC", "Gamma Fund", "Diversified", "GBP", expense_ratio=Decimal("0.01")),
    ])
    book = Portfolio("TEST", "Test book", cash={"GBP": Decimal(1000)})
    opened = date(2026, 1, 5)
    book.add_position(Position("AAA", (Lot(opened, Decimal(1000), Decimal(10)),)))
    book.add_position(Position("BBB", (Lot(opened, Decimal(10000), Decimal(100)),)))
    book.add_position(Position("CCC", (Lot(opened, Decimal(2000), Decimal(2)),)))
    prices = PriceHistory({
        "AAA": [PricePoint(DAY_BEFORE, Decimal(10)), PricePoint(AS_OF, Decimal(12))],
        "BBB": [PricePoint(DAY_BEFORE, Decimal(100)), PricePoint(AS_OF, Decimal(100))],
        "CCC": [PricePoint(DAY_BEFORE, Decimal(2)), PricePoint(AS_OF, Decimal(2))],
    })
    fx = FxRates({("GBP", "USD"): [(DAY_BEFORE, Decimal("1.25")), (AS_OF, Decimal("1.25"))]})
    return universe, book, prices, fx


@pytest.fixture
def small_valuation(small_book):
    universe, book, prices, fx = small_book
    return value_portfolio(book, universe, prices, fx, AS_OF, base_currency="GBP", stale_after_days=3)
