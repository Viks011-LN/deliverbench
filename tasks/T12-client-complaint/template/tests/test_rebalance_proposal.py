"""Drift, the proposal engine, its effect, and the text and CSV output.

Exact numbers use small_book (NAV 25,000 GBP): AAA 48%, BBB 32% (a USD bond
at GBPUSD 1.25, so 0.8 GBP per USD), CCC 16% and cash 4%.
"""

import csv
import io
import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from folio.calc.valuation import value_portfolio
from folio.data.prices_csv import PriceHistory, PricePoint
from folio.domain.instruments import Equity
from folio.domain.money import Money
from folio.errors import DataError
from folio.rebalance import engine, export, text
from folio.rebalance.dealing import load_rules, parse_rules
from folio.rebalance.drift import cash_weight_of, holdings_of, measure_drift
from folio.rebalance.effect import effect_of
from folio.rebalance.engine import propose
from folio.rebalance.sizing import Quotes
from folio.rebalance.targets import load_targets, parse_targets

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 10, 30)
HEADER = "scope,key,weight,band\n"
MODEL = HEADER + ("instrument,AAA,0.40,0.02\nsector,Government,0.36,0.02\n"
                  "instrument,CCC,0.20,0.01\ncash,,0.04,0.01\n")
RULES = "min_ticket = 500\ncash_buffer = 0.02\n[lots]\nequity = 10\nbond = 1000\nfund = 100\n"


def targets_for(universe, text=MODEL):
    return parse_targets(text.splitlines(), universe, source="targets.csv")


def rules_for(universe, text=RULES):
    return parse_rules(tomllib.loads(text), universe, "GBP", source="trading.toml")


def run(book, model=MODEL, rules=RULES):
    universe, portfolio, prices, fx = book
    valuation = value_portfolio(portfolio, universe, prices, fx, AS_OF, base_currency="GBP", stale_after_days=3)
    quotes = Quotes(valuation, universe, prices, fx)
    return propose(valuation, targets_for(universe, model), rules_for(universe, rules), quotes)


def trade_list(proposal):
    return [(trade.side, trade.instrument.id, trade.quantity) for trade in proposal.trades]


@pytest.fixture
def wider_book(small_book):
    """small_book plus DDD, an Energy share priced at 5 GBP that the book does not hold."""
    universe, portfolio, prices, fx = small_book
    universe.add(Equity(id="DDD", name="Delta Energy plc", sector="Energy", currency="GBP"))
    series = {key: prices.history(key, AS_OF, AS_OF) for key in prices.instruments()}
    series["DDD"] = [PricePoint(AS_OF, Decimal(5))]
    return universe, portfolio, PriceHistory(series), fx


def test_drift_on_the_small_book(small_book, small_valuation):
    model = targets_for(small_book[0])
    drifts = measure_drift(model, holdings_of(small_valuation), cash_weight_of(small_valuation))
    assert [(d.target.label, d.current, d.drift, d.outside) for d in drifts] == [
        ("AAA", Decimal("0.48"), Decimal("0.08"), True),
        ("CCC", Decimal("0.16"), Decimal("-0.04"), True),
        ("Government", Decimal("0.32"), Decimal("-0.04"), True),
        ("Cash", Decimal("0.04"), Decimal("0"), False),
    ]
    assert drifts[2].members == ("BBB",)


def test_a_drift_on_the_band_edge_does_not_trade(small_book, settings):
    model = HEADER + "instrument,AAA,0.46,0.02\nsector,Government,0.34,0.02\ninstrument,CCC,0.16,0\ncash,,0.04,0\n"
    proposal = run(small_book, model)
    assert not any(drift.outside for drift in proposal.before)
    assert proposal.trades == () and proposal.skipped == ()
    report = text.render_proposal(proposal, effect_of(proposal), settings.report)
    assert "No trades: every target is inside its band." in report.splitlines()
    assert "Left out" not in report


def test_every_holding_needs_a_target(small_book):
    model = HEADER + "instrument,AAA,0.48,0.02\nsector,Government,0.48,0.02\ncash,,0.04,0.01\n"
    with pytest.raises(DataError, match=r"^targets\.csv: held but covered by no target: CCC \(Diversified\)"):
        run(small_book, model)


