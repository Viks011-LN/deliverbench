"""Reading the price file.

The file is a CSV of daily closing prices: a header `date,SYM1,SYM2,...`, then one row per trading day, oldest
first. A blank cell is a missing price (the stock was not listed yet, or did not trade). Blank lines are skipped.
"""
import csv
import datetime

from bt.errors import PriceFileError


def read_rows(path):
    """The file's rows as lists of cells (csv module, so quoted cells work)."""
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def parse_header(path, rows):
    """The symbols, in header order. The first column must be `date`."""
    if not rows:
        raise PriceFileError(f"{path}: the price file is empty")
    header = [cell.strip() for cell in rows[0]]
    if len(header) < 2 or header[0].lower() != "date":
        raise PriceFileError(f"{path}: the first column must be 'date', followed by at least one symbol")
    symbols = header[1:]
    if len(set(symbols)) != len(symbols):
        raise PriceFileError(f"{path}: a symbol appears twice in the header")
    return symbols


def parse_price(path, line_number, symbol, cell):
    """One cell: None if blank, else a positive float."""
    cell = cell.strip()
    if cell == "":
        return None
    try:
        value = float(cell)
    except ValueError:
        raise PriceFileError(f"{path}:{line_number}: {cell!r} is not a price ({symbol})") from None
    if not value > 0.0:
        raise PriceFileError(f"{path}:{line_number}: prices must be positive ({symbol} {cell})")
    return value


def load_prices(path):
    """Read a price file. Returns (dates, symbols, prices): dates as "YYYY-MM-DD" strings, symbols in header
    order, and prices mapping each symbol to a list of floats (or None) aligned with dates."""
    rows = read_rows(path)
    symbols = parse_header(path, rows)
    width = len(symbols) + 1
    dates = []
    prices = {symbol: [] for symbol in symbols}
    for line_number, row in enumerate(rows[1:], start=2):
        if not row:
            continue  # blank line
        if len(row) != width:
            raise PriceFileError(f"{path}:{line_number}: expected {width} cells, found {len(row)}")
        day = row[0].strip()
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise PriceFileError(f"{path}:{line_number}: {day!r} is not a YYYY-MM-DD date") from None
        if dates and day <= dates[-1]:
            raise PriceFileError(f"{path}:{line_number}: dates must increase ({day} comes after {dates[-1]})")
        dates.append(day)
        for symbol, cell in zip(symbols, row[1:]):
            prices[symbol].append(parse_price(path, line_number, symbol, cell))
    if len(dates) < 2:
        raise PriceFileError(f"{path}: at least two days of prices are needed")
    return dates, symbols, prices
