"""F01: the agent refuses to start in a Harbor process where telemetry is on."""
from __future__ import annotations

import asyncio

import pytest

from dbench.agent import DeliverAgent
from dbench.telemetry import TELEMETRY_VAR


def make_agent(tmp_path):
    return DeliverAgent(logs_dir=tmp_path)


def test_setup_refuses_when_telemetry_is_on(tmp_path, monkeypatch):
    monkeypatch.setenv(TELEMETRY_VAR, "1")
    with pytest.raises(RuntimeError, match="telemetry is on"):
        asyncio.run(make_agent(tmp_path).setup(environment=None))


def test_setup_refuses_when_telemetry_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv(TELEMETRY_VAR, raising=False)
    with pytest.raises(RuntimeError):
        asyncio.run(make_agent(tmp_path).setup(environment=None))


def test_setup_passes_when_telemetry_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv(TELEMETRY_VAR, "0")
    asyncio.run(make_agent(tmp_path).setup(environment=None))
