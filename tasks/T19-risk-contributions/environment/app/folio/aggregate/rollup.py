"""Group-by with one, explicit ordering rule.

rollup() is the single place that decides how groups are ordered, so every
table in folio sorts the same way: largest total first, ties broken by key.
Pass ``order`` for keys with a natural order of their own (instrument kinds,
rating bands); groups whose key is not in ``order`` then follow in key order.
Groups with no members never appear, whatever ``order`` says.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Group(Generic[T]):
    key: str
    total: Decimal
    members: tuple[T, ...]

    @property
    def count(self) -> int:
        return len(self.members)


def rollup(
    items: Iterable[T],
    key: Callable[[T], str],
    value: Callable[[T], Decimal],
    *,
    order: Sequence[str] | None = None,
) -> list[Group[T]]:
    """Group ``items`` by ``key`` and total ``value`` per group."""
    members: dict[str, list[T]] = {}
    totals: dict[str, Decimal] = {}
    for item in items:
        label = key(item)
        if not isinstance(label, str) or not label:
            raise ValueError(f"group key must be a non-empty string, got {label!r} for {item!r}")
        members.setdefault(label, []).append(item)
        totals[label] = totals.get(label, Decimal(0)) + value(item)
    groups = [Group(label, totals[label], tuple(members[label])) for label in members]
    return sort_groups(groups, order)


def sort_groups(groups: Iterable[Group[T]], order: Sequence[str] | None = None) -> list[Group[T]]:
    if order is None:
        return sorted(groups, key=lambda group: (-group.total, group.key))
    if len(set(order)) != len(order):
        raise ValueError(f"order lists a key twice: {list(order)}")
    rank = {label: index for index, label in enumerate(order)}
    return sorted(groups, key=lambda group: (rank.get(group.key, len(rank)), group.key))


def top_n(groups: list[Group[T]], n: int, other: str = "Other") -> list[Group[T]]:
    """Keep the first ``n`` groups and fold the rest into one ``other`` group.

    ``n`` <= 0 keeps everything. The folded group goes last whatever its size.
    """
    if n <= 0 or len(groups) <= n:
        return list(groups)
    if any(group.key == other for group in groups):
        raise ValueError(f"cannot fold into {other!r}: a group already has that key")
    head, tail = groups[:n], groups[n:]
    folded = Group(
        other,
        sum((group.total for group in tail), Decimal(0)),
        tuple(member for group in tail for member in group.members),
    )
    return list(head) + [folded]


def share(part: Decimal, whole: Decimal) -> Decimal:
    """``part / whole``, or zero when ``whole`` is zero."""
    if whole == 0:
        return Decimal(0)
    return part / whole