def test_proposal_on_the_small_book(small_book):
    proposal = run(small_book)
    # AAA: 2,000 GBP too much is 166.7 shares, 17 lots of 10. BBB: 1,000 GBP short is
    # 1,250 USD of nominal, one lot of 1,000. CCC: 1,000 GBP short is 500 units.
    assert trade_list(proposal) == [("sell", "AAA", 170), ("buy", "CCC", 500), ("buy", "BBB", 1000)]
    sell, fund, bond = proposal.trades
    assert sell.base_value == Money(2040, "GBP")
    assert (sell.weight_before, sell.weight_after) == (Decimal("0.48"), Decimal("0.3984"))
    assert bond.local_value == Money(1000, "USD") and bond.base_value == Money(800, "GBP")
    assert (bond.target.label, bond.weight_after) == ("Government", Decimal("0.352"))
    assert fund.weight_after == Decimal("0.2")
    assert proposal.total(engine.SELL) == Money(2040, "GBP")
    assert proposal.total(engine.BUY) == Money(1800, "GBP")
    assert proposal.traded_share == Decimal("0.1536")
    assert proposal.skipped == () and proposal.buy_scale is None


def test_the_cash_effect_by_currency(small_book):
    effect = effect_of(run(small_book))
    moves = {move.currency: (move.before, move.sold, move.bought, move.after) for move in effect.cash}
    assert moves == {
        "GBP": (Money(1000, "GBP"), Money(2040, "GBP"), Money(1000, "GBP"), Money(2040, "GBP")),
        "USD": (Money(0, "USD"), Money(0, "USD"), Money(1000, "USD"), Money(-1000, "USD")),
    }
    assert effect.short_currencies == ["USD"]
    assert effect.cash_after == Money(1240, "GBP")
    assert effect.cash_weight == Decimal("0.0496")
    assert [(instrument.id, weight) for instrument, weight in effect.holdings] == [
        ("AAA", Decimal("0.3984")), ("BBB", Decimal("0.352")), ("CCC", Decimal("0.2"))]
    assert not any(drift.outside for drift in effect.after)


def test_trades_under_the_minimum_ticket_are_left_out(small_book):
    proposal = run(small_book, rules=RULES.replace("min_ticket = 500", "min_ticket = 900"))
    assert trade_list(proposal) == [("sell", "AAA", 170), ("buy", "CCC", 500)]
    [left] = proposal.skipped
    assert (left.instrument.id, left.side, left.quantity, left.base_value) == ("BBB", "buy", 1000, Money(800, "GBP"))
    assert left.reason == engine.UNDER_TICKET
    after = {drift.target.label: drift for drift in effect_of(proposal).after}
    assert after["Government"].outside


def test_a_trade_smaller_than_one_lot_is_left_out(small_book):
    proposal = run(small_book, rules=RULES.replace("bond = 1000", "bond = 5000"))
    [left] = proposal.skipped
    assert (left.instrument.id, left.quantity, left.base_value) == ("BBB", 0, Money(1000, "GBP"))
    assert left.reason == engine.UNDER_LOT


def test_buys_are_cut_to_keep_the_cash_buffer(small_book):
    # Floor 2,500 GBP; cash 1,000 + 2,040 from the sale leaves 540 for 1,800 of buys.
    rules = "min_ticket = 100\ncash_buffer = 0.10\n[lots]\nequity = 10\nbond = 1000\nfund = 50\n"
    proposal = run(small_book, rules=rules)
    assert proposal.buy_scale == Decimal("0.3")
    assert trade_list(proposal) == [("sell", "AAA", 170), ("buy", "CCC", 150)]
    [left] = proposal.skipped
    assert (left.instrument.id, left.base_value, left.reason) == ("BBB", Money(240, "GBP"), engine.CUT_TO_NOTHING)
    assert effect_of(proposal).cash_after == Money(2740, "GBP")


def test_no_buys_when_cash_starts_below_the_buffer(small_book):
    model = HEADER + "instrument,AAA,0.48,0.02\nsector,Government,0.36,0.02\ninstrument,CCC,0.16,0.01\ncash,,0,0.05\n"
    proposal = run(small_book, model, RULES.replace("cash_buffer = 0.02", "cash_buffer = 0.05"))
    assert proposal.trades == () and proposal.buy_scale == 0
    assert [(item.instrument.id, item.reason) for item in proposal.skipped] == [("BBB", engine.CUT_TO_NOTHING)]


def test_a_zero_weight_sells_the_whole_holding(small_book):
    model = HEADER + "instrument,AAA,0,0.02\nsector,Government,0.6,0.02\ninstrument,CCC,0.36,0.01\ncash,,0.04,0.01\n"
    proposal = run(small_book, model, RULES.replace("equity = 10", "equity = 300"))
    sale = proposal.sells[0]
    assert (sale.instrument.id, sale.quantity, sale.weight_after) == ("AAA", 1000, 0)  # not a multiple of 300
    assert [trade.instrument.id for trade in proposal.buys] == ["BBB", "CCC"]
    assert "AAA" not in [instrument.id for instrument, _ in effect_of(proposal).holdings]


