"""Shared fixtures. Tests build events and settings in memory, or in pytest's tmp_path, never in the repo."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alertd.config import load_settings
from alertd.feed import parse_line
from alertd.state import State
from alertd.timeutil import parse_time

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def make_settings(tmp_path):
    """Settings from a config file with the given text (the defaults, with that text over them)."""
    def make(text: str = ""):
        path = tmp_path / "settings.toml"
        path.write_text(text, encoding="utf-8")
        return load_settings(path)
    return make


@pytest.fixture
def defaults(make_settings):
    return make_settings("")


@pytest.fixture
def make_event():
    """An Event from keyword fields; id, kind and at have defaults."""
    counter = iter(range(1, 10_000))

    def make(kind: str = "price_move", at: str = "2026-11-03T10:00:00Z", **fields):
        n = next(counter)
        data = {"id": fields.pop("id", f"e{n}"), "kind": kind, "at": at, **fields}
        return parse_line(json.dumps(data), n)
    return make


@pytest.fixture
def t():
    """parse_time, short: t("2026-11-03T10:00:00Z")."""
    return parse_time


@pytest.fixture
def empty_state():
    return State()


@pytest.fixture
def write_lines(tmp_path):
    """Write JSON objects as a feed (one per line) and return its path."""
    def write(name: str, rows: list[dict]) -> Path:
        path = tmp_path / name
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path
    return write
