"""Setups: a model endpoint plus the settings it runs with, read from endpoints.local.toml.

The file is git-ignored because it holds addresses. Everything that goes into a result travels as a
setup *card*, which never contains the URL, a host name or an address.
"""
from __future__ import annotations

import json
import os
import re
import tomllib
import uuid
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO / "endpoints.local.toml"
IDS_FILE = REPO / ".dbench" / "setup-ids.local.json"
_ADDRESS = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|https?://", re.IGNORECASE)


class SetupError(ValueError):
    pass


@dataclass(frozen=True)
class Setup:
    name: str
    url: str
    model: str
    engine: str = ""
    engine_version: str = ""
    quantisation: str = ""
    kv_cache: str = ""
    context_length: int | None = None
    tool_parser: str = ""
    reasoning_parser: str = ""
    speculative_decoding: str = ""
    prefix_cache: str = ""
    hardware: str = ""
    reasoning_effort: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    api_key_env: str | None = None
    notes: str = ""

    def card(self, setup_id: str) -> dict:
        """Everything about the setup that may appear in a result: no URL, host or key name."""
        card = {k: v for k, v in asdict(self).items() if k not in {"url", "api_key_env"}}
        card["setup_id"] = setup_id
        host = urlparse(self.url).hostname or ""
        for key, value in card.items():
            text = str(value)
            if (host and host in text) or _ADDRESS.search(text):
                raise SetupError(f"setup '{self.name}': field '{key}' looks like it contains an address")
        return card


_KNOWN = {f.name for f in fields(Setup)} - {"name"}


def load_setups(path: Path = DEFAULT_FILE) -> dict[str, Setup]:
    if not path.exists():
        raise SetupError(f"{path.name} not found. Copy endpoints.example.toml to endpoints.local.toml and fill it in.")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    setups = {}
    for name, table in data.items():
        if not isinstance(table, dict):
            raise SetupError(f"'{name}' must be a [table]")
        unknown = set(table) - _KNOWN
        if unknown:
            raise SetupError(f"setup '{name}': unknown keys {sorted(unknown)} (known: {sorted(_KNOWN)})")
        for required in ("url", "model"):
            if not table.get(required):
                raise SetupError(f"setup '{name}': '{required}' is required")
        setups[name] = Setup(name=name, **table)
    return setups


def get_setup(name: str, path: Path = DEFAULT_FILE) -> Setup:
    setups = load_setups(path)
    if name not in setups:
        raise SetupError(f"no setup '{name}' in {path.name}; known: {', '.join(sorted(setups)) or 'none'}")
    return setups[name]


def setup_id(name: str, ids_file: Path | None = None) -> str:
    """A stable random ID per setup name, kept locally. Results carry this, never a hash of the endpoint."""
    ids_file = ids_file or Path(os.environ.get("DBENCH_IDS_FILE", IDS_FILE))
    ids = json.loads(ids_file.read_text(encoding="utf-8")) if ids_file.exists() else {}
    if name not in ids:
        ids[name] = uuid.uuid4().hex[:12]
        ids_file.parent.mkdir(parents=True, exist_ok=True)
        ids_file.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    return ids[name]
