import pytest

from alertd.levels import LEVELS, higher, is_critical, raise_level, rank


def test_levels_lowest_first():
    assert LEVELS == ("info", "warning", "critical")
    assert [rank(level) for level in LEVELS] == [0, 1, 2]


def test_raise_level_one_step():
    assert raise_level("info") == "warning"
    assert raise_level("warning") == "critical"


def test_critical_stays_critical():
    assert raise_level("critical") == "critical"
    assert raise_level("info", 5) == "critical"


def test_higher():
    assert higher("info", "warning") == "warning"
    assert higher("critical", "info") == "critical"
    assert is_critical("critical") and not is_critical(None)


def test_an_unknown_level_is_refused():
    with pytest.raises(ValueError):
        rank("urgent")
