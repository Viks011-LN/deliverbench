"""Historical scenarios: replay the worst N-business-day move in the price history.

The scenario's ``scope`` says where to look:

* "book" tries every window of N consecutive price dates on today's
  holdings (each instrument's price move and each currency's FX move over
  the window, applied to what is held now) and replays the window that
  loses most. Its moves really happened together, so the scenario is as
  plausible as the history it comes from.
* "instrument" gives each holding the worst N-day price move in its own
  history, wherever that falls. Those moves never all happened on the same
  days, so this is harsher than any real window; currencies do not move.

N counts price dates, which are business days. On a date without a price an
instrument keeps its previous one, as in returns.line_values, so a fund that
prices weekly makes its whole move on the day its new price arrives. The
book is only tried from the first date on which every holding has a price
(returns.history_dates). Ties go to the earliest window.

"Worst" means lowest: an instrument that never fell over N days gets its
smallest gain.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from folio.calc.returns import history_dates
from folio.calc.valuation import Valuation
from folio.data.fx_csv import FxRates
from folio.data.prices_csv import PriceHistory
from folio.errors import RiskError
from folio.scenarios.shocks import HistoricalSpec, Moves, Window, revalue

Levels = dict[str, list[Decimal]]  # one value per history date, keyed by instrument id or currency


def replay(spec: HistoricalSpec, valuation: Valuation, prices: PriceHistory, fx: FxRates) -> Moves:
    """The moves of a historical scenario on ``valuation``'s book."""
    if spec.scope == "book":
        return worst_book_window(valuation, prices, fx, spec.days)
    return worst_instrument_moves(valuation, prices, spec.days)


def worst_book_window(valuation: Valuation, prices: PriceHistory, fx: FxRates, days: int) -> Moves:
    """Every price and FX move of the ``days``-long window that would cost today's book most."""
    dates = history_dates(valuation, prices)
    _require_history(len(dates), days, "the book", valuation.as_of)
    base = valuation.base_currency
    levels: Levels = {
        line.instrument.id: [prices.latest(line.instrument.id, day).price for day in dates]
        for line in valuation.positions
    }
    held = {line.instrument.currency for line in valuation.positions}
    held |= {cash.local_value.currency for cash in valuation.cash}
    rates: Levels = {currency: [fx.rate(currency, base, day) for day in dates] for currency in sorted(held - {base})}

    def pnl(end: int) -> Decimal:
        return _book_pnl(valuation, _moves_between(levels, rates, end - days, end))

    end = min(range(days, len(dates)), key=lambda end: (pnl(end), end))
    window = Window(dates[end - days], dates[end])
    moves = _moves_between(levels, rates, end - days, end)
    return Moves(moves.prices, moves.fx, {instrument_id: window for instrument_id in moves.prices}, window)


def worst_instrument_moves(valuation: Valuation, prices: PriceHistory, days: int) -> Moves:
    """Each holding's own worst ``days``-long price move up to the valuation date; FX stays put."""
    dates = [day for day in prices.dates() if day <= valuation.as_of]
    changes: dict[str, Decimal] = {}
    windows: dict[str, Window] = {}
    for line in valuation.positions:
        instrument_id = line.instrument.id
        first = prices.first_price_date(instrument_id)
        own = [day for day in dates if day >= first]
        _require_history(len(own), days, instrument_id, valuation.as_of)
        series = [prices.latest(instrument_id, day).price for day in own]
        end = min(range(days, len(own)), key=lambda end: (series[end] / series[end - days], end))
        changes[instrument_id] = series[end] / series[end - days] - 1
        windows[instrument_id] = Window(own[end - days], own[end])
    return Moves(changes, {}, windows)


def _moves_between(levels: Levels, rates: Levels, start: int, end: int) -> Moves:
    return Moves(
        {key: series[end] / series[start] - 1 for key, series in levels.items()},
        {key: series[end] / series[start] - 1 for key, series in rates.items()},
    )


def _book_pnl(valuation: Valuation, moves: Moves) -> Decimal:
    """What ``moves`` would make (positive) or lose on the book, in the base currency."""
    total = Decimal(0)
    for line in valuation.positions:
        amount = line.base_value.amount
        moved = revalue(amount, moves.price_change(line.instrument.id), moves.fx_change(line.instrument.currency))
        total += moved - amount
    for cash in valuation.cash:
        amount = cash.base_value.amount
        total += revalue(amount, Decimal(0), moves.fx_change(cash.local_value.currency)) - amount
    return total


def _require_history(count: int, days: int, what: str, as_of: date) -> None:
    if count <= days:
        raise RiskError(f"a {days}-day move needs {days + 1} price dates, but {what} has prices on only "
                        f"{count} up to {as_of}")
