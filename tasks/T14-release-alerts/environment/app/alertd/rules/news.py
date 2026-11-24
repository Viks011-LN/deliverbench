"""News: a story with a tag the desk watches, or about a ticker on its watchlist (docs/desk/news.md)."""
from __future__ import annotations

from datetime import timedelta

from alertd import format as fmt
from alertd.levels import raise_level
from alertd.model import Finding

KIND = "news"
HEADLINE_LIMIT = 80


def key(event) -> str:
    tickers = event.strings("tickers")
    return f"{KIND}:{event.text('source')}:{tickers[0] if tickers else '-'}"


def evaluate(event, settings: dict) -> Finding | None:
    tags = event.strings("tags")
    tickers = event.strings("tickers")
    headline = event.text("headline")
    source = event.text("source")
    watched = [tag for tag in tags if tag in settings["watch_tags"] or tag in settings["critical_tags"]]
    followed = [ticker for ticker in tickers if ticker in settings["watchlist"]]

    reasons, level = [], None
    if watched:
        reasons.append("tag")
        level = "critical" if any(tag in settings["critical_tags"] for tag in watched) else "warning"
    if followed:
        reasons.append("watchlist")
        # A watched tag on a ticker the desk follows is one step more serious.
        level = "info" if level is None else raise_level(level)
    if level is None:
        return None
    detail = source if not watched else f"{source}, tags: {', '.join(sorted(set(watched)))}"
    return Finding(
        key=key(event),
        level=level,
        reasons=reasons,
        subject=tickers[0] if tickers else source,
        what=fmt.shorten(headline, HEADLINE_LIMIT),
        detail=detail,
        as_of=event.time("published_at"),
        stale_after=timedelta(minutes=settings["stale_after_minutes"]),
    )
