"""Relative return and tracking error against the index levels.

The book side is returns.nav_series(): today's holdings at each day's prices
and FX, the same series ``folio risk`` uses. The index side is
benchmark_levels.csv. paired_returns() puts the two side by side, one row per
day; a day's active return is the book's return minus the index's.

Tracking error is the standard deviation of the daily active returns in the
window, annualised with the square root of risk.annualisation_days. Relative
return is the book's return over the window minus the index's: a plain
difference, not a ratio, so that it is what the allocation/selection split
adds up to.

Beta is the covariance of the daily book and index returns over the variance
of the index returns. Over a few weeks it is a rough guide, nothing more.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import NamedTuple

from folio.benchmark.levels_csv import IndexLevels
from folio.calc.returns import Series, cumulative_return, simple_returns
from folio.config.settings import RiskSettings
from folio.errors import RiskError


class PairedReturn(NamedTuple):
    since: date   # the earlier day of the two
    day: date     # the later day, which the return is dated by
    book: float
    index: float

    @property
    def active(self) -> float:
        return self.book - self.index


def paired_returns(series: Series, levels: IndexLevels) -> list[PairedReturn]:
    """Daily book and index returns on the dates of ``series`` from the first index level on.

    Oldest first. A date without its own level uses the latest earlier one,
    as a gap in prices does for the book.
    """
    usable = [(day, nav) for day, nav in series if day >= levels.first_date()]
    book = simple_returns(usable)
    index = simple_returns([(day, levels.latest(day).price) for day, _ in usable])
    return [
        PairedReturn(since, day, ours, theirs)
        for (since, _), (day, ours), (_, theirs) in zip(usable, book, index)
    ]


@dataclass(frozen=True)
class TrackingSummary:
    """Everything ``tracking`` prints. Returns are fractions: 0.012 is +1.2%."""

    code: str               # the index, as named in the levels file
    start: date             # NAV date the window starts from
    end: date
    observations: int       # daily returns in the window
    book_return: float
    index_return: float
    tracking_error: float   # annualised
    beta: float | None      # None when the index did not move
    worst_day: tuple[date, float]  # by active return
    best_day: tuple[date, float]
    last_level: date        # date of the index level used for ``end``

    @property
    def relative_return(self) -> float:
        return self.book_return - self.index_return


def summarise_tracking(series: Series, levels: IndexLevels, window: int, settings: RiskSettings) -> TrackingSummary:
    """Tracking figures over the last ``window`` daily returns of ``series``.

    Needs at least risk.min_observations returns in the window, like the
    core risk figures, and raises RiskError otherwise.
    """
    if window < 2:
        raise ValueError(f"the window must hold at least 2 daily returns, got {window}")
    pairs = paired_returns(series, levels)[-window:]
    if len(pairs) < settings.min_observations:
        raise RiskError(
            f"only {len(pairs)} daily returns in the window with both a NAV and a level of {levels.code} "
            f"(levels start on {levels.first_date()}), risk.min_observations is {settings.min_observations}; "
            f"use a longer --window, load more history or lower the setting"
        )
    book = [pair.book for pair in pairs]
    index = [pair.index for pair in pairs]
    active = [pair.active for pair in pairs]
    spread = statistics.variance(index)
    # Ties go to the earliest day, as in risk.summarise_risk.
    worst = min(pairs, key=lambda pair: (pair.active, pair.day))
    best = max(pairs, key=lambda pair: (pair.active, -pair.day.toordinal()))
    end = pairs[-1].day
    return TrackingSummary(
        code=levels.code,
        start=pairs[0].since,
        end=end,
        observations=len(pairs),
        book_return=cumulative_return(book),
        index_return=cumulative_return(index),
        tracking_error=statistics.stdev(active) * math.sqrt(settings.annualisation_days),
        beta=statistics.covariance(book, index) / spread if spread > 0 else None,
        worst_day=(worst.day, worst.active),
        best_day=(best.day, best.active),
        last_level=levels.latest(end).day,
    )
