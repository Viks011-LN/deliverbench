"""Constants shared by the engine and the reports.

Some modules still carry their own copy of a constant from before this file existed (the metrics and the borrow
fee each define TRADING_DAYS); the values are the same.
"""

TRADING_DAYS = 252          # trading days in a year: annualisation, interest, and the daily share of the borrow fee
BPS = 10000.0               # basis points in one

REBALANCE_FREQUENCIES = ("daily", "weekly", "monthly")
OUTPUT_FORMATS = ("json", "text", "html")

EQUITY_COLUMNS = ("date", "nav", "cash", "gross", "net")
TRADE_COLUMNS = ("date", "symbol", "side", "units", "price", "notional", "commission", "slippage", "reason")

REASON_REBALANCE = "rebalance"
REASON_FORCED_EXIT = "forced exit"
REASON_STOP_LOSS = "stop loss"

WORST_DRAWDOWNS = 3         # how many drawdowns the report and the summary list
