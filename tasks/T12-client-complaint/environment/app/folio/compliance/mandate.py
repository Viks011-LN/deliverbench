"""Read the mandate file, guidelines.toml: the client's investment guidelines.

    [mandate]
    portfolio = "GBL-BAL"
    client = "Ellesmere Staff Pension Scheme"

    [guidelines.issuer_max_share]
    value = 0.07
    note = "Schedule 2, para 1"

    [guidelines.max_positions]
    value = 40
    enabled = false

The mandate is the client's document, not the desk's. It is kept apart from
folio's settings so that a folio.toml or a --set meant for the desk's limits
can never loosen it, and it names the portfolio it was agreed for so that one
client's mandate is not checked against another client's book.

Each guideline is a table with ``value``, an optional ``note`` (where the
guideline comes from in the agreement) and an optional ``enabled``, true by
default, which switches it off while keeping its value on record. Guidelines
of kind none_held (the restricted list) take no value. A guideline the file
does not mention is simply not part of this client's mandate.

The reader is strict because a typo here would quietly drop a client's rule:
an unknown section, guideline or key, a value of the wrong type and a value
out of range all raise ConfigError naming the file and the key as written,
e.g. ``guidelines.toml: guidelines.issuer_max_share.value must be ...``.
"""

from __future__ import annotations

import difflib
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, NoReturn

from folio.compliance.guideline import MAX_COUNT, MAX_SHARE, MIN_SHARE, NONE_HELD
from folio.domain.money import to_decimal
from folio.errors import ConfigError

SECTIONS = ("mandate", "guidelines")
MANDATE_KEYS = ("portfolio", "client")
TERM_KEYS = ("value", "note", "enabled")

# What a value of each kind may be, and how to say so when it is not.
RANGES: dict[str, tuple[Callable[[Decimal], bool], str]] = {
    MAX_SHARE: (lambda value: Decimal(0) < value <= Decimal(1), "a fraction of NAV above 0 and at most 1"),
    MIN_SHARE: (lambda value: Decimal(0) < value < Decimal(1), "a fraction of NAV above 0 and below 1"),
    MAX_COUNT: (lambda value: value >= 1, "1 or more"),
}


@dataclass(frozen=True)
class Term:
    """One guideline as the mandate states it."""

    key: str
    kind: str
    value: Decimal | None  # None for none_held guidelines, which take no value
    note: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class Mandate:
    """The client's guidelines for one portfolio."""

    portfolio: str
    client: str
    terms: tuple[Term, ...]  # in the order of the ``kinds`` given to the reader, not file order
    source: str = "<mandate>"

    def term(self, key: str) -> Term | None:
        return next((term for term in self.terms if term.key == key), None)

    def in_force(self, key: str) -> bool:
        term = self.term(key)
        return term is not None and term.enabled

    @property
    def enabled_terms(self) -> tuple[Term, ...]:
        return tuple(term for term in self.terms if term.enabled)

    def require_portfolio(self, code: str) -> None:
        """Refuse to check portfolio ``code`` against a mandate agreed for another one."""
        if code != self.portfolio:
            raise ConfigError(f"{self.source} is the mandate for portfolio {self.portfolio}, "
                              f"but the data folder holds {code}")


def load_mandate(path, kinds: Mapping[str, str]) -> Mandate:
    """Read the mandate at ``path``; ``kinds`` maps every known guideline to its kind."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"mandate file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name}: {exc}") from None
    return parse_mandate(document, kinds, source=path.name)


def parse_mandate(document: Mapping[str, Any], kinds: Mapping[str, str], source: str = "<mandate>") -> Mandate:
    """Build a Mandate from parsed TOML; ``source`` is the name used in error messages."""
    reader = _Reader(source)
    for section in sorted(document):
        if section not in SECTIONS:
            close = difflib.get_close_matches(section, SECTIONS, n=1)
            hint = (f" (did you mean [{close[0]}]?)" if close
                    else "; expected [mandate] and [guidelines.<name>] tables")
            reader.fail(f"unknown section [{section}]{hint}")

    header = reader.table(document.get("mandate"), "mandate")
    reader.known_keys(header, MANDATE_KEYS, "key", prefix="mandate.")
    portfolio = reader.text(header.get("portfolio"), "mandate.portfolio")
    client = reader.text(header.get("client", portfolio), "mandate.client")

    guidelines = reader.table(document.get("guidelines"), "guidelines")
    if not guidelines:
        reader.fail("no guidelines; add a [guidelines.<name>] table for each one")
    reader.known_keys(guidelines, kinds, "guideline", prefix="guidelines.")
    terms = tuple(_term(reader, key, kind, guidelines[key]) for key, kind in kinds.items() if key in guidelines)
    return Mandate(portfolio, client, terms, source)


def _term(reader: _Reader, key: str, kind: str, raw: Any) -> Term:
    name = f"guidelines.{key}"
    table = reader.table(raw, name)
    reader.known_keys(table, TERM_KEYS, "key", prefix=f"{name}.")
    enabled = table.get("enabled", True)
    if not isinstance(enabled, bool):
        reader.fail(f"{name}.enabled must be true or false, got {enabled!r}")
    note = reader.text(table["note"], f"{name}.note") if "note" in table else ""
    if kind == NONE_HELD:
        if "value" in table:
            reader.fail(f"{name} takes no value: nothing on the list may be held; remove the value line")
        return Term(key, kind, None, note, enabled)
    if "value" not in table:
        reader.fail(f"{name} has no value")
    return Term(key, kind, _value(reader, kind, table["value"], f"{name}.value"), note, enabled)


def _value(reader: _Reader, kind: str, raw: Any, name: str) -> Decimal:
    if kind == MAX_COUNT:
        if isinstance(raw, bool) or not isinstance(raw, int):
            reader.fail(f"{name} must be a whole number, got {raw!r}")
        value = Decimal(raw)
    else:
        if isinstance(raw, str) and raw.strip().endswith("%"):
            reader.fail(f"{name} must be a fraction, not a percentage: write 0.05 for 5%, got {raw!r}")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            reader.fail(f"{name} must be a number such as 0.05, got {raw!r}")
        try:
            value = to_decimal(raw, what=name)
        except ValueError as exc:
            reader.fail(str(exc))
    accepts, wording = RANGES[kind]
    if not accepts(value):
        reader.fail(f"{name} must be {wording}, got {value}")
    return value


class _Reader:
    """Checks on parsed TOML that fail with ConfigError naming the file."""

    def __init__(self, source: str):
        self.source = source

    def fail(self, message: str) -> NoReturn:
        raise ConfigError(f"{self.source}: {message}")

    def table(self, value: Any, name: str) -> dict[str, Any]:
        if value is None:
            self.fail(f"[{name}] is missing")
        if not isinstance(value, dict):
            self.fail(f"{name} must be a table, written [{name}], got {value!r}")
        return value

    def known_keys(self, table: Mapping[str, Any], known: Iterable[str], what: str, prefix: str) -> None:
        known = sorted(known)
        unknown = sorted(key for key in table if key not in known)
        if unknown:
            close = difflib.get_close_matches(unknown[0], known, n=1)
            hint = f" (did you mean {prefix}{close[0]}?)" if close else f"; expected one of: {', '.join(known)}"
            self.fail(f"unknown {what} {prefix}{unknown[0]}{hint}")

    def text(self, value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            self.fail(f"{name} must be a non-empty string, got {value!r}")
        return value.strip()
