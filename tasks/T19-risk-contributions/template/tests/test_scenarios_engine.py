import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from folio.calc import bonds, exposure
from folio.calc.valuation import value_portfolio
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory, PricePoint
from folio.errors import RiskError
from folio.scenarios import csv_output, text_output
from folio.scenarios.engine import Stresser
from folio.scenarios.grouping import group_pnl
from folio.scenarios.shocks import FxShock, HistoricalSpec, PriceShock, Scenario, Window, YieldShift

AS_OF = date(2026, 10, 30)
WEEK = [date(2026, 10, 26) + timedelta(days=i) for i in range(5)]  # Monday 26 to Friday 30 October 2026


def equity_crash(**extra):
    return Scenario("crash", "Equities -20%", prices=(PriceShock("kind", "equity", Decimal("-0.2")),), **extra)


def run(valuation, scenario, prices=None, fx=None):
    return Stresser(valuation, prices, fx).run(scenario)


def test_price_shocks_compound(small_valuation):
    scenario = Scenario("tech", prices=(PriceShock("kind", "equity", Decimal("-0.2")),
                                        PriceShock("sector", "Technology", Decimal("-0.1"))))
    result = run(small_valuation, scenario)
    aaa, bbb, ccc = result.positions
    assert aaa.price_change == Decimal("-0.28")  # 0.8 x 0.9 - 1, not -0.30
    assert aaa.stressed_value.amount == Decimal(8640)
    assert (bbb.pnl.amount, ccc.pnl.amount) == (0, 0)
    assert result.pnl.amount == Decimal(-3360)
    assert result.pnl_share == Decimal("-0.1344")
    assert result.stressed_nav.amount == Decimal(21640)
    assert result.worst_position().line.instrument.id == "AAA"


def test_fx_shock_moves_positions_and_cash_in_that_currency(small_book):
    universe, book, prices, fx = small_book
    book.cash["USD"] = Decimal(500)  # 400 GBP at GBPUSD 1.25
    valuation = value_portfolio(book, universe, prices, fx, AS_OF, base_currency="GBP", stale_after_days=3)
    result = run(valuation, Scenario("usd", fx=(FxShock("USD", Decimal("-0.1")),)))
    assert [line.pnl.amount for line in result.positions] == [0, Decimal(-800), 0]
    assert [(cash.currency, cash.pnl.amount) for cash in result.cash] == [("GBP", 0), ("USD", Decimal(-40))]
    assert result.pnl.amount == Decimal(-840)
    assert result.worst_position().line.instrument.id == "BBB"


def test_yield_shift_goes_through_modified_duration(small_valuation):
    (risk,) = bonds.bond_risks(small_valuation)
    result = run(small_valuation, Scenario("up", yields=(YieldShift(Decimal(100)),)))
    bbb = result.positions[1]
    assert float(bbb.price_change) == pytest.approx(-risk.modified_duration / 100)
    assert float(result.pnl.amount) == pytest.approx(-8000 * risk.modified_duration / 100)
    assert result.positions[0].pnl.amount == result.positions[2].pnl.amount == 0  # no duration, no move
    sterling_only = run(small_valuation, Scenario("gbp", yields=(YieldShift(Decimal(100), "GBP"),)))
    assert sterling_only.pnl.amount == 0  # BBB is a USD bond


def test_yield_shift_price_change_never_below_minus_one():
    assert YieldShift(Decimal(200)).price_change(Decimal(5)) == Decimal("-0.1")
    assert YieldShift(Decimal(1000)).price_change(Decimal(15)) == Decimal(-1)
    assert YieldShift(Decimal(-50)).price_change(Decimal(4)) == Decimal("0.02")


def test_nothing_lost_means_no_worst_position(small_valuation):
    result = run(small_valuation, Scenario("up", prices=(PriceShock("sector", "Technology", Decimal("0.1")),)))
    assert result.pnl.amount == Decimal(1200)
    assert result.worst_position() is None


@pytest.fixture
def history_book(small_book):
    """small_book with five days of history: AAA dips on the 27th, the dollar on the 28th."""
    universe, book, _, _ = small_book
    closes = {"AAA": [10, 9, "9.5", 10, 12], "BBB": [100, 100, 98, 99, 100], "CCC": [2, 2, 2, 2, 2]}
    prices = PriceHistory({key: [PricePoint(day, Decimal(str(close))) for day, close in zip(WEEK, values)]
                           for key, values in closes.items()})
    fx = FxRates({("GBP", "USD"): [(day, Decimal(rate)) for day, rate in
                                   zip(WEEK, ["1.25", "1.25", "1.30", "1.25", "1.25"])]})
    valuation = value_portfolio(book, universe, prices, fx, AS_OF, base_currency="GBP", stale_after_days=3)
    return valuation, prices, fx


def replay(history_book, days, scope):
    valuation, prices, fx = history_book
    return run(valuation, Scenario("replay", historical=HistoricalSpec(days, scope)), prices, fx)


def test_book_replay_finds_the_worst_window(history_book):
    one_day = replay(history_book, 1, "book")
    assert one_day.window == Window(WEEK[0], WEEK[1])
    assert one_day.pnl.amount == Decimal(-1200)  # AAA 10 -> 9 on 12,000 GBP
    two_days = replay(history_book, 2, "book")
    assert two_days.window == Window(WEEK[0], WEEK[2])
    aaa, bbb, _ = two_days.positions
    assert aaa.price_change == Decimal("-0.05")
    assert bbb.price_change == Decimal("-0.02")
    assert float(bbb.fx_change) == pytest.approx(1.25 / 1.30 - 1)  # USD worth less in GBP
    assert float(two_days.pnl.amount) == pytest.approx(-600 + 8000 * (0.98 * 1.25 / 1.30 - 1))
    assert all(line.window == two_days.window for line in two_days.positions)


