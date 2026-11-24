import io
import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.data.business_days import business_days_between, roll_back
from folio.data.folder import load_folder
from folio.data.fx_csv import FxRates, parse_fx
from folio.data.instruments_csv import parse_instruments
from folio.data.positions_json import parse_portfolio
from folio.data.prices_csv import parse_prices
from folio.domain.instruments import Bond
from folio.errors import DataError, MissingPriceError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = "id,name,kind,sector,currency,coupon_rate,maturity,expense_ratio\n"


def test_sample_instruments(universe):
    assert len(universe) == 40
    assert len(universe.sectors()) == 8
    gilt = universe["UKT34"]
    assert isinstance(gilt, Bond) and gilt.maturity == date(2034, 3, 7)
    assert universe["MXTB29"].issuer_key == "MXTB"
    assert universe["PCRF"].expense_ratio == Decimal("0.0125")


def test_unused_columns_comments_and_trailing_cells():
    universe = parse_instruments(io.StringIO(
        "id,name,kind,sector,currency,rating\n"
        "AAA,Alpha,equity,Energy,gbp,BBB+\n"
        "#OLD,Gone,equity,Energy,GBP,\n"
        "BBB,Beta,equity,Energy,USD,,,\n"))
    assert universe.ids() == ["AAA", "BBB"]
    assert universe["AAA"].currency == "GBP"


@pytest.mark.parametrize("text, message", [
    ("id,name,kind\nA,B,equity\n", "test.csv:1: missing column(s): sector, currency"),
    (HEADER + "A,Alpha,share,Energy,GBP,,,\n", "test.csv:2: unknown kind 'share'"),
    (HEADER + "A,Alpha,equity,Energy,GBP,0.05,,\n", "test.csv:2: A: coupon_rate is only valid for kind bond"),
    (HEADER + "A,Alpha,equity,Energy,GBP,,,\nA,Again,equity,Energy,GBP,,,\n", "test.csv:3: duplicate instrument id A"),
    (HEADER + "A,Alpha,equity,Energy,GBP,,,,surprise\n", "test.csv:2: row has more cells"),
])
def test_instrument_errors_name_file_and_line(text, message):
    with pytest.raises(DataError) as caught:
        parse_instruments(io.StringIO(text), source="test.csv")
    assert str(caught.value).startswith(message)


def test_sample_portfolio(portfolio):
    assert portfolio.code == "GBL-BAL"
    assert len(portfolio.positions) == 39
    assert len(portfolio.open_positions(date(2026, 10, 30))) == 38
    assert portfolio.positions["NYQV"].is_open(date(2026, 8, 19))
    assert not portfolio.positions["NYQV"].is_open(date(2026, 8, 21))


def document(**changes):
    doc = {"portfolio": "P1", "_comment": "ignored",
           "positions": [{"instrument": "AAA", "lots": [{"date": "2026-01-02", "quantity": "10", "price": 5}]}]}
    doc.update(changes)
    return doc


def test_minimal_document():
    book = parse_portfolio(document(cash={"EUR": 100.5}))
    assert (book.name, book.cash) == ("P1", {"EUR": Decimal("100.5")})


@pytest.mark.parametrize("changes, message", [
    ({"positions": []}, "positions: is empty"),
    ({"positions": [{"instrument": "AAA", "lots": [{"date": "2026-01-02", "quantity": "ten", "price": 5}]}]},
     "positions[0].lots[0].quantity: value 'ten' is not a number"),
    ({"positions": [{"instrument": "AAA", "lot": []}]}, "positions[0]: unknown key 'lot'"),
    ({"cash": {"usd": 5}}, "cash.usd: invalid currency code"),
    ({"positions": [{"instrument": "AAA", "lots": [{"date": "2026-01-02", "quantity": 1, "price": 5}]},
                    {"instrument": "AAA", "lots": [{"date": "2026-01-03", "quantity": 1, "price": 5}]}]},
     "positions[1]: portfolio P1: more than one position in AAA"),
])
def test_positions_errors_give_the_json_path(changes, message):
    with pytest.raises(DataError) as caught:
        parse_portfolio(document(**changes), source="p.json")
    assert str(caught.value).startswith(f"p.json: {message}")


def test_latest_price_fills_gaps(prices):
    # 2026-08-31 was a UK bank holiday: no MXTB price, so Friday's is used.
    assert prices.latest("MXTB", date(2026, 8, 31)).day == date(2026, 8, 28)
    assert prices.latest("PCRF", date(2026, 10, 29)).day == date(2026, 9, 30)  # prices monthly
    with pytest.raises(MissingPriceError, match="no price for PCRF on or before 2026-06-15"):
        prices.latest("PCRF", date(2026, 6, 15))
    october = prices.history("IXFR", date(2026, 10, 1), date(2026, 10, 31))
    assert [point.day.day for point in october] == [2, 9, 16, 23, 30]  # prices on Fridays


