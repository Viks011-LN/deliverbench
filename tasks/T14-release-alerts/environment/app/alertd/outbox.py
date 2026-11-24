"""The outbox: where `alertd run` puts the alerts it sends.

One line per alert: the time alertd saw the event, a tab, then the message. The desk's chat bridge reads the outbox
and posts each new line; it lives outside alertd."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from alertd.errors import StateError
from alertd.timeutil import format_time


class Outbox:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.written = 0

    def append(self, at: datetime, message: str) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(f"{format_time(at)}\t{message}\n")
        except OSError as exc:
            raise StateError(f"cannot write the outbox {self.path}: {exc.strerror or exc}") from None
        self.written += 1


def read_outbox(path: str | Path) -> list[tuple[str, str]]:
    """(time, message) for every line of an outbox."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [tuple(line.split("\t", 1)) for line in lines if line.strip()]