def test_instrument_replay_takes_each_worst_move_on_its_own_dates(history_book):
    result = replay(history_book, 1, "instrument")
    assert result.window is None
    moves = {line.line.instrument.id: (line.price_change, line.window) for line in result.positions}
    assert moves == {
        "AAA": (Decimal("-0.1"), Window(WEEK[0], WEEK[1])),
        "BBB": (Decimal("-0.02"), Window(WEEK[1], WEEK[2])),
        "CCC": (Decimal(0), Window(WEEK[0], WEEK[1])),  # never moved: the earliest window
    }
    assert all(line.fx_change == 0 for line in result.positions)
    assert result.pnl.amount == Decimal(-1360)


def test_replay_needs_enough_history(history_book):
    with pytest.raises(RiskError, match="a 5-day move needs 6 price dates, but the book has prices on only 5"):
        replay(history_book, 5, "book")
    with pytest.raises(RiskError, match="but AAA has prices on only 5 up to 2026-10-30"):
        replay(history_book, 5, "instrument")


def test_group_by_sector_currency_and_kind(small_valuation):
    result = run(small_valuation, equity_crash(fx=(FxShock("USD", Decimal("-0.1")),)))

    by_sector = group_pnl(result, exposure.DIMENSIONS["sector"])
    assert [(row.key, row.pnl.amount) for row in by_sector.rows] == [
        ("Technology", Decimal(-2400)), ("Government", Decimal(-800)), ("Diversified", 0)]
    assert (by_sector.cash.key, by_sector.cash.positions, by_sector.cash.pnl.amount) == ("Cash", 0, 0)
    assert (by_sector.total.positions, by_sector.total.pnl.amount) == (3, Decimal(-3200))
    assert by_sector.total.share == Decimal("-0.128")

    by_currency = group_pnl(result, exposure.DIMENSIONS["currency"])
    assert by_currency.cash is None  # cash joins its currency's row
    gbp = by_currency.row("GBP")
    assert (gbp.positions, gbp.value.amount, gbp.pnl.amount) == (2, Decimal(17000), Decimal(-2400))

    fund_crash = run(small_valuation, Scenario("funds", prices=(PriceShock("kind", "fund", Decimal("-0.5")),)))
    by_kind = group_pnl(fund_crash, exposure.DIMENSIONS["kind"])
    assert [row.key for row in by_kind.rows] == ["equity", "bond", "fund"]  # fixed order, not worst first


def test_groups_and_cash_add_up_on_the_sample(valuation, prices, fx):
    stresser = Stresser(valuation, prices, fx)
    scenario = Scenario("mixed", prices=(PriceShock("sector", "Energy", Decimal("0.2")),),
                        fx=(FxShock("EUR", Decimal("-0.05")),), yields=(YieldShift(Decimal(50)),))
    for result in (stresser.run(scenario), stresser.run(Scenario("week", historical=HistoricalSpec(5)))):
        for dimension in exposure.DIMENSIONS.values():
            breakdown = group_pnl(result, dimension)
            parts = [row.pnl.amount for row in breakdown.rows]
            parts += [breakdown.cash.pnl.amount] if breakdown.cash is not None else []
            assert sum(parts) == pytest.approx(result.pnl.amount), dimension.name
            assert breakdown.total.positions == len(valuation.positions)


def test_run_report_format(small_valuation, settings):
    result = run(small_valuation, equity_crash())
    text = text_output.render_run(result, group_pnl(result, exposure.SECTOR), settings.report)
    assert text == (
        "Test book (TEST)\n"
        "Valued 2026-10-30 in GBP\n"
        "\n"
        "Scenario crash: Equities -20%\n"
        "Shocks: kind equity -20%\n"
        "\n"
        "P&L by sector\n"
        "Sector       Positions  Value (GBP)   Stressed        P&L  Of NAV\n"
        "-----------  ---------  -----------  ---------  ---------  ------\n"
        "Technology           1    12,000.00   9,600.00  -2,400.00  -9.60%\n"
        "Diversified          1     4,000.00   4,000.00       0.00   0.00%\n"
        "Government           1     8,000.00   8,000.00       0.00   0.00%\n"
        "Cash                       1,000.00   1,000.00       0.00   0.00%\n"
        "-----------  ---------  -----------  ---------  ---------  ------\n"
        "Total                3    25,000.00  22,600.00  -2,400.00  -9.60%\n"
        "\n"
        "NAV after the scenario: GBP 22,600.00 (-9.60%)\n"
    )


def test_csv_has_a_row_per_holding_and_scenario(small_valuation):
    stresser = Stresser(small_valuation, None, None)
    results = stresser.run_all([equity_crash(), Scenario("a-dollar", fx=(FxShock("USD", Decimal("0.1")),))])
    out = io.StringIO()
    assert csv_output.write_csv(results, out) == 8
    rows = list(csv.DictReader(io.StringIO(out.getvalue())))
    assert out.getvalue().splitlines()[0] == ",".join(csv_output.COLUMNS)
    assert [row["scenario"] for row in rows] == ["a-dollar"] * 4 + ["crash"] * 4  # name order
    assert [row["instrument"] for row in rows[:4]] == ["AAA", "BBB", "CCC", "CASH"]
    bbb = rows[1]
    assert (bbb["fx_change"], bbb["stressed_value"], bbb["pnl"], bbb["pnl_share"]) == (
        "0.100000", "8800.00", "800.00", "0.032000")
    assert rows[3]["kind"] == "cash" and rows[3]["window_start"] == ""
    for result in results:
        mine = [Decimal(row["pnl"]) for row in rows if row["scenario"] == result.scenario.name]
        assert sum(mine) == result.pnl.amount