@pytest.mark.parametrize("text, message", [
    ("day,A\n", "p.csv:1: the first column must be 'date'"),
    ("date,A\n2026-10-31,1\n", "p.csv:2: 2026-10-31 is a Saturday"),
    ("date,A\n2026-10-30,1\n2026-10-29,1\n", "p.csv:3: dates must increase"),
    ("date,A\n2026-10-30,-1\n", "p.csv:2: price of A must be positive"),
])
def test_price_errors(text, message):
    with pytest.raises(DataError) as caught:
        parse_prices(io.StringIO(text), source="p.csv")
    assert str(caught.value).startswith(message)


def test_price_jumps():
    prices = parse_prices(io.StringIO("date,A,B\n2026-10-28,10,5\n2026-10-29,10.5,\n2026-10-30,4,7.5\n"))
    assert prices.jumps(Decimal("0.4")) == [("A", date(2026, 10, 30), Decimal(4) / Decimal("10.5") - 1),
                                            ("B", date(2026, 10, 30), Decimal("0.5"))]


def test_direct_inverse_and_cross_rates(fx):
    day = date(2026, 10, 30)
    eurusd, gbpusd = fx.rate("EUR", "USD", day), fx.rate("GBP", "USD", day)
    assert fx.rate("USD", "GBP", day) == 1 / gbpusd
    assert fx.rate("EUR", "GBP", day) == eurusd * (1 / gbpusd)
    assert fx.currencies() == ["EUR", "GBP", "JPY", "USD"]
    # No GBPUSD fixing on the UK holiday; Friday's is 3 days old, within the limit.
    assert fx.rate("GBP", "USD", date(2026, 8, 31)) == fx.rate("GBP", "USD", date(2026, 8, 28))


def test_stale_and_missing_fx():
    rates = FxRates({("EUR", "USD"): [(date(2026, 10, 1), Decimal("1.1"))]}, max_age_days=5)
    with pytest.raises(MissingPriceError, match="11 days old"):
        rates.rate("EUR", "USD", date(2026, 10, 12))
    with pytest.raises(MissingPriceError, match="without USDCHF"):
        rates.rate("EUR", "CHF", date(2026, 10, 2))
    with pytest.raises(DataError, match="fx.csv:1: pair USDEUR appears twice"):
        parse_fx(io.StringIO("date,EURUSD,USDEUR\n"), source="fx.csv")


def test_business_days():
    friday, monday = date(2026, 10, 30), date(2026, 11, 2)
    assert roll_back(date(2026, 10, 31)) == friday
    assert (business_days_between(friday, monday), business_days_between(monday, friday)) == (1, -1)
    assert business_days_between(friday, date(2026, 11, 13), holidays={date(2026, 11, 11)}) == 9


@pytest.fixture
def folder_copy(tmp_path):
    for name in ("instruments.csv", "positions.json", "prices.csv", "fx.csv"):
        shutil.copy(DATA_DIR / name, tmp_path / name)
    return tmp_path


def test_sample_folder_loads_cleanly():
    data = load_folder(DATA_DIR, base_currency="GBP", max_rate_age_days=5)
    assert data.warnings == []
    assert len(data.universe) == 40


def test_folder_cross_checks(folder_copy):
    positions = json.loads((folder_copy / "positions.json").read_text())
    positions["positions"].append({"instrument": "NEWCO", "lots": [{"date": "2026-10-01", "quantity": 1, "price": 1}]})
    (folder_copy / "positions.json").write_text(json.dumps(positions))
    with pytest.raises(DataError, match="holds instruments missing from instruments.csv: NEWCO"):
        load_folder(folder_copy, base_currency="GBP")
    with open(folder_copy / "instruments.csv", "a") as handle:
        handle.write("NEWCO,New Co plc,equity,Industrials,CHF,CH,,,,,\n")
    with pytest.raises(DataError, match="prices.csv has no prices for NEWCO"):
        load_folder(folder_copy, base_currency="GBP")
    (folder_copy / "fx.csv").unlink()
    with pytest.raises(DataError, match="has no fx.csv"):
        load_folder(folder_copy, base_currency="GBP")
    with pytest.raises(DataError, match="data folder not found"):
        load_folder(folder_copy / "nowhere", base_currency="GBP")
