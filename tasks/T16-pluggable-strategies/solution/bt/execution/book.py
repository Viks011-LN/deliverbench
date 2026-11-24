"""The book: cash, units held, the last price of each name, profit and loss by name, trading statistics and the
trade log.

The engine drives it through the day in a fixed order (docs/ARCHITECTURE.md): begin_day() names the day, mark()
books the day's profit and loss (and forces exits), check_stops() closes the positions that hit their stop,
accrue_interest() pays or charges the cash rate, charge_borrow()
takes the shorts' fee, value() is the NAV before trading, trade_to() moves a name to its target, and end_of_day()
values the book for the equity curve.
"""
from bt.constants import REASON_REBALANCE, TRADING_DAYS
from bt.execution.borrow import borrow_fee
from bt.execution.costs import trade_cost
from bt.execution.exits import forced_exit, stop_loss_exit, stopped_out


def new_stats():
    """The trading statistics of a run, all zero."""
    return {
        "trades": 0,
        "forced_exits": 0,
        "stop_losses": 0,
        "traded_notional": 0.0,
        "commissions": 0.0,
        "slippage": 0.0,
        "borrow_fees": 0.0,
        "interest": 0.0,
    }


class Book:
    """Cash and units. Units are fractional; a negative number of units is a short. A position's entry price is the
    price of the trade that opened it (from no units, or from the other side); resizing it keeps the entry price."""

    def __init__(self, capital, symbols):
        self.symbols = list(symbols)
        self.cash = float(capital)
        self.units = {symbol: 0.0 for symbol in self.symbols}
        self.last_price = {symbol: None for symbol in self.symbols}
        self.pnl = {symbol: 0.0 for symbol in self.symbols}
        self.entry_price = {symbol: None for symbol in self.symbols}
        self.stats = new_stats()
        self.log = []
        self.today = None

    def begin_day(self, day):
        """Start a new day: trades are logged under it."""
        self.today = day

    def record(self, symbol, units, price, notional, fee, slip, reason):
        """Add a trade to the log: `units` bought (positive) or sold (negative) at `price`."""
        self.log.append({
            "date": self.today,
            "symbol": symbol,
            "side": "buy" if units > 0.0 else "sell",
            "units": units,
            "price": price,
            "notional": notional,
            "commission": fee,
            "slippage": slip,
            "reason": reason,
            "after": self.units[symbol],
        })

    def mark(self, prices_today, config):
        """Book the day's profit and loss at today's prices. A held name with no price today (beyond the fill gap)
        is sold at its last price (a forced exit)."""
        for symbol in self.symbols:
            price = prices_today[symbol]
            held = self.units[symbol]
            if price is not None:
                if held != 0.0:
                    self.pnl[symbol] += held * (price - self.last_price[symbol])
                self.last_price[symbol] = price
            elif held != 0.0:
                forced_exit(self, symbol, config)

    def check_stops(self, prices_today, config):
        """With a stop_loss, close every position that has moved against its entry price by that fraction at
        today's close. A name with no price today is left to the forced exit."""
        if config["stop_loss"] is None:
            return
        for symbol in self.symbols:
            held = self.units[symbol]
            if held != 0.0 and prices_today[symbol] is not None and \
                    stopped_out(held, prices_today[symbol], self.entry_price[symbol], config["stop_loss"]):
                stop_loss_exit(self, symbol, config)

    def accrue_interest(self, config):
        """A day's interest on the cash at cash_rate a year: paid on a positive balance, charged on a negative one
        (a leveraged or short-heavy book). Nothing happens at a rate of 0."""
        if config["cash_rate"] == 0.0:
            return
        interest = self.cash * config["cash_rate"] / TRADING_DAYS
        self.cash += interest
        self.stats["interest"] += interest

    def charge_borrow(self, config):
        """Shorts pay the day's borrow fee on their market value."""
        for symbol in self.symbols:
            if self.units[symbol] < 0.0:
                fee = borrow_fee(self.units[symbol], self.last_price[symbol], config["borrow_bps"])
                self.cash -= fee
                self.pnl[symbol] -= fee
                self.stats["borrow_fees"] += fee

    def value(self):
        """The NAV: cash plus every position at its last price."""
        nav = self.cash
        for symbol in self.symbols:
            if self.units[symbol] != 0.0:
                nav += self.units[symbol] * self.last_price[symbol]
        return nav

    def trade_to(self, symbol, target, price, nav, config):
        """Trade `symbol` to `target` units at `price`, paying commission and slippage. A trade whose notional is
        below rebalance_band of the NAV is not worth making and is skipped."""
        trade = target - self.units[symbol]
        if trade == 0.0:
            return
        notional = abs(trade) * price
        if notional < config["rebalance_band"] * nav:
            return  # too small to be worth trading
        fee, slip = trade_cost(notional, config)
        before = self.units[symbol]
        self.cash -= trade * price
        self.cash -= fee + slip
        self.pnl[symbol] -= fee + slip
        self.units[symbol] = target
        if target == 0.0:
            self.entry_price[symbol] = None
        elif before == 0.0 or (before > 0.0) != (target > 0.0):
            self.entry_price[symbol] = price
        self.stats["commissions"] += fee
        self.stats["slippage"] += slip
        self.stats["traded_notional"] += notional
        self.stats["trades"] += 1
        self.record(symbol, trade, price, notional, fee, slip, REASON_REBALANCE)

    def holdings(self):
        """How many names are held (long or short)."""
        return sum(1 for symbol in self.symbols if self.units[symbol] != 0.0)

    def end_of_day(self, day):
        """The equity curve's row for the day: NAV, cash, and gross and net exposure as fractions of the NAV."""
        value = self.cash
        gross = 0.0
        net = 0.0
        for symbol in self.symbols:
            if self.units[symbol] != 0.0:
                position = self.units[symbol] * self.last_price[symbol]
                value += position
                gross += abs(position)
                net += position
        return {"date": day, "nav": value, "cash": self.cash, "gross": gross / value, "net": net / value,
                "holdings": self.holdings()}
