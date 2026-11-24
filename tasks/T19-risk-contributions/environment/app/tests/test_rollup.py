from decimal import Decimal

import pytest

from folio.aggregate.rollup import rollup, share, top_n

ITEMS = [("b", 5), ("a", 5), ("c", 1), ("b", 2), ("d", 9)]


def by_label(items, **kwargs):
    return rollup(items, key=lambda item: item[0], value=lambda item: Decimal(item[1]), **kwargs)


def test_largest_first_ties_by_key():
    groups = by_label(ITEMS)
    assert [(g.key, g.total, g.count) for g in groups] == [
        ("d", 9, 1), ("b", 7, 2), ("a", 5, 1), ("c", 1, 1)]
    assert groups[1].members == (("b", 5), ("b", 2))  # input order kept inside a group


def test_fixed_order_with_strays_last_and_no_empty_groups():
    groups = by_label(ITEMS, order=("c", "x", "a"))
    assert [g.key for g in groups] == ["c", "a", "b", "d"]
    with pytest.raises(ValueError, match="lists a key twice"):
        by_label(ITEMS, order=("a", "a"))


def test_bad_keys_are_rejected():
    with pytest.raises(ValueError, match="non-empty string"):
        by_label([("", 1)])
    with pytest.raises(ValueError, match="non-empty string"):
        by_label([(None, 1)])


def test_top_n_folds_the_tail():
    groups = top_n(by_label(ITEMS), 2)
    assert [(g.key, g.total, g.count) for g in groups] == [("d", 9, 1), ("b", 7, 2), ("Other", 6, 2)]
    assert top_n(by_label(ITEMS), 0) == by_label(ITEMS)
    assert top_n(by_label(ITEMS), 4) == by_label(ITEMS)
    with pytest.raises(ValueError, match="already has that key"):
        top_n(by_label([("Other", 1), ("a", 2), ("b", 3)]), 1)


def test_share():
    assert share(Decimal(1), Decimal(4)) == Decimal("0.25")
    assert share(Decimal(1), Decimal(0)) == 0
