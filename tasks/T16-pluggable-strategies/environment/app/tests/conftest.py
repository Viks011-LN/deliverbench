"""Shared helpers for the tests: the sample data, the command line, and small hand-made price tables.

Run the tests with `pytest` from the repo root (pytest.ini puts the root on the import path).
"""
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
DATA = APP / "tests" / "data"
GOLDEN = APP / "tests" / "golden"


def run_cli(*args, cwd=APP):
    """Run `python -m bt` with these arguments from the repo root; returns the finished process."""
    return subprocess.run([sys.executable, "-m", "bt", *args], cwd=cwd, capture_output=True, text=True)


def weekdays(start, count):
    """`count` weekdays from `start` (a date), as "YYYY-MM-DD" strings."""
    days = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return days


def write_prices(path, dates, columns):
    """Write a price file: columns maps each symbol to a list of prices (None for a blank cell)."""
    lines = ["date," + ",".join(columns)]
    for t, day in enumerate(dates):
        cells = ["" if columns[s][t] is None else repr(columns[s][t]) for s in columns]
        lines.append(day + "," + ",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def trending(start, step, count):
    """Prices that move by a fixed fraction every day."""
    prices = []
    price = start
    for _ in range(count):
        prices.append(round(price, 4))
        price *= 1.0 + step
    return prices


def zigzag(start, amplitude, count, period=6):
    """Prices that swing around a level: enough movement for the reversion signal."""
    prices = []
    for t in range(count):
        phase = t % period
        offset = phase if phase <= period // 2 else period - phase
        prices.append(round(start * (1.0 + amplitude * (offset - period / 4)), 4))
    return prices


@pytest.fixture
def sample():
    """The sample price file: (dates, symbols, prices)."""
    from bt.data import load_prices

    return load_prices(str(DATA / "prices.csv"))


@pytest.fixture
def sample_config():
    """A loader for the sample configs by name ("momentum", "reversion")."""
    from bt.config import load_config

    return lambda name: load_config(str(DATA / f"{name}.json"))


@pytest.fixture
def config_file(tmp_path):
    """Write a config file from a JSON text and return its path (as a string, like the command line's)."""
    def write(text, name="config.json"):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return str(path)
    return write


@pytest.fixture
def small_market(tmp_path):
    """A 160-day market of four names: two trending up, one down, one swinging. Returns (dates, symbols,
    prices) as load_prices would."""
    from bt.data import load_prices

    dates = weekdays(date(2025, 2, 3), 160)
    columns = {
        "UPPA": trending(50.0, 0.004, 160),
        "UPPB": trending(80.0, 0.002, 160),
        "DOWN": trending(120.0, -0.003, 160),
        "SWNG": zigzag(40.0, 0.02, 160),
    }
    return load_prices(str(write_prices(tmp_path / "small.csv", dates, columns)))
