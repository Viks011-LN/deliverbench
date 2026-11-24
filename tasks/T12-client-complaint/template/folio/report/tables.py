"""Plain-text tables with fixed-width columns, and number formatting for them.

    columns = [Column("Sector"), Column("Weight", align="right")]
    print(render_table(columns, [["Energy", "4.2%"]], total=["Total", "100.0%"]))

    Sector  Weight
    ------  ------
    Energy    4.2%
    ------  ------
    Total   100.0%

Cells are strings. The caller formats numbers (format_money, format_pct) so
the table code never has to guess at precision. Each column is as wide as its
widest cell, columns are two spaces apart and lines carry no trailing spaces.

bucket() and histogram_lines() draw the return histogram of
``folio risk --histogram``.
"""

import bisect
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Callable, List, Optional, Sequence, Tuple

GAP = "  "
ALIGNMENTS = ("left", "right")


@dataclass(frozen=True)
class Column:
    title: str
    align: str = "left"
    min_width: int = 0

    def __post_init__(self):
        if self.align not in ALIGNMENTS:
            raise ValueError(f"column {self.title!r}: align must be 'left' or 'right', not {self.align!r}")


def render_table(columns: Sequence[Column], rows: Sequence[Sequence[str]],
                 total: Optional[Sequence[str]] = None, rule: str = "-") -> str:
    """Render ``rows`` under ``columns``; ``total`` goes below a second rule."""
    if not columns:
        raise ValueError("a table needs at least one column")
    body = [list(row) for row in rows]
    every = body + ([list(total)] if total is not None else [])
    for index, row in enumerate(every):
        if len(row) != len(columns):
            raise ValueError(f"row {index} has {len(row)} cells for {len(columns)} columns")

    widths = []
    for index, column in enumerate(columns):
        cells = [len(row[index]) for row in every]
        widths.append(max([len(column.title), column.min_width] + cells))

    def line(cells: Sequence[str]) -> str:
        padded = []
        for cell, width, column in zip(cells, widths, columns):
            padded.append(cell.rjust(width) if column.align == "right" else cell.ljust(width))
        return GAP.join(padded).rstrip()

    separator = GAP.join(rule * width for width in widths)
    lines = [line([column.title for column in columns]), separator]
    lines.extend(line(row) for row in body)
    if total is not None:
        lines.extend([separator, line(total)])
    return "\n".join(lines)


def _round(value, places: int) -> Decimal:
    number = value if isinstance(value, Decimal) else Decimal(repr(float(value)))
    result = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    return result.copy_abs() if result == 0 else result  # never print "-0.00"


def format_money(amount, places: int = 2) -> str:
    """``Decimal('1234567.891')`` -> ``'1,234,567.89'``."""
    return f"{_round(amount, places):,.{places}f}"


def format_pct(fraction, places: int = 1, signed: bool = False) -> str:
    """``0.2414`` -> ``'24.1%'``; with ``signed`` positive values get a '+'."""
    value = _round(Decimal(repr(fraction)) * 100 if isinstance(fraction, float) else fraction * 100, places)
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.{places}f}%"


def format_quantity(quantity: Decimal) -> str:
    """Whole numbers without decimals, others with as many as they need."""
    if quantity == quantity.to_integral_value():
        return f"{quantity:,.0f}"
    return f"{quantity.normalize():,f}"


def clip(text: str, width: int) -> str:
    """Shorten ``text`` to ``width`` characters, marking the cut with '...'."""
    if len(text) <= width:
        return text
    return text[: max(width - 3, 0)] + "..."


def bucket(values: Sequence[float], edges: Sequence[float],
           label: Callable[[float], str] = str) -> List[Tuple[str, int]]:
    """Count ``values`` into histogram bins defined by ``edges``.

    Bins are half-open, [edges[i], edges[i+1]), plus an open bin below the
    first edge and one at or above the last, so every value lands in exactly
    one bin:

        bucket([0.5, 1.5, 7], [0, 1, 5])
        -> [("< 0", 0), ("[0, 1)", 1), ("[1, 5)", 1), (">= 5", 1)]

    ``label`` formats an edge for the bin names (default ``str``).
    """
    if not edges:
        raise ValueError("bucket() needs at least one edge")
    if any(upper <= lower for lower, upper in zip(edges, edges[1:])):
        raise ValueError(f"edges must be strictly increasing: {list(edges)}")
    counts = [0] * (len(edges) + 1)
    for value in values:
        counts[bisect.bisect_right(edges, value)] += 1
    names = [f"< {label(edges[0])}"]
    names += [f"[{label(lower)}, {label(upper)})" for lower, upper in zip(edges, edges[1:])]
    names.append(f">= {label(edges[-1])}")
    return list(zip(names, counts))


def histogram_lines(bins: Sequence[Tuple[str, int]], width: int = 40, mark: str = "#") -> List[str]:
    """One line per bin: name, count and a bar scaled so the largest is ``width`` long."""
    if not bins:
        return []
    largest = max(count for _, count in bins)
    name_width = max(len(name) for name, _ in bins)
    count_width = len(str(largest))
    lines = []
    for name, count in bins:
        bar = mark * (round(count * width / largest) if largest else 0)
        lines.append(f"{name.ljust(name_width)}  {str(count).rjust(count_width)}  {bar}".rstrip())
    return lines
