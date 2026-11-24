"""The house style of alert messages, and the number formatting every message uses.

A message reads ``<LEVEL> <subject>: <what> (<detail>)``, for example

    WARNING ORVK: price down 3.12% (last 41.27, from 42.60)

The level is in capitals. The subject says what the alert is about, ``what`` says what happened, and the detail, in
brackets, gives the figures behind it; a kind with no detail leaves out the brackets too. Parts of ``what`` or of
the detail are separated by ", ".

Numbers in messages are written by number() and the helpers built on it, never by str() or format(), so that every
kind writes the same figure the same way:

- rounding is half away from zero, on the value as written: 2.675 is 2.68 and 12.25 is 12.3 (Python's own
  format() would give 2.67 and 12.2);
- thousands are separated by commas: 1,212;
- a value that rounds to zero is written without a sign.

Each unit has its own number of decimals and its own suffix (UNITS). amount() writes a figure in its unit,
signed() a difference with its sign (+0.24%, -93k), and change() a move in words (up 0.24%, down 93k)."""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from alertd.levels import check
from alertd.timeutil import clock_of

# unit: (decimals, suffix)
UNITS = {
    "pct": (2, "%"),     # percent, and percentage changes
    "bp": (0, "bp"),     # basis points
    "k": (0, "k"),       # thousands
    "m": (1, "m"),       # millions (of the desk's base currency)
    "bn": (1, "bn"),     # billions
    "min": (0, " min"),  # minutes
}


def number(value: float, places: int) -> str:
    """``value`` with ``places`` decimals, in the house style (see above)."""
    exact = Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if exact == 0:
        exact = abs(exact)
    return f"{exact:,.{places}f}"


def amount(value: float, unit: str) -> str:
    """A figure in its unit: 3.42%, 1,212k, -14.6bn."""
    places, suffix = UNITS[unit]
    return number(value, places) + suffix


def _rounds_to_zero(text: str) -> bool:
    return not any(ch in "123456789" for ch in text)


def signed(value: float, unit: str) -> str:
    """A difference with its sign: +0.24%, -93k. A value that rounds to zero has no sign: 0.00%."""
    text = amount(abs(value), unit)
    if _rounds_to_zero(text):
        return text
    return ("+" if value > 0 else "-") + text


def change(value: float, unit: str) -> str:
    """A move in words: up 0.24%, down 12bp; unchanged when it rounds to zero."""
    text = amount(abs(value), unit)
    if _rounds_to_zero(text):
        return "unchanged"
    return ("up " if value > 0 else "down ") + text


def share(part: float, whole: float, places: int = 1) -> str:
    """``part`` as a percentage of ``whole``: 104.5%."""
    return number(part / whole * 100, places) + "%"


def clock(value: datetime) -> str:
    """A time of day for a message: 09:12 UTC."""
    return clock_of(value).strftime("%H:%M") + " UTC"


def level_tag(level: str) -> str:
    return check(level).upper()


def shorten(text: str, limit: int = 80) -> str:
    """Text cut to ``limit`` characters, ending in "..." when it was cut."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def message(level: str, subject: str, what: str, detail: str | None = None) -> str:
    """The message in the house style: <LEVEL> <subject>: <what> (<detail>)."""
    text = f"{level_tag(level)} {subject}: {what}"
    return f"{text} ({detail})" if detail else text
