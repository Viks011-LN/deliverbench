"""The simulation: the day loop.

Every day, in this order (docs/ARCHITECTURE.md has the details):

  1. book the day's profit and loss at the close; a held name whose price is missing beyond the fill gap is
     sold at its last price (a forced exit), and one that hit its stop loss is closed at the close;
  2. from the second day on, the cash earns (or pays) a day of cash_rate; shorts pay the day's borrow fee;
  3. value the book (the NAV before trading) and update the high-water mark for the drawdown control;
  4. on a rebalancing day: score, rank, cap, scale for volatility and drawdown, and trade every name to its
     target at the close;
  5. value the book again for the equity curve.

Nothing is traded before the warm-up is over: the strategy needs its history, and the volatility scaling needs
vol_window days of returns. The first rebalancing day is the day with index max(strategy warm-up, vol_window),
counting the first day of the run as day 0. The strategy is the module in bt/strategies/ that the config's
`signal.type` names (bt/signals/slot.py); the engine knows no strategy by name.
"""
from bt.data.series import first_price_index, forward_fill, simple_returns
from bt.execution.book import Book
from bt.portfolio.caps import apply_weight_cap
from bt.portfolio.drawdown import drawdown, drawdown_control
from bt.portfolio.ranking import apply_exclusions, apply_min_history, apply_price_floor, scores_to_weights
from bt.portfolio.schedule import trades_today
from bt.portfolio.targets import target_units
from bt.portfolio.turnover import limit_turnover
from bt.portfolio.volatility import trailing_vol, volatility_scale
from bt.signals.slot import get_strategy, parameters, strategy_scores


def warmup_days(signal):
    """The days of history the configured strategy needs before its first score: its warmup(params)."""
    strategy = get_strategy(signal)
    return strategy.warmup(parameters(strategy, signal))


def first_trading_day(signal, config):
    """Index of the first rebalancing day: the end of the longer of the two warm-ups."""
    return strategy_start(get_strategy(signal), signal, config)


def strategy_start(strategy, signal, config):
    """first_trading_day(), for a strategy already found."""
    return max(strategy.warmup(parameters(strategy, signal)), config["vol_window"])


def prepare(symbols, raw_prices, max_gap):
    """Forward-filled prices and their day-on-day returns, per symbol."""
    prices = {}
    returns = {}
    for symbol in symbols:
        prices[symbol] = forward_fill(raw_prices[symbol], max_gap)
        returns[symbol] = simple_returns(prices[symbol])
    return prices, returns


def rebalance(book, strategy, symbols, prices, returns, first_prices, t, nav, current_drawdown, config):
    """Score, rank and size the book on day t, then trade every name with a price today to its target.
    `strategy` is the module the config's signal names (found once per run: bt/signals/slot.py)."""
    today = {symbol: prices[symbol][t] for symbol in symbols}
    scores = strategy_scores(strategy, parameters(strategy, config["signal"]), prices, symbols, t)
    scores = apply_exclusions(scores, config["exclude"])
    scores = apply_min_history(scores, first_prices, t, config["min_history"])
    scores = apply_price_floor(scores, today, config["min_price"])
    weights = scores_to_weights(scores, config["top_n"], config["allow_short"])
    weights = apply_weight_cap(weights, config["max_weight"])
    vols = {}
    for symbol in weights:
        vols[symbol] = trailing_vol(returns[symbol], t, config["vol_window"])
    scale = volatility_scale(weights, vols, config["vol_target"], config["max_leverage"])
    scale = drawdown_control(scale, current_drawdown, config["drawdown_limit"], config["drawdown_scale"])
    targets = {}
    for symbol in symbols:
        price = today[symbol]
        if price is None:
            continue
        targets[symbol] = target_units(weights.get(symbol, 0.0), scale, nav, price)
    targets = limit_turnover(targets, book.units, today, nav, config["max_turnover"])
    for symbol, target in targets.items():
        book.trade_to(symbol, target, today[symbol], nav, config)


def run_backtest(dates, symbols, raw_prices, config):
    """Simulate the strategy day by day on cash and units. Returns {"curve": one row per day, "stats": the
    trading statistics, "pnl": profit and loss by symbol, "units": the final units, "last_price": the last price
    of each symbol, "trades": the trade log}."""
    prices, returns = prepare(symbols, raw_prices, config["max_fill_gap"])
    first_prices = {symbol: first_price_index(prices[symbol]) for symbol in symbols}
    strategy = get_strategy(config["signal"])
    start = strategy_start(strategy, config["signal"], config)
    book = Book(config["initial_capital"], symbols)
    peak = book.cash
    curve = []

    for t in range(len(dates)):
        book.begin_day(dates[t])
        today = {symbol: prices[symbol][t] for symbol in symbols}
        book.mark(today, config)
        book.check_stops(today, config)
        if t > 0:
            book.accrue_interest(config)
        book.charge_borrow(config)
        nav = book.value()
        if nav > peak:
            peak = nav
        current_drawdown = drawdown(nav, peak)
        if trades_today(dates, t, start, config["rebalance"]):
            rebalance(book, strategy, symbols, prices, returns, first_prices, t, nav, current_drawdown, config)
        curve.append(book.end_of_day(dates[t]))

    return {"curve": curve, "stats": book.stats, "pnl": book.pnl, "units": book.units,
            "last_price": book.last_price, "trades": book.log}