def test_bonds_in_any_nominal(small_book):
    proposal = run(small_book, rules="bonds_in_nominal_multiples = false\n" + RULES)
    bond = next(trade for trade in proposal.trades if trade.instrument.id == "BBB")
    assert bond.quantity == 1250 and bond.base_value == Money(1000, "GBP")


def test_an_instrument_target_can_buy_a_new_name(wider_book):
    model = HEADER + ("instrument,AAA,0.40,0.02\nsector,Government,0.32,0.02\ninstrument,CCC,0.16,0.01\n"
                      "instrument,DDD,0.08,0.01\ncash,,0.04,0.01\n")
    proposal = run(wider_book, model)
    assert trade_list(proposal) == [("sell", "AAA", 170), ("buy", "DDD", 400)]
    new = proposal.buys[0]
    assert (new.price, new.weight_before, new.weight_after) == (Decimal(5), 0, Decimal("0.08"))


def test_a_sector_target_with_nothing_held_cannot_be_spread(wider_book):
    model = HEADER + ("instrument,AAA,0.40,0.02\nsector,Government,0.32,0.02\ninstrument,CCC,0.16,0.01\n"
                      "sector,Energy,0.08,0.01\ncash,,0.04,0.01\n")
    with pytest.raises(DataError, match=r"^targets\.csv:5: sector Energy has a model weight of 0\.08 but the book"):
        run(wider_book, model)


def test_sample_proposal_spreads_sectors_and_sells_first(valuation, universe, prices, fx):
    model = load_targets(DATA_DIR / "targets.csv", universe)
    rules = load_rules(DATA_DIR / "trading.toml", universe, "GBP").with_overrides(min_ticket=Decimal(0))
    proposal = propose(valuation, model, rules, Quotes(valuation, universe, prices, fx))
    sides = [trade.side for trade in proposal.trades]
    assert sides == sorted(sides, key=[engine.SELL, engine.BUY].index)
    assert {trade.target.label for trade in proposal.trades} == {
        drift.target.label for drift in proposal.before if drift.outside}

    technology = next(drift for drift in proposal.before if drift.target.label == "Technology")
    trades = {trade.instrument.id: trade for trade in proposal.trades if trade.target.label == "Technology"}
    assert sorted(trades) == list(technology.members)
    for trade in trades.values():
        # Each holding keeps its share of the sector, give or take half a round lot.
        wanted = trade.target.weight * trade.weight_before / technology.current
        lot_weight = rules.lot_for(trade.instrument) * trade.base_value.amount / trade.quantity / valuation.nav.amount
        assert abs(trade.weight_after - wanted) <= lot_weight / 2


def test_text_report_of_the_proposal(small_book, settings):
    proposal = run(small_book)
    lines = text.render_proposal(proposal, effect_of(proposal), settings.report).splitlines()
    assert lines[3] == "Proposed trades (minimum ticket GBP 500.00, cash buffer 2.0% of NAV)"
    assert lines[6].split() == ["sell", "AAA", "equity", "GBP", "170", "12", "2,040.00", "48.0%", "39.8%", "AAA"]
    assert lines[8].split() == ["buy", "BBB", "bond", "USD", "1,000", "100", "800.00", "32.0%", "35.2%", "Government"]
    assert "Sells GBP 2,040.00, buys GBP 1,800.00, net cash +240.00; 15.4% of NAV traded." in lines
    assert "Cash after: 5.0% of NAV (model 4.0%, buffer 2.0%)." in lines
    assert "USD ends below zero: buy it against another currency before the trades settle." in lines
    assert lines[-1] == "Every target is inside its band."


def test_csv_export_of_the_trades(small_book):
    proposal = run(small_book)
    out = io.StringIO()
    assert export.write_trades(proposal, out) == 3
    rows = list(csv.DictReader(io.StringIO(out.getvalue())))
    assert out.getvalue().splitlines()[0] == ",".join(export.COLUMNS)
    assert [row["instrument"] for row in rows] == ["AAA", "CCC", "BBB"]
    bond = rows[2]
    assert (bond["side"], bond["quantity"], bond["currency"]) == ("buy", "1000", "USD")
    assert (bond["local_value"], bond["fx_rate"], bond["base_value"]) == ("1000.00", "0.800000", "800.00")
    assert (bond["weight_before"], bond["weight_after"]) == ("0.320000", "0.352000")
    assert (bond["target_scope"], bond["target"]) == ("sector", "Government")
    assert rows[0]["as_of"] == "2026-10-30" and rows[0]["portfolio"] == "TEST"
