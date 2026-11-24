"""The one validator for tool arguments (dbench/toolschema.py): every keyword it allows is checked, and a job whose
task tools use any other keyword is refused."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dbench.tasks import validate_job
from dbench.toolschema import CHECKED_KEYWORDS, schema_problem, unsupported_keywords

T00B = Path(__file__).resolve().parents[1] / "tasks" / "T00b-tool-relay"

TICKET = {
    "type": "object",
    "properties": {
        "account": {"type": "string", "pattern": "^[A-Z]{4}-[0-9]{2}$"},
        "side": {"type": "string", "enum": ["buy", "sell"]},
        "quantity": {"type": "integer", "minimum": 1, "maximum": 1000000},
        "limit_price": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 100000},
        "note": {"type": "string", "minLength": 1, "maxLength": 5},
        "tags": {"type": "array", "items": {"type": "string", "const": "x"}, "minItems": 1, "maxItems": 2},
        "legs": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"],
                 "additionalProperties": {"type": "integer"}},
    },
    "required": ["account", "side", "quantity"],
    "additionalProperties": False,
}
GOOD = {"account": "NRDF-01", "side": "buy", "quantity": 100, "limit_price": 10.5, "note": "ok",
        "tags": ["x"], "legs": {"n": 1, "m": 2}}


def test_a_valid_value_passes():
    assert schema_problem(GOOD, TICKET, "arguments") is None


@pytest.mark.parametrize("change,expected", [
    ({"account": "nrdf-01"}, "must match the pattern"),
    ({"side": "short"}, "must be one of"),
    ({"quantity": 0}, "at least 1"),
    ({"quantity": 1000001}, "at most 1000000"),
    ({"quantity": True}, "must be an integer"),
    ({"quantity": 100.0}, "must be an integer"),
    ({"limit_price": 0}, "greater than 0"),
    ({"limit_price": 100000}, "less than 100000"),
    ({"limit_price": float("nan")}, "finite"),
    ({"limit_price": float("inf")}, "finite"),
    ({"limit_price": "10.5"}, "must be a number"),
    ({"note": ""}, "at least 1 characters"),
    ({"note": "too long"}, "at most 5 characters"),
    ({"tags": []}, "at least 1 items"),
    ({"tags": ["x", "x", "x"]}, "at most 2 items"),
    ({"tags": ["y"]}, "must be 'x'"),
    ({"legs": {"m": 2}}, "missing n"),
    ({"legs": {"n": 1, "m": "two"}}, "legs.m must be an integer"),
    ({"comment": "please"}, "unexpected field 'comment'"),
])
def test_each_keyword_is_checked(change, expected):
    problem = schema_problem({**GOOD, **change}, TICKET, "arguments")
    assert problem and expected in problem, problem


def test_every_checked_keyword_is_exercised_above():
    used = set()

    def walk(schema):
        used.update(k for k in schema if k in CHECKED_KEYWORDS)
        for sub in (schema.get("properties") or {}).values():
            walk(sub)
        for key in ("items", "additionalProperties"):
            if isinstance(schema.get(key), dict):
                walk(schema[key])

    walk(TICKET)
    assert used == CHECKED_KEYWORDS


@pytest.mark.parametrize("schema,expected", [
    ({"type": "object", "properties": {"d": {"type": "string", "format": "date"}}}, "d: format"),
    ({"type": "object", "properties": {"q": {"type": "number", "multipleOf": 0.05}}}, "q: multipleOf"),
    ({"type": "object", "oneOf": []}, "parameters: oneOf"),
    ({"type": "object", "properties": {"x": {"type": "decimal"}}}, "type 'decimal'"),
    ({"type": "object", "additionalProperties": {"type": "string", "pattern": "^a", "format": "x"}}, "*: format"),
])
def test_unchecked_keywords_are_found(schema, expected):
    found = unsupported_keywords(schema)
    assert any(expected in f for f in found), found


def test_a_job_whose_tools_use_an_unchecked_keyword_is_refused(tmp_path):
    copy = tmp_path / "job"
    shutil.copytree(T00B, copy)
    tools_file = copy / "environment" / "dbench-tools.json"
    spec = json.loads(tools_file.read_text(encoding="utf-8"))
    spec["tools"][0]["function"]["parameters"]["properties"]["symbol"]["format"] = "ticker"
    tools_file.write_text(json.dumps(spec), encoding="utf-8")
    problems = validate_job(copy)
    assert any("get_price.parameters.symbol: format" in p for p in problems), problems
