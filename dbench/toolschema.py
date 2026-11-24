"""The one validator for tool arguments (P3 plan, T08: "one validator").

The agent checks every tool call against the tool's JSON schema before it runs or relays it; a call that breaks
the schema is a malformed call and never reaches a tool or a job's service. So that no part of a schema is
silently ignored, every keyword a tool schema may use is listed here, and the job validator (dbench/tasks.py)
refuses a job whose task tools use any other.
"""
from __future__ import annotations

import math
import re
from typing import Any

# Keywords that constrain a value, all of them checked by schema_problem.
CHECKED_KEYWORDS = frozenset({
    "type", "enum", "const",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern",
    "items", "minItems", "maxItems",
    "properties", "required", "additionalProperties",
})
# Keywords that only describe (they constrain nothing).
ANNOTATION_KEYWORDS = frozenset({"description", "title", "examples"})

_JSON_TYPES = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def unsupported_keywords(schema: Any, where: str = "parameters") -> list[str]:
    """Every place a schema uses a keyword schema_problem does not check (or a type it does not know)."""
    if not isinstance(schema, dict):
        return [f"{where} is not a schema object"]
    found = [f"{where}: {key}" for key in sorted(schema) if key not in CHECKED_KEYWORDS | ANNOTATION_KEYWORDS]
    kind = schema.get("type")
    if kind is not None and kind not in _JSON_TYPES:
        found.append(f"{where}: type {kind!r}")
    for key, sub in (schema.get("properties") or {}).items():
        found += unsupported_keywords(sub, f"{where}.{key}")
    if isinstance(schema.get("items"), dict):
        found += unsupported_keywords(schema["items"], f"{where}[]")
    extra = schema.get("additionalProperties")
    if isinstance(extra, dict):
        found += unsupported_keywords(extra, f"{where}.*")
    elif extra is not None and not isinstance(extra, bool):
        found.append(f"{where}: additionalProperties must be true, false or a schema")
    return found


def _an(kind: str) -> str:
    return f"{'an' if kind[0] in 'aeiou' else 'a'} {kind}"


def schema_problem(value: Any, schema: dict, where: str) -> str | None:
    """The first way value breaks the schema, or None. Checks every keyword in CHECKED_KEYWORDS."""
    kind = schema.get("type")
    if kind in _JSON_TYPES and not _JSON_TYPES[kind](value):
        return f"{where} must be {_an(kind)}, not {type(value).__name__}"
    if isinstance(value, float) and not math.isfinite(value):
        return f"{where} must be a finite number"
    if "const" in schema and value != schema["const"]:
        return f"{where} must be {schema['const']!r}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{where} must be one of {', '.join(map(str, schema['enum']))}"

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Written so that a NaN fails every bound.
        if "minimum" in schema and not value >= schema["minimum"]:
            return f"{where} must be at least {schema['minimum']}"
        if "maximum" in schema and not value <= schema["maximum"]:
            return f"{where} must be at most {schema['maximum']}"
        if "exclusiveMinimum" in schema and not value > schema["exclusiveMinimum"]:
            return f"{where} must be greater than {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and not value < schema["exclusiveMaximum"]:
            return f"{where} must be less than {schema['exclusiveMaximum']}"

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            return f"{where} must be at least {schema['minLength']} characters long"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{where} must be at most {schema['maxLength']} characters long"
        if "pattern" in schema and not re.search(schema["pattern"], value):
            return f"{where} must match the pattern {schema['pattern']}"

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            return f"{where} must have at least {schema['minItems']} items"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{where} must have at most {schema['maxItems']} items"
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(value):
                problem = schema_problem(item, schema["items"], f"{where}[{i}]")
                if problem:
                    return problem

    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            return f"{where} is missing {', '.join(missing)}"
        extra = schema.get("additionalProperties", True)
        for key in value:
            if key in properties:
                continue
            if extra is False:
                return f"{where} has an unexpected field {key!r} (allowed: {', '.join(properties) or 'none'})"
            if isinstance(extra, dict):
                problem = schema_problem(value[key], extra, f"{where}.{key}")
                if problem:
                    return problem
        for key, sub in properties.items():
            if key in value and value[key] is not None:
                problem = schema_problem(value[key], sub, f"{where}.{key}")
                if problem:
                    return problem
    return None
