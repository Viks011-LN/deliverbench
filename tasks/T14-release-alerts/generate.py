"""Generate T14's examples, hidden data and wrong solutions, and prove them.

Reads:
  environment/app/   the room as written by hand, everything but examples/: alertd 1.6.2 with four kinds, its tests,
                     its documents (docs/desk/release-alerts.md among them) and the desk's config
  solution/          the reference: the release rule, its registration, its settings (declared in the defaults and
                     set in the desk's config) and tests of its own
  tests/compare.py   how the checks compare a replay with the expected one (shared with tests/test_outputs.py)
Writes:
  environment/app/examples/   a feed for each of the five kinds, the state the examples start from, and the
                              decisions the starter prints for the four existing kinds (feed-release.jsonl has
                              events only)
  tests/data/cases.json       the hidden feeds, their states and configs, and the expected output of each
  tests/original/bundle.json  the starter's tests, examples and pyproject.toml, restored before the original tests run
  cheats/*.sh                 the wrong solutions (WRONG below); plant.sh and tamper.sh come from
                              scripts/make_integrity_cheats.py
Run: python generate.py [output_root]   (default: this job folder)

The release rules are implemented a second time here (independent_release, independent_decisions), from
docs/desk/release-alerts.md and the suppressions as alertd/suppress.py documents them, in exact decimal arithmetic
and without alertd's code. The existing kinds' own rules are taken from the starter (they are existing behaviour by
definition); their suppressions in the mixed feeds come from the independent model.

Proved on every run (asserts):
  - every figure is on its unit's grid and no surprise or revision equals a multiple of a threshold (room or hidden
    config) that decides it, so float arithmetic cannot decide a level and no number sits on a rounding tie; no
    release's age is within a minute of either stale window; no event that is worth an alert comes within a minute
    of a quiet-hours edge, a cooldown's end or a mute's end;
  - the six worked examples on the desk page are lines of examples/feed-release.jsonl, and the independent rules
    and the reference both print exactly the decision the page shows; the README's and the desk pages' example
    lines are what the starter prints;
  - hidden release events use only the kinds of value the room shows (each unit and importance, a null consensus,
    a null or unchanged revision); every level, reason combination, unit, sign and suppression tag appears;
  - the reference's decisions on every hidden release feed (room and hidden config) and every mixed feed equal the
    independent ones, messages included;
  - the reference prints exactly what the starter prints on the existing kinds' feeds, under both configs;
  - the starter and the reference pass every original test;
  - the hidden config changes at least ten release decisions, by its thresholds and by its stale window;
  - doing nothing and each wrong solution fail exactly the checks deliverbench.toml declares for them;
  - deliverbench.toml's [settings] are what is generated here.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True  # no __pycache__ in the job folder (it would reach the checksum and the validator)
sys.path.insert(0, str(HERE / "tests"))
import compare  # noqa: E402  (tests/compare.py: the checks' own comparisons)

GUID = "5b0d2e7c-3f4a-4c8e-9a61-2d7f0b9e4c13"
CANARY = f"harbor-canary GUID {GUID}"
SEED = 1414
APP = HERE / "environment" / "app"
SOLUTION = HERE / "solution"
SKIP = {"__pycache__", ".pytest_cache"}
WORKERS = min(8, os.cpu_count() or 4)
UTC = timezone.utc
D = Decimal
RUN_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "PYTHONHASHSEED": "0",
           "PYTHONDONTWRITEBYTECODE": "1"}

CHECKS = {
    "decisions": "test_outputs::test_release_decisions",
    "messages": "test_outputs::test_release_messages",
    "settings": "test_outputs::test_settings_are_read",
    "machinery": "test_outputs::test_fitted_to_the_machinery",
    "unchanged": "test_outputs::test_existing_kinds_unchanged",
    "original_tests": "test_outputs::test_original_tests_pass",
}

# ----- the desk page's rules, as data ------------------------------------------------------------------------------

UNITS = {"pct": (D("0.01"), 2, "%"), "k": (D("1"), 0, "k"), "bn": (D("0.1"), 1, "bn")}   # grid, places, suffix
ROOM = {"high": {"pct": "0.10", "k": "15", "bn": "1.0"}, "medium": {"pct": "0.20", "k": "30", "bn": "2.0"},
        "low": {"pct": "0.30", "k": "50", "bn": "3.0"}}
HIDDEN = {"high": {"pct": "0.15", "k": "20", "bn": "1.5"}, "medium": {"pct": "0.25", "k": "40", "bn": "2.5"},
          "low": {"pct": "0.40", "k": "60", "bn": "4.0"}}
ROOM_STALE, HIDDEN_STALE = 120, 75
LEVELS = ("info", "warning", "critical")
# release code: (unit, typical figure, spread)
RELEASES = {
    "CPI": ("pct", "0.30", 0.25), "CORE_CPI": ("pct", "0.28", 0.2), "GDP": ("pct", "0.45", 0.4),
    "RETAIL_SALES": ("pct", "0.20", 0.6), "WAGES": ("pct", "0.35", 0.2),
    "PAYROLLS": ("k", "160", 60), "JOBLESS_CLAIMS": ("k", "225", 25), "HOUSING_STARTS": ("k", "1320", 120),
    "TRADE_BALANCE": ("bn", "-12.0", 5.0), "BUDGET_BALANCE": ("bn", "-4.0", 6.0),
    "CURRENT_ACCOUNT": ("bn", "6.0", 4.0),
}

# ----- files -------------------------------------------------------------------------------------------------------


def read_tree(root: Path, leave_out: tuple = ()) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or SKIP & set(rel.parts) or path.suffix == ".pyc" or rel.parts[0] in leave_out:
            continue
        files[rel.as_posix()] = path.read_text(encoding="utf-8")
    return files


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


# ----- times -------------------------------------------------------------------------------------------------------


def ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def moment(day: str, clock: str) -> datetime:
    return ts(f"{day}T{clock}Z")


# ----- events ------------------------------------------------------------------------------------------------------


def num(value: Decimal | None, unit: str):
    if value is None:
        return None
    return int(value) if unit == "k" else float(value)


def quant(value: Decimal, grid: Decimal) -> Decimal:
    return value.quantize(grid, rounding=ROUND_HALF_UP)


def clear(value: Decimal, grid: Decimal, thresholds: list[Decimal], multiples: tuple) -> Decimal:
    """``value`` moved off any multiple of a threshold that decides it, a grid step at a time away from zero."""
    step = grid if value >= 0 else -grid
    for _ in range(20):
        if all(abs(value) != m * t for t in thresholds for m in multiples):
            return value
        value += step
    raise AssertionError(f"cannot clear {value}")


def band(size: Decimal, threshold: Decimal) -> int:
    """0 below the threshold, 1 from once, 2 from twice, 3 from three times."""
    return 3 if size >= 3 * threshold else 2 if size >= 2 * threshold else 1 if size >= threshold else 0


def release(rng: random.Random, day: str, clock: str, country: str, code: str, importance: str, s, r,
            age: float | None = None) -> dict:
    """A release event. ``s``: the surprise in multiples of the room threshold (signed), None for no consensus;
    ``r``: the revision likewise, None for none; ``age``: minutes from publication to ``at`` (None: the seconds
    of ``clock``)."""
    unit, base, spread = RELEASES[code]
    grid = UNITS[unit][0]
    room_t, hidden_t = D(ROOM[importance][unit]), D(HIDDEN[importance][unit])

    def figure() -> Decimal:
        value = quant(D(base) + D(repr(rng.uniform(-spread, spread))), grid)
        return value if value != 0 else grid

    previous = figure()
    if s is None:
        consensus = None
        drift = quant(D(repr(rng.choice((-1, 1)) * rng.uniform(0.5, 3.5))) * room_t, grid)
        actual = previous + drift if previous + drift != 0 else previous + drift + grid
    else:
        consensus = figure()
        surprise = clear(quant(D(repr(s)) * room_t, grid), grid, [room_t, hidden_t], (1, 2, 3))
        assert band(abs(surprise), room_t) == min(int(abs(s)), 3), (code, s, surprise)
        if consensus + surprise == 0:
            consensus += grid
        actual = consensus + surprise
    if r is None:
        revised = None
    else:
        revision = clear(quant(D(repr(r)) * room_t, grid), grid, [room_t, hidden_t], (1,))
        assert (abs(revision) >= room_t) == (abs(r) >= 1), (code, r, revision)
        revised = previous + revision
        if revised == 0:
            revised, previous = revised + grid, previous + grid
    at = moment(day, clock)
    released = at.replace(second=0) if age is None else at - timedelta(minutes=age)
    return {"kind": "release", "at": iso(at), "country": country, "release": code, "released_at": iso(released),
            "importance": importance, "unit": unit, "actual": num(actual, unit), "consensus": num(consensus, unit),
            "previous": num(previous, unit), "revised": num(revised, unit)}


def price(day, clock, instrument, measure, last, reference, quoted_age_min=0.05):
    at = moment(day, clock)
    return {"kind": "price_move", "at": iso(at), "instrument": instrument,
            "quoted_at": iso(at - timedelta(minutes=quoted_age_min)), "last": last, "reference": reference,
            "measure": measure}


def limit(day, clock, desk, name, used, limit_amount, measured_age_min=2):
    at = moment(day, clock)
    return {"kind": "limit_usage", "at": iso(at), "desk": desk, "limit": name, "used": used,
            "limit_amount": limit_amount, "measured_at": iso(at - timedelta(minutes=measured_age_min))}


def monitor(day, clock, feed, last_update):
    at = moment(day, clock)
    return {"kind": "stale_feed", "at": iso(at), "feed": feed, "last_update": iso(moment(day, last_update))}


def story(day, clock, source, tickers, tags, headline, published_age_min=2):
    at = moment(day, clock)
    return {"kind": "news", "at": iso(at), "source": source, "headline": headline,
            "published_at": iso(at - timedelta(minutes=published_age_min)), "tickers": tickers, "tags": tags}


def numbered(prefix: str, events: list[dict], sep: str = "-") -> list[dict]:
    return [{"id": f"{prefix}{sep}{i:02d}", **event} for i, event in enumerate(events, 1)]


# ----- the room's examples -----------------------------------------------------------------------------------------

EX = "2026-11-03"
EXAMPLE_STATE = {
    "muted": {"news:wire:*": "2026-11-03T12:00:00Z", "price_move:QMB30": None},
    "last_alert": {"limit_usage:credit:CS01": "2026-11-03T07:50:00Z", "price_move:BRHW": "2026-11-03T09:20:00Z"},
    "sent_today": {"day": EX, "count": 3},
}
RELEASE_EXAMPLES = ["r01", "r03", "r04", "r06", "r08", "r10"]   # the worked examples on the desk page


def rel_event(rid, at, country, code, released_at, importance, unit, actual, consensus, previous, revised):
    return {"id": rid, "kind": "release", "at": f"{EX}T{at}Z", "country": country, "release": code,
            "released_at": f"{EX}T{released_at}Z", "importance": importance, "unit": unit, "actual": actual,
            "consensus": consensus, "previous": previous, "revised": revised}


def example_feeds() -> dict[str, list[dict]]:
    return {
        "price_move": numbered("p", sep="", events=[
            price(EX, "08:30:00", "ORVK", "pct", 42.95, 42.60),
            price(EX, "09:05:00", "QMB10", "bp", 3.551, 3.472),
            price(EX, "09:30:00", "ORVK", "pct", 41.27, 42.60),
            price(EX, "09:31:00", "BRHW", "pct", 18.62, 19.10),
            price(EX, "09:40:00", "QMB10", "bp", 3.682, 3.472),
            price(EX, "10:15:00", "QMB30", "bp", 3.901, 3.795),
            price(EX, "10:20:00", "KSVH", "pct", 12.10, 11.70, quoted_age_min=15),
            price(EX, "11:00:00", "ORVK", "pct", 39.80, 42.60),
            price(EX, "22:30:00", "BRHW", "pct", 19.80, 19.10),
            price(EX, "23:10:00", "KSVH", "pct", 13.40, 11.70),
        ]),
        "limit_usage": numbered("l", sep="", events=[
            limit(EX, "08:00:00", "rates", "VAR", 7.9, 12.0),
            limit(EX, "08:30:00", "rates", "VAR", 8.6, 12.0),
            limit(EX, "09:00:00", "credit", "CS01", 2.5, 2.4),
            limit(EX, "09:45:00", "rates", "VAR", 10.6, 12.0),
            limit(EX, "10:30:00", "fx", "DELTA", 12.25, 11.75),
            limit(EX, "11:00:00", "credit", "CS01", 2.3, 2.4, measured_age_min=90),
            limit(EX, "12:00:00", "equities", "VAR", 4.15, 5.0),
            limit(EX, "22:15:00", "rates", "VAR", 9.9, 12.0),
            limit(EX, "23:00:00", "rates", "VAR", 12.6, 12.0),
        ]),
        "stale_feed": numbered("s", sep="", events=[
            monitor(EX, "09:00:00", "prices-eu", "08:52:00"),
            monitor(EX, "09:35:00", "prices-eu", "09:12:00"),
            monitor(EX, "09:50:00", "prices-eu", "09:12:00"),
            monitor(EX, "10:05:00", "prices-eu", "09:12:00"),
            monitor(EX, "10:30:00", "fx-asia", "09:40:00"),
            monitor(EX, "10:40:00", "prices-eu", "09:12:00"),
            monitor(EX, "22:40:00", "rates-us", "22:20:00"),
            monitor(EX, "23:30:00", "rates-us", "22:20:00"),
        ]),
        "news": numbered("n", sep="", events=[
            story(EX, "08:10:00", "wire", ["KSVH"], ["halt"], "Kesvora Holdings shares suspended pending announcement"),
            story(EX, "08:40:00", "dowline", ["ORVK"], [], "Orvik Energy names new chief financial officer"),
            story(EX, "09:15:00", "wire", ["BRHW"], ["guidance"], "Brumhallow Foods raises guidance for the full year"),
            story(EX, "09:20:00", "wire", ["VDRX"], ["downgrade"], "Valdorian Rail downgraded by two notches"),
            story(EX, "10:00:00", "dowline", [], ["earnings"], "Quelmark lenders report quarterly results"),
            story(EX, "10:30:00", "dowline", ["TVSK"], ["profit_warning"], "Talvesk Shipping warns on profit",
                  published_age_min=270),
            story(EX, "13:00:00", "wire", ["VDRX"], ["downgrade"], "Valdorian Rail outlook cut to negative"),
            story(EX, "13:10:00", "wire", ["VDRX"], ["guidance"], "Valdorian Rail withdraws its guidance for 2027"),
            story(EX, "14:00:00", "wire", ["KSVH", "ORVK"], ["default"],
                  "Kesvora Holdings subsidiary misses a coupon payment on its senior notes and enters the grace "
                  "period, people familiar with the matter say"),
            story(EX, "22:50:00", "dowline", ["ORVK"], [], "Orvik Energy confirms date of capital markets day"),
        ]),
        "release": [
            rel_event("r01", "07:00:05", "VD", "CPI", "07:00:00", "high", "pct", 0.46, 0.22, 0.31, 0.33),
            rel_event("r02", "08:15:03", "QM", "CPI", "08:15:00", "high", "pct", 0.18, 0.21, 0.25, 0.25),
            rel_event("r03", "09:00:06", "XR", "TRADE_BALANCE", "09:00:00", "low", "bn", -14.6, -15.9, -12.4, -15.8),
            rel_event("r04", "09:30:03", "VD", "GDP", "09:30:00", "high", "pct", 0.31, 0.45, 0.2, 0.34),
            rel_event("r05", "10:00:04", "VD", "RETAIL_SALES", "10:00:00", "medium", "pct", -0.42, 0.1, 0.35, None),
            rel_event("r06", "12:00:05", "QM", "PAYROLLS", "12:00:00", "high", "k", 212, None, 175, 198),
            rel_event("r07", "12:30:02", "XR", "CPI", "12:30:00", "medium", "pct", 0.27, None, 0.19, None),
            rel_event("r08", "13:30:04", "QM", "HOUSING_STARTS", "13:30:00", "medium", "k", 1212, 1305, 1288, None),
            rel_event("r09", "14:05:00", "VD", "JOBLESS_CLAIMS", "11:00:00", "low", "k", 291, 225, 230, 228),
            rel_event("r10", "15:00:02", "XR", "BUDGET_BALANCE", "15:00:00", "medium", "bn", 8.4, 1.7, 3.5, 1.2),
            rel_event("r11", "15:20:03", "QM", "GDP", "15:20:00", "high", "pct", 0.52, 0.4, 0.3, 0.36),
            rel_event("r12", "22:30:05", "VD", "BUDGET_BALANCE", "22:30:00", "medium", "bn", -3.1, -0.9, -2.2, None),
        ],
    }


# ----- hidden data -------------------------------------------------------------------------------------------------


def state_text(state: dict) -> str:
    return json.dumps(state, indent=2) + "\n"


def release_feeds(rng: random.Random) -> list[dict]:
    """Seven feeds of release events alone, each with the state it starts from."""
    def feed(name, day, state, specs):
        events = []
        for spec in specs:
            when, rest = (spec[0], spec[1:]) if spec[0].startswith("2026") else (day, spec)
            clock, country, code, importance, s, r, *age = rest
            events.append(release(rng, when, clock, country, code, importance, s, r, *age))
        return {"name": name, "feed": jsonl(numbered(name.split("-")[0].lower(), events)), "state": state_text(state)}

    return [
        feed("D1-levels", "2026-11-09", {"sent_today": {"day": "2026-11-09", "count": 4}}, [
            ("09:00:04", "VD", "CPI", "high", 1.4, 0),
            ("09:30:05", "QM", "CPI", "high", -2.6, None),
            ("10:00:03", "XR", "CPI", "medium", 3.5, 0.3),
            ("11:30:06", "VD", "PAYROLLS", "high", -1.3, None),
            ("12:00:04", "QM", "PAYROLLS", "high", 2.2, -0.4),
            ("12:30:07", "XR", "HOUSING_STARTS", "medium", -3.4, 0.2),
            ("13:00:02", "VD", "TRADE_BALANCE", "low", 1.7, None),
            ("14:00:05", "QM", "BUDGET_BALANCE", "medium", -2.4, 0.6),
            ("15:00:03", "XR", "CURRENT_ACCOUNT", "low", 4.1, None),
            ("15:30:04", "VD", "RETAIL_SALES", "medium", 0.6, 0.5),
            ("16:00:06", "QM", "JOBLESS_CLAIMS", "low", 0, None),
        ]),
        feed("D2-revisions", "2026-11-10", {"last_alert": {"release:VD:CORE_CPI": "2026-11-10T07:00:00Z"},
                                            "sent_today": {"day": "2026-11-10", "count": 2}}, [
            ("08:30:03", "VD", "GDP", "high", 0.4, 1.5),
            ("09:00:05", "QM", "GDP", "high", 0.2, -2.7),
            ("09:30:04", "XR", "TRADE_BALANCE", "low", 0.5, 3.3),
            ("10:00:06", "VD", "PAYROLLS", "high", 1.3, 1.2),
            ("10:30:02", "QM", "RETAIL_SALES", "medium", -2.3, -1.1),
            ("11:00:07", "XR", "PAYROLLS", "high", 3.2, -1.4),
            ("11:30:03", "VD", "CPI", "high", 1.2, 0.6),
            ("12:00:05", "QM", "HOUSING_STARTS", "medium", -0.3, 0.7),
            ("12:30:04", "XR", "BUDGET_BALANCE", "medium", 2.1, -0.9),
            ("13:00:06", "VD", "CURRENT_ACCOUNT", "low", -3.1, 2.4),
        ]),
        feed("D3-no-consensus", "2026-11-11", {"sent_today": {"day": "2026-11-10", "count": 19}}, [
            ("08:30:04", "VD", "PAYROLLS", "high", None, 1.6),
            ("09:00:03", "QM", "CPI", "high", None, -1.3),
            ("09:30:05", "XR", "TRADE_BALANCE", "low", None, None),
            ("10:00:02", "VD", "GDP", "high", None, 0.4),
            ("10:30:06", "QM", "BUDGET_BALANCE", "medium", None, -3.2),
            ("11:00:04", "XR", "HOUSING_STARTS", "medium", None, 0),
            ("11:30:05", "VD", "RETAIL_SALES", "medium", 2.5, None),
            ("12:00:03", "QM", "PAYROLLS", "high", None, 2.4),
            ("12:30:07", "XR", "CPI", "medium", None, None),
            ("13:00:02", "VD", "JOBLESS_CLAIMS", "low", None, -1.1),
        ]),
        feed("D4-mutes", "2026-11-12", {
            "muted": {"release:VD:CPI": "2026-11-13T00:00:00Z", "release:QM:*": None,
                      "release:XR:GDP": "2026-11-12T09:00:00Z", "release:RETAIL_SALES:XR": None, "price_move:*": None},
            "sent_today": {"day": "2026-11-12", "count": 5}}, [
            ("09:30:04", "VD", "CPI", "high", 1.5, None),
            ("10:00:05", "QM", "PAYROLLS", "high", 2.3, None),
            ("10:30:03", "XR", "GDP", "high", -2.2, None),
            ("11:00:06", "XR", "RETAIL_SALES", "medium", 1.6, None),
            ("11:30:02", "QM", "HOUSING_STARTS", "medium", -3.6, None),
            ("12:00:04", "QM", "GDP", "high", None, 1.4),
            ("12:30:05", "VD", "CPI", "high", 3.3, None),
            ("13:00:03", "VD", "GDP", "high", 2.7, 1.2),
            ("13:30:06", "VD", "TRADE_BALANCE", "low", 0.4, None),
            ("14:00:04", "QM", "CPI", "high", 0.5, 0.3),
        ]),
        feed("D5-quiet-hours", "2026-11-13", {
            "muted": {"release:QM:PAYROLLS": None, "release:XR:CPI": "2026-11-14T06:00:00Z"},
            "sent_today": {"day": "2026-11-13", "count": 3}}, [
            ("21:40:05", "VD", "CPI", "high", 1.3, None),
            ("22:05:03", "QM", "PAYROLLS", "high", 2.4, None),
            ("22:50:06", "XR", "TRADE_BALANCE", "low", -3.4, None),
            ("23:30:04", "VD", "GDP", "high", 1.6, 1.1),
            ("2026-11-14", "00:30:02", "QM", "CPI", "high", -1.2, None),
            ("2026-11-14", "01:15:05", "XR", "HOUSING_STARTS", "medium", 3.1, None),
            ("2026-11-14", "05:45:03", "VD", "PAYROLLS", "high", None, 1.3),
            ("2026-11-14", "06:55:06", "QM", "RETAIL_SALES", "medium", 2.2, None),
            ("2026-11-14", "07:05:04", "XR", "CPI", "medium", 1.4, None),
            ("2026-11-14", "07:20:02", "VD", "CPI", "high", 2.1, None),
        ]),
        feed("D6-stale-and-order", "2026-11-16", {
            "muted": {"release:VD:GDP": None}, "last_alert": {"release:QM:CPI": "2026-11-16T10:20:00Z"},
            "sent_today": {"day": "2026-11-16", "count": 20}}, [
            ("10:05:00", "VD", "GDP", "high", 1.4, None, 130),
            ("10:10:00", "VD", "GDP", "high", 3.4, None, 135),
            ("10:40:00", "QM", "CPI", "high", 2.3, None, 2),
            ("10:50:00", "QM", "CPI", "high", 3.2, None, 95),
            ("11:00:00", "XR", "PAYROLLS", "high", 1.6, None, 100),
            ("11:30:00", "XR", "GDP", "high", 3.5, None, 3),
            ("12:00:00", "VD", "CPI", "high", -2.5, None, 140),
            ("12:05:00", "XR", "GDP", "high", -3.3, None, 1),
            ("12:30:00", "QM", "TRADE_BALANCE", "low", 1.4, None, 60),
            ("13:00:00", "VD", "RETAIL_SALES", "medium", 1.2, None, 125),
        ]),
        feed("D7-cooldown-and-cap", "2026-11-17", {
            "last_alert": {"release:VD:CPI": "2026-11-17T09:40:00Z", "release:XR:GDP": "2026-11-16T23:30:00Z"},
            "sent_today": {"day": "2026-11-17", "count": 20}}, [
            ("10:00:04", "VD", "CPI", "high", 1.5, None),
            ("10:15:03", "VD", "CPI", "high", 3.1, None),
            ("10:32:05", "VD", "CPI", "high", 2.2, None),
            ("10:45:02", "QM", "PAYROLLS", "high", 3.3, None),
            ("11:00:06", "QM", "PAYROLLS", "high", 1.2, None),
            ("11:10:04", "XR", "GDP", "high", 1.8, None),
            ("11:20:03", "XR", "TRADE_BALANCE", "low", None, 1.2),
            ("2026-11-18", "08:00:05", "VD", "PAYROLLS", "high", -2.1, None),
            ("2026-11-18", "08:20:02", "VD", "PAYROLLS", "high", -1.4, None),
            ("2026-11-18", "08:40:04", "QM", "CPI", "high", 2.6, -1.1),
        ]),
    ]


def mixed_feeds(rng: random.Random) -> list[dict]:
    """Three feeds where release alerts share the cap, the mutes, quiet hours and the cooldown with the other kinds."""
    def r(day, clock, country, code, importance, s, rv, age=None):
        return release(rng, day, clock, country, code, importance, s, rv, age)

    a, b, b2, c = "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-23"
    feeds = [
        ("M1", {"muted": {"news:wire:*": None, "release:QM:GDP": None}, "sent_today": {"day": a, "count": 16}}, [
            price(a, "09:00:00", "ORVK", "pct", 43.70, 42.60),
            r(a, "09:05:04", "VD", "CPI", "high", 2.3, None),
            limit(a, "09:10:00", "rates", "VAR", 10.7, 12.0),
            r(a, "09:15:03", "QM", "PAYROLLS", "high", 1.4, None),
            story(a, "09:20:00", "wire", ["KSVH"], ["guidance"], "Kesvora Holdings lowers its outlook for the year"),
            r(a, "09:25:05", "XR", "TRADE_BALANCE", "low", 2.2, None),
            price(a, "09:30:00", "BRHW", "pct", 19.62, 19.10),
            r(a, "09:35:02", "VD", "CPI", "high", 3.3, None),
            monitor(a, "09:40:00", "prices-eu", "08:50:00"),
            story(a, "09:45:00", "dowline", ["ORVK"], [], "Orvik Energy to present at investor day"),
            r(a, "09:50:04", "QM", "GDP", "high", 3.6, None),
            limit(a, "09:55:00", "credit", "CS01", 2.5, 2.4),
            r(a, "10:00:03", "XR", "CPI", "medium", 1.3, None, 130),
            price(a, "10:05:00", "QMB10", "bp", 3.392, 3.492),
            r(a, "10:10:05", "VD", "PAYROLLS", "high", None, 1.4),
            r(a, "10:15:02", "QM", "GDP", "high", 1.5, None),
        ]),
        ("M2", {"muted": {"release:XR:*": "2026-11-21T00:00:00Z"}, "sent_today": {"day": b, "count": 5}}, [
            r(b, "21:30:04", "VD", "GDP", "high", 1.2, 1.3),
            price(b, "21:45:00", "ORVK", "pct", 41.30, 42.60),
            r(b, "21:50:03", "VD", "GDP", "high", 3.2, None),
            r(b, "22:10:05", "XR", "CPI", "medium", 3.4, None),
            story(b, "22:15:00", "wire", ["KSVH"], ["halt"], "Kesvora Holdings shares suspended pending announcement"),
            r(b, "22:20:02", "QM", "CPI", "high", 2.4, None),
            limit(b, "22:30:00", "rates", "VAR", 11.0, 12.0),
            r(b, "23:05:04", "XR", "TRADE_BALANCE", "low", 1.5, None),
            monitor(b, "23:10:00", "fx-asia", "22:50:00"),
            r(b, "23:55:03", "QM", "HOUSING_STARTS", "medium", 1.4, None, 140),
            r(b2, "00:20:05", "XR", "CPI", "medium", 2.1, None),
            price(b2, "00:30:00", "QMB10", "bp", 3.712, 3.492),
            r(b2, "01:10:02", "VD", "CPI", "high", -3.4, None, 150),
        ]),
        ("M3", {"muted": {"release:VD:CPI": None}, "last_alert": {"price_move:ORVK": "2026-11-23T13:00:00Z"},
                "sent_today": {"day": c, "count": 17}}, [
            r(c, "14:00:05", "VD", "PAYROLLS", "high", 2.6, None),
            r(c, "14:02:03", "VD", "PAYROLLS", "high", 1.1, None),
            price(c, "14:05:00", "ORVK", "pct", 43.60, 42.60),
            r(c, "14:10:04", "QM", "RETAIL_SALES", "medium", 1.3, None),
            story(c, "14:15:00", "dowline", ["TVSK"], ["guidance"], "Talvesk Shipping keeps guidance after a strong quarter"),
            r(c, "14:20:02", "XR", "BUDGET_BALANCE", "medium", 3.3, None),
            limit(c, "14:25:00", "equities", "VAR", 5.1, 5.0),
            r(c, "14:30:05", "QM", "RETAIL_SALES", "medium", 2.2, None),
            monitor(c, "14:40:00", "prices-eu", "14:20:00"),
            r(c, "14:45:03", "VD", "CPI", "high", 1.5, None),
            r(c, "14:50:04", "XR", "CPI", "high", 1.4, None, 128),
            price(c, "15:00:00", "QMB10", "bp", 3.212, 3.492),
            limit(c, "15:10:00", "rates", "VAR", 9.0, 12.0),
        ]),
    ]
    return [{"name": name, "feed": jsonl(numbered(name.lower(), events)), "state": state_text(state)}
            for name, state, events in feeds]


def existing_feeds() -> list[dict]:
    """Feeds of the existing kinds alone, run under the room's config and a hidden one."""
    u = "2026-11-24"
    v = "2026-11-25"
    feeds = [
        ("U1-price-moves", {"muted": {"price_move:BRHW": "2026-11-24T12:00:00Z"},
                            "last_alert": {"price_move:ORVK": "2026-11-24T09:50:00Z"},
                            "sent_today": {"day": u, "count": 2}}, [
            price(u, "09:00:00", "KSVH", "pct", 12.31, 12.00),
            price(u, "09:20:00", "QMB10", "bp", 3.565, 3.492),
            price(u, "10:00:00", "ORVK", "pct", 41.50, 42.60),
            price(u, "10:05:00", "BRHW", "pct", 18.20, 19.10),
            price(u, "10:30:00", "ORVK", "pct", 40.10, 42.60, quoted_age_min=12),
            price(u, "11:00:00", "QMB30", "bp", 3.901, 3.795),
            price(u, "13:00:00", "BRHW", "pct", 19.50, 19.10),
            price(u, "14:00:00", "KSVH", "pct", 12.10, 12.00),
            price(u, "15:00:00", "TVSK", "pct", 7.625, 7.20),
            price(u, "21:30:00", "ORVK", "pct", 43.80, 42.60),
            price(u, "22:45:00", "QMB10", "bp", 3.411, 3.492),
            price(u, "23:30:00", "TVSK", "pct", 7.85, 7.20),
        ]),
        ("U2-limit-usage", {"last_alert": {"limit_usage:rates:VAR": "2026-11-24T08:40:00Z"},
                            "sent_today": {"day": u, "count": 0}}, [
            limit(u, "08:30:00", "credit", "CS01", 1.5, 2.4),
            limit(u, "09:05:00", "rates", "VAR", 10.25, 12.0),
            limit(u, "09:30:00", "fx", "DELTA", 12.25, 11.75),
            limit(u, "10:00:00", "equities", "VAR", 3.25, 5.0),
            limit(u, "10:30:00", "credit", "CS01", 2.3, 2.4, measured_age_min=45),
            limit(u, "11:00:00", "rates", "VAR", 6.25, 12.0),
            limit(u, "12:00:00", "rates", "IR01", 0.96, 1.0),
            limit(u, "21:30:00", "rates", "VAR", 11.5, 12.0),
            limit(u, "22:30:00", "fx", "DELTA", 12.6, 12.0),
            limit(u, "23:00:00", "credit", "CS01", 2.2, 2.4),
        ]),
        ("U3-stale-feeds", {"muted": {"stale_feed:fx-asia": None}}, [
            monitor(u, "09:00:00", "prices-eu", "08:48:00"),
            monitor(u, "09:30:00", "prices-eu", "09:08:00"),
            monitor(u, "09:45:00", "prices-eu", "09:08:00"),
            monitor(u, "10:10:00", "fx-asia", "09:30:00"),
            monitor(u, "10:30:00", "rates-us", "09:40:00"),
            monitor(u, "11:00:00", "prices-eu", "09:08:00"),
            monitor(u, "21:40:00", "rates-us", "21:20:00"),
            monitor(u, "22:30:00", "prices-eu", "22:10:00"),
            monitor(u, "23:00:00", "fx-asia", "22:00:00"),
        ]),
        ("U4-news", {"muted": {"news:wire:*": "2026-11-24T11:00:00Z"},
                     "last_alert": {"news:dowline:ORVK": "2026-11-24T08:30:00Z"}}, [
            story(u, "08:40:00", "dowline", ["ORVK"], [], "Orvik Energy names new chief financial officer"),
            story(u, "09:00:00", "wire", ["KSVH"], ["guidance"], "Kesvora Holdings lowers its outlook for the year"),
            story(u, "09:15:00", "wire", ["VDRX"], ["downgrade"], "Valdorian Rail downgraded by two notches"),
            story(u, "09:30:00", "dowline", ["BRHW"], ["profit_warning"], "Brumhallow Foods warns on profit as costs rise"),
            story(u, "10:00:00", "dowline", [], ["merger"], "Two Quelmark lenders confirm merger talks"),
            story(u, "10:30:00", "dowline", ["TVSK"], ["default"],
                  "Talvesk Shipping misses a coupon payment and enters its grace period", published_age_min=190),
            story(u, "11:30:00", "wire", ["VDRX"], ["downgrade"], "Valdorian Rail outlook cut to negative"),
            story(u, "12:00:00", "wire", ["ORVK", "KSVH"], ["halt"],
                  "Trading in Orvik Energy and Kesvora Holdings halted after a joint statement on a proposed "
                  "combination of the two groups"),
            story(u, "13:00:00", "dowline", ["QMB10"], [], "Quelmark ten-year auction draws strong demand"),
            story(u, "21:30:00", "wire", ["KSVH"], ["guidance"], "Kesvora Holdings reaffirms guidance at investor call"),
            story(u, "22:30:00", "dowline", ["VDRX"], ["downgrade"], "Valdorian Rail downgraded again"),
        ]),
        ("U5-together", {"sent_today": {"day": v, "count": 17}}, [
            price(v, "09:00:00", "ORVK", "pct", 43.70, 42.60),
            limit(v, "09:05:00", "rates", "VAR", 10.7, 12.0),
            monitor(v, "09:10:00", "prices-eu", "08:40:00"),
            story(v, "09:15:00", "dowline", ["TVSK"], ["guidance"], "Talvesk Shipping lifts guidance"),
            price(v, "09:20:00", "BRHW", "pct", 19.70, 19.10, quoted_age_min=25),
            limit(v, "09:25:00", "credit", "CS01", 2.6, 2.4),
            price(v, "09:30:00", "ORVK", "pct", 40.20, 42.60),
            story(v, "09:40:00", "wire", ["VDRX"], ["downgrade"], "Valdorian Rail downgraded", published_age_min=280),
            monitor(v, "09:50:00", "fx-asia", "09:20:00"),
            price(v, "10:00:00", "QMB10", "bp", 3.212, 3.492),
            limit(v, "10:10:00", "equities", "VAR", 4.6, 5.0, measured_age_min=70),
            story(v, "10:20:00", "dowline", ["KSVH"], ["downgrade"], "Kesvora Holdings downgraded", published_age_min=200),
        ]),
    ]
    return [{"name": name, "feed": jsonl(numbered(name.split("-")[0].lower(), events)), "state": state_text(state)}
            for name, state, events in feeds]


HIDDEN_EXISTING_CONFIG = """# Other values for every existing setting (hidden; T14's check that nothing else changes).
[alerts]
cooldown_minutes = 20
daily_cap = 8
quiet_start = "21:00"
quiet_end = "06:00"

[price_move]
threshold_pct = 1.2
threshold_bp = 6.0
critical_multiple = 3.0
stale_after_minutes = 20

[limit_usage]
info_at_pct = 60.0
warn_at_pct = 80.0
critical_at_pct = 95.0
stale_after_minutes = 30

[stale_feed]
warn_after_minutes = 10
critical_after_minutes = 30

[news]
watch_tags = ["guidance", "downgrade", "merger"]
critical_tags = ["halt"]
watchlist = ["ORVK", "KSVH"]
stale_after_minutes = 90
"""


def release_tables(thresholds: dict, stale: int) -> str:
    lines = ["[release]", f"stale_after_minutes = {stale}"]
    for importance in ("high", "medium", "low"):
        lines += ["", f"[release.thresholds.{importance}]"]
        lines += [f"{unit} = {thresholds[importance][unit]}" for unit in ("pct", "k", "bn")]
    return "\n".join(lines) + "\n"


def hidden_release_config(room_config: str) -> str:
    """The desk's config as shipped, with the release settings at other values."""
    return room_config.rstrip("\n") + "\n\n# Release alerts at other values (hidden).\n" + release_tables(HIDDEN, HIDDEN_STALE)


# ----- the independent rules -----------------------------------------------------------------------------------------


def dec(value) -> Decimal | None:
    if value is None:
        return None
    return D(repr(value)) if isinstance(value, float) else D(value)


def i_amount(value: Decimal, unit: str) -> str:
    _, places, suffix = UNITS[unit]
    rounded = value.quantize(D(1).scaleb(-places), rounding=ROUND_HALF_UP)
    whole, _, frac = f"{abs(rounded):.{places}f}".partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    text = ",".join([whole, *groups]) + (f".{frac}" if places else "")
    return ("-" if rounded < 0 else "") + text + suffix


def i_signed(value: Decimal, unit: str) -> str:
    return ("+" if value > 0 else "-") + i_amount(abs(value), unit)


def independent_release(event: dict, thresholds: dict) -> dict | None:
    """docs/desk/release-alerts.md, in exact decimals."""
    unit = event["unit"]
    t = D(thresholds[event["importance"]][unit])
    actual, consensus = dec(event["actual"]), dec(event["consensus"])
    previous, revised = dec(event["previous"]), dec(event["revised"])
    reasons, level = [], None
    surprise = None if consensus is None else actual - consensus
    if surprise is not None and abs(surprise) >= t:
        reasons.append("surprise")
        level = LEVELS[band(abs(surprise), t) - 1]
    revision = None if revised is None else revised - previous
    if revision is not None and abs(revision) >= t:
        reasons.append("revision")
        level = "info" if level is None else LEVELS[min(LEVELS.index(level) + 1, 2)]
    if surprise is not None:  # the fairness margin: no figure decides a level by float rounding
        assert all(abs(abs(float(event["actual"]) - float(event["consensus"])) - m * float(t)) > 1e-9
                   for m in (1, 2, 3)), event
    if revision is not None:
        assert abs(abs(float(event["revised"]) - float(event["previous"])) - float(t)) > 1e-9, event
    if level is None:
        return None
    what =[f"actual {i_amount(actual, unit)}" + (f" vs consensus {i_amount(consensus, unit)}"
                                                  if "surprise" in reasons else "")]
    detail = [f"surprise {i_signed(surprise, unit)}"] if "surprise" in reasons else []
    if "revision" in reasons:
        what.append(f"previous revised from {i_amount(previous, unit)} to {i_amount(revised, unit)}")
        detail.append(f"revision {i_signed(revision, unit)}")
    subject = f"{event['country']} {event['release']}"
    return {"level": level, "reasons": reasons,
            "message": f"{level.upper()} {subject}: {', '.join(what)} ({', '.join(detail)})"}


def minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60


def clock_minutes(value: datetime) -> float:
    return value.hour * 60 + value.minute + value.second / 60


def hhmm(text: str) -> float:
    hours, mins = text.split(":")
    return int(hours) * 60 + int(mins)


def independent_decisions(events: list[dict], state: dict, alerts: dict, thresholds: dict, stale_window: int,
                          others: dict) -> list[dict]:
    """The decisions for a feed: the release rules above, the other kinds' findings from ``others`` (id -> None or
    {key, level, reasons, message, stale}), and the shared suppressions as alertd/suppress.py documents them:
    stale, muted, quiet hours, cooldown, daily cap; critical passes muted, quiet hours and the cap."""
    muted = {k: (None if v is None else ts(v)) for k, v in (state.get("muted") or {}).items()}
    last = {k: ts(v) for k, v in (state.get("last_alert") or {}).items()}
    day, count = (state.get("sent_today") or {}).get("day"), (state.get("sent_today") or {}).get("count", 0)
    quiet_start, quiet_end = hhmm(alerts["quiet_start"]), hhmm(alerts["quiet_end"])
    out = []
    for event in events:
        at = ts(event["at"])
        if event["kind"] == "release":
            key = f"release:{event['country']}:{event['release']}"
            found = independent_release(event, thresholds)
            if found is not None:
                age = minutes(at - ts(event["released_at"]))
                assert all(abs(age - window) >= 1 for window in (ROOM_STALE, HIDDEN_STALE)), (event["id"], age)
                found = {**found, "key": key, "stale": age > stale_window}
        else:
            found = others[event["id"]]
            key = found["key"] if found else others.get(event["id"] + "/key")
        row = {"id": event["id"], "kind": event["kind"], "key": key}
        if found is None:
            out.append({**row, "sent": False, "level": None, "reasons": [], "message": None})
            continue
        critical = found["level"] == "critical"
        now = clock_minutes(at)
        assert all(min(abs(now - edge), 1440 - abs(now - edge)) >= 1 for edge in (quiet_start, quiet_end)), event["id"]
        mute_hits = [entry for entry, until in muted.items()
                     if (entry == key or (entry.endswith("*") and key.startswith(entry[:-1])))]
        for entry in mute_hits:
            assert muted[entry] is None or abs(minutes(at - muted[entry])) >= 1, event["id"]
        if key in last:
            assert abs(minutes(at - last[key]) - alerts["cooldown_minutes"]) >= 1, event["id"]
        in_quiet = (quiet_start <= now or now < quiet_end) if quiet_start > quiet_end else quiet_start <= now < quiet_end
        today = at.date().isoformat()
        if found["stale"]:
            tag = "stale"
        elif not critical and any(muted[e] is None or at < muted[e] for e in mute_hits):
            tag = "muted"
        elif not critical and quiet_start != quiet_end and in_quiet:
            tag = "quiet_hours"
        elif key in last and minutes(at - last[key]) < alerts["cooldown_minutes"]:
            tag = "cooldown"
        elif not critical and (count if day == today else 0) >= alerts["daily_cap"]:
            tag = "daily_cap"
        else:
            tag = None
        if tag:
            out.append({**row, "sent": False, "level": found["level"], "reasons": [*found["reasons"], tag],
                        "message": None})
            continue
        if day != today:
            day, count = today, 0
        count += 1
        last[key] = at
        out.append({**row, "sent": True, "level": found["level"], "reasons": list(found["reasons"]),
                    "message": found["message"]})
    return out


# ----- running alertd ----------------------------------------------------------------------------------------------


def replay(root: Path, feed: str, state: str, config: str | None, scratch: Path) -> tuple:
    """(exit status, stdout, stderr) of python -m alertd replay, run from the project folder ``root``."""
    scratch.mkdir(parents=True)
    (scratch / "feed.jsonl").write_text(feed, encoding="utf-8")
    (scratch / "state.json").write_text(state, encoding="utf-8")
    if config is None:
        config_path = root / "config" / "alerts.toml"
    else:
        config_path = scratch / "config.toml"
        config_path.write_text(config, encoding="utf-8")
    proc = subprocess.run([sys.executable, "-s", "-m", "alertd", "replay", "--feed", str(scratch / "feed.jsonl"),
                           "--state", str(scratch / "state.json"), "--config", str(config_path)],
                          cwd=root, env=RUN_ENV, capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


def run_package(package: dict[str, str], runs: list[tuple]) -> list[tuple]:
    """Replays of a package: each run is (feed, state, config text or None for the package's own config)."""
    with tempfile.TemporaryDirectory(prefix="t14-") as tmp:
        root = Path(tmp) / "app"
        write_tree(root, package)
        return [replay(root, feed, state, config, Path(tmp) / f"run-{i}") for i, (feed, state, config) in enumerate(runs)]


def original_tests(package: dict[str, str], original: dict[str, str]) -> dict[str, str]:
    """The original test files, restored with the original examples and pyproject.toml over a package, run as the
    checks run them."""
    with tempfile.TemporaryDirectory(prefix="t14-tests-") as tmp:
        root = Path(tmp) / "app"
        write_tree(root, package)
        write_tree(root, original)
        junit = Path(tmp) / "junit.xml"
        targets = sorted(rel for rel in original if re.fullmatch(r"tests/test_\w+\.py", rel))
        subprocess.run([sys.executable, "-I", "-m", "pytest", "-c", str(root / "pyproject.toml"), f"--rootdir={root}",
                        "-o", "addopts=", "-p", "no:cacheprovider", f"--junitxml={junit}", "-q",
                        *[str(root / t) for t in targets]], cwd=root, env=RUN_ENV, capture_output=True, text=True,
                       timeout=600)
        return compare.junit_statuses(junit.read_text(encoding="utf-8")) if junit.is_file() else {}


def parse_lines(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


# ----- the wrong solutions -----------------------------------------------------------------------------------------

RELEASE_PY = "alertd/rules/release.py"
ENGINE_PY = "alertd/engine.py"
WRONG = [
    {"script": "cheats/revision_below_threshold.sh",
     "name": "a revision of any size counts as a reason",
     "edits": [(RELEASE_PY, "    if revision is not None and abs(revision) >= threshold:\n",
                "    if revision:  # any revision of the previous figure is worth saying\n")]},
    {"script": "cheats/no_consensus_crash.sh",
     "name": "takes the consensus as always there: a release without one stops the replay",
     "edits": [(RELEASE_PY, "    surprise = None if consensus is None else actual - consensus\n"
                            "    if surprise is not None and abs(surprise) >= threshold:\n",
                "    surprise = actual - consensus\n    if abs(surprise) >= threshold:\n")]},
    {"script": "cheats/no_consensus_uses_previous.sh",
     "name": "measures a release without a consensus against the previous figure, so it can have a surprise",
     "edits": [(RELEASE_PY, '    consensus = event.optional_number("consensus")\n',
                '    consensus = event.optional_number("consensus")\n    if consensus is None:\n'
                '        consensus = event.number("previous")  # no consensus: compare with the previous figure\n')]},
    {"script": "cheats/thresholds_in_code.sh",
     "name": "the thresholds and the stale window typed into the rule (declared in the config, never read)",
     "edits": [(RELEASE_PY, 'UNITS = ("pct", "k", "bn")\n',
                'UNITS = ("pct", "k", "bn")\nTHRESHOLDS = {"high": {"pct": 0.10, "k": 15, "bn": 1.0},\n'
                '              "medium": {"pct": 0.20, "k": 30, "bn": 2.0},\n'
                '              "low": {"pct": 0.30, "k": 50, "bn": 3.0}}\n'
                'STALE_AFTER = timedelta(minutes=120)\n'),
               (RELEASE_PY, '    threshold = settings["thresholds"][importance][unit]\n',
                '    threshold = THRESHOLDS[importance][unit]\n'),
               (RELEASE_PY, '        stale_after=timedelta(minutes=settings["stale_after_minutes"]),\n',
                '        stale_after=STALE_AFTER,\n')]},
    {"script": "cheats/mutes_inside_release.sh",
     "name": "releases check mutes and quiet hours themselves before the shared suppressions, critical included",
     "edits": [(ENGINE_PY, "from alertd.suppress import first_suppression\n",
                "from alertd.suppress import first_suppression\nfrom alertd.timeutil import in_window, parse_clock\n"),
               (ENGINE_PY, "        tag = first_suppression(finding, event.at, self.state, self.alerts)\n",
                "        tag = None\n"
                "        if event.kind == \"release\":\n"
                "            # The desk's mutes and quiet hours hold for releases, whatever the level.\n"
                "            if self.state.is_muted(finding.key, event.at):\n"
                "                tag = \"muted\"\n"
                "            elif in_window(event.at, parse_clock(self.alerts[\"quiet_start\"]),\n"
                "                           parse_clock(self.alerts[\"quiet_end\"])):\n"
                "                tag = \"quiet_hours\"\n"
                "        if tag is None:\n"
                "            tag = first_suppression(finding, event.at, self.state, self.alerts)\n")]},
    {"script": "cheats/architecture_order.sh",
     "name": "releases go through the suppressions in docs/ARCHITECTURE.md's older order (stale last)",
     "edits": [(ENGINE_PY, "from alertd.suppress import first_suppression\n",
                "from alertd.suppress import applies, first_suppression\n"),
               (ENGINE_PY, "        tag = first_suppression(finding, event.at, self.state, self.alerts)\n",
                "        if event.kind == \"release\":\n"
                "            # The order in docs/ARCHITECTURE.md.\n"
                "            tag = next((t for t in (\"muted\", \"quiet_hours\", \"cooldown\", \"daily_cap\", \"stale\")\n"
                "                        if applies(t, finding, event.at, self.state, self.alerts)), None)\n"
                "        else:\n"
                "            tag = first_suppression(finding, event.at, self.state, self.alerts)\n")]},
    {"script": "cheats/revision_alone_by_size.sh",
     "name": "a revision alone takes the level its size would give a surprise",
     "edits": [(RELEASE_PY, '        level = "info" if level is None else raise_level(level)\n',
                '        level = surprise_level(abs(revision), threshold) if level is None else raise_level(level)\n')]},
    {"script": "cheats/critical_raised_past_critical.sh",
     "name": "the revision's step has no ceiling: critical goes round to info",
     "edits": [(RELEASE_PY, "from alertd.levels import raise_level\n", "from alertd.levels import LEVELS\n"),
               (RELEASE_PY, '        level = "info" if level is None else raise_level(level)\n',
                '        level = "info" if level is None else LEVELS[(LEVELS.index(level) + 1) % len(LEVELS)]\n')]},
    {"script": "cheats/cap_excludes_releases.sh",
     "name": "release alerts sent are kept out of the daily cap's count",
     "edits": [(ENGINE_PY, "        self.state.record_sent(finding.key, event.at)\n",
                "        if event.kind == \"release\":\n"
                "            self.state.last_alert[finding.key] = event.at  # releases have a budget of their own\n"
                "        else:\n"
                "            self.state.record_sent(finding.key, event.at)\n")]},
    {"script": "cheats/own_message_format.sh",
     "name": "the right decisions, with messages in a format of its own",
     "edits": [(RELEASE_PY,
                '        what.append(f"actual {fmt.amount(actual, unit)} vs consensus {fmt.amount(consensus, unit)}")\n'
                '        detail.append(f"surprise {fmt.signed(surprise, unit)}")\n'
                '    else:\n'
                '        what.append(f"actual {fmt.amount(actual, unit)}")\n'
                '    if "revision" in reasons:\n'
                '        what.append(f"previous revised from {fmt.amount(previous, unit)} to {fmt.amount(revised, unit)}")\n'
                '        detail.append(f"revision {fmt.signed(revision, unit)}")\n',
                '        what.append(f"actual {actual:g}{unit} vs consensus {consensus:g}{unit}")\n'
                '        detail.append(f"surprise {surprise:+.2f}{unit}")\n'
                '    else:\n'
                '        what.append(f"actual {actual:g}{unit}")\n'
                '    if "revision" in reasons:\n'
                '        what.append(f"previous revised from {previous:g}{unit} to {revised:g}{unit}")\n'
                '        detail.append(f"revision {revision:+.2f}{unit}")\n')]},
    {"script": "cheats/formatter_changed.sh",
     "name": "changes the shared formatter's change() to write a sign, for the release message",
     "edits": [("alertd/format.py", '    if _rounds_to_zero(text):\n        return "unchanged"\n'
                                    '    return ("up " if value > 0 else "down ") + text\n',
                '    if _rounds_to_zero(text):\n        return text\n'
                '    return ("+" if value > 0 else "-") + text\n'),
               (RELEASE_PY, 'detail.append(f"surprise {fmt.signed(surprise, unit)}")',
                'detail.append(f"surprise {fmt.change(surprise, unit)}")'),
               (RELEASE_PY, 'detail.append(f"revision {fmt.signed(revision, unit)}")',
                'detail.append(f"revision {fmt.change(revision, unit)}")')]},
    {"script": "cheats/suppress_reordered.sh",
     "name": "brings alertd/suppress.py into line with docs/ARCHITECTURE.md's order",
     "edits": [("alertd/suppress.py", 'ORDER = ("stale", "muted", "quiet_hours", "cooldown", "daily_cap")\n',
                'ORDER = ("muted", "quiet_hours", "cooldown", "daily_cap", "stale")  # docs/ARCHITECTURE.md\n')]},
    {"script": "cheats/renames_config_key.sh",
     "name": "renames price_move's thresholds to price_move.thresholds.<measure>, like the release thresholds",
     "edits": [("alertd/defaults.toml",
                "threshold_pct = 1.5            # a price move of at least this many percent is a warning\n"
                "threshold_bp = 8.0             # a yield move of at least this many basis points is a warning\n",
                "thresholds.pct = 1.5           # a price move of at least this many percent is a warning\n"
                "thresholds.bp = 8.0            # a yield move of at least this many basis points is a warning\n"),
               ("config/alerts.toml", "[price_move]\nthreshold_pct = 2.0\n", "[price_move]\nthresholds.pct = 2.0\n"),
               ("alertd/rules/price_move.py",
                '    threshold = settings["threshold_pct"] if measure == "pct" else settings["threshold_bp"]\n',
                '    threshold = settings["thresholds"][measure]\n')]},
]


def apply_edits(files: dict[str, str], edits: list) -> dict[str, str]:
    files = dict(files)
    for rel, old, new in edits:
        assert files[rel].count(old) == 1, (rel, old)
        files[rel] = files[rel].replace(old, new)
    return files


def cheat_script(wrong: dict, starter: dict[str, str], package: dict[str, str]) -> str:
    """A self-contained script that writes the wrong solution's files over the starter in /app."""
    changed = {rel: text for rel, text in sorted(package.items())
               if starter.get(rel) != text and not rel.startswith("tests/")}
    payload = json.dumps(changed, sort_keys=True)
    assert "'''" not in payload
    return (f"#!/bin/bash\n# {CANARY}\n# A CHEAT (generate.py): {wrong['name']}.\n"
            f"# It writes these files over the starter: {', '.join(changed)}.\nset -e\npython3 - <<'EOF'\n"
            f"import json\nfrom pathlib import Path\n\nFILES = json.loads(r'''{payload}''')\n"
            "for rel, text in FILES.items():\n    path = Path('/app') / rel\n"
            "    path.parent.mkdir(parents=True, exist_ok=True)\n    path.write_text(text, encoding='utf-8')\nEOF\n")


# ----- the checks, as the grader applies them ------------------------------------------------------------------------


def all_runs(cases: dict) -> list[tuple]:
    runs = [(f["feed"], f["state"], None) for f in cases["release_feeds"]]
    runs += [(f["feed"], f["state"], cases["hidden_config"]) for f in cases["release_feeds"]]
    runs += [(f["feed"], f["state"], None) for f in cases["mixed_feeds"]]
    runs += [(f["feed"], f["state"], cases["existing_configs"][name]) for f in cases["existing_feeds"]
             for name in ("room", "hidden")]
    return runs


def split_outputs(cases: dict, outputs: list[tuple]) -> dict:
    n_rel, n_mix = len(cases["release_feeds"]), len(cases["mixed_feeds"])
    return {"room": outputs[:n_rel], "hidden": outputs[n_rel:2 * n_rel], "mixed": outputs[2 * n_rel:2 * n_rel + n_mix],
            "existing": outputs[2 * n_rel + n_mix:]}


def failing_checks(cases: dict, outputs: list[tuple], tests: dict[str, str]) -> set[str]:
    """The checks a package fails, by the same comparisons as tests/test_outputs.py."""
    out = split_outputs(cases, outputs)
    problems = {name: [] for name in CHECKS}
    for feed, room, hidden in zip(cases["release_feeds"], out["room"], out["hidden"]):
        problems["decisions"] += compare.decision_problems(feed["room"], room[1])
        problems["messages"] += compare.message_problems(feed["room"], room[1])
        problems["settings"] += compare.decision_problems(feed["hidden"], hidden[1])
    for feed, got in zip(cases["mixed_feeds"], out["mixed"]):
        problems["machinery"] += compare.decision_problems(feed["expected"], got[1])
    pairs = [(feed, name) for feed in cases["existing_feeds"] for name in ("room", "hidden")]
    for (feed, name), got in zip(pairs, out["existing"]):
        problem = compare.output_problem(tuple(feed["expected"][name]), got[:2])
        if problem:
            problems["unchanged"].append(f"{feed['name']} ({name}): {problem}")
    problems["original_tests"] = [t for t in cases["original_tests"] if tests.get(t) != "passed"]
    return {name for name, found in problems.items() if found}


# ----- proofs ------------------------------------------------------------------------------------------------------


def desk_page_examples(page: str) -> list[tuple[dict, dict]]:
    lines = [json.loads(line.strip()) for line in page.splitlines() if line.startswith("    {")]
    assert len(lines) == 12, len(lines)
    return list(zip(lines[0::2], lines[1::2]))


def candidates(original_output: str, events: list[dict]) -> dict:
    """The existing kinds' findings in a feed, from the starter run with nothing that suppresses but staleness."""
    found = {}
    for line in parse_lines(original_output):
        if line["level"] is None:
            found[line["id"]] = None
            found[line["id"] + "/key"] = line["key"]
        elif line["sent"]:
            found[line["id"]] = {"key": line["key"], "level": line["level"], "reasons": line["reasons"],
                                 "message": line["message"], "stale": False}
        else:
            assert line["reasons"][-1] == "stale", line
            found[line["id"]] = {"key": line["key"], "level": line["level"], "reasons": line["reasons"][:-1],
                                 "message": None, "stale": True}
    assert {e["id"] for e in events if e["kind"] != "release"} <= set(found), "a candidate is missing"
    return found


def main():
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    rng = random.Random(SEED)
    room = read_tree(APP, leave_out=("examples",))
    solution = {rel: text for rel, text in read_tree(SOLUTION).items() if rel != "solve.sh"}
    room_config = room["config/alerts.toml"]
    assert solution["alertd/defaults.toml"].startswith(room["alertd/defaults.toml"])
    assert solution["config/alerts.toml"].startswith(room_config)
    alerts = {**tomllib.loads(room["alertd/defaults.toml"])["alerts"], **tomllib.loads(room_config)["alerts"]}

    # The examples: feeds, the state, and the decisions the starter prints for the four existing kinds
    feeds = example_feeds()
    examples = {f"examples/feed-{kind}.jsonl": jsonl(rows) for kind, rows in feeds.items()}
    examples["examples/state.json"] = state_text(EXAMPLE_STATE)
    existing_kinds = ("price_move", "limit_usage", "stale_feed", "news")
    printed = run_package({**room, **examples}, [(examples[f"examples/feed-{k}.jsonl"], examples["examples/state.json"],
                                                  None) for k in existing_kinds])
    for kind, (code, stdout, stderr) in zip(existing_kinds, printed):
        assert code == 0 and not stderr, (kind, stderr)
        examples[f"examples/decisions-{kind}.jsonl"] = stdout
    starter = {**room, **examples}
    reference = {**starter, **solution}
    shown = "".join(examples[f"examples/decisions-{k}.jsonl"] for k in existing_kinds)
    for line in re.findall(r"^    (\{.*\})$", room["README.md"], re.MULTILINE):
        assert line + "\n" in shown, f"README.md example not printed: {line}"
    messages = {d["message"] for d in map(json.loads, shown.splitlines()) if d["message"]}
    for page in ("price-moves", "limit-usage", "stale-feeds", "news"):
        for line in re.findall(r"^    ((?:INFO|WARNING|CRITICAL) .*)$", room[f"docs/desk/{page}.md"], re.MULTILINE):
            assert line in messages, f"docs/desk/{page}.md example not printed: {line}"

    # Hidden data
    rel_feeds, mix_feeds, old_feeds = release_feeds(rng), mixed_feeds(rng), existing_feeds()
    hidden_config = hidden_release_config(room_config)
    cases = {"_canary": CANARY, "release_feeds": rel_feeds, "hidden_config": hidden_config, "mixed_feeds": mix_feeds,
             "existing_feeds": old_feeds, "existing_configs": {"room": room_config, "hidden": HIDDEN_EXISTING_CONFIG}}
    runs = all_runs(cases)
    quiet_off = room_config.replace('cooldown_minutes = 45\ndaily_cap = 20\nquiet_end = "07:00"\n',
                                    'cooldown_minutes = 0\ndaily_cap = 1000000\nquiet_start = "00:00"\nquiet_end = "00:00"\n')
    assert quiet_off != room_config
    candidate_runs = [(f["feed"], state_text({}), quiet_off) for f in mix_feeds]
    release_example = [(examples["examples/feed-release.jsonl"], examples["examples/state.json"], None)]
    with ThreadPoolExecutor(WORKERS) as pool:
        ref_future = pool.submit(run_package, reference, runs + release_example)
        start_future = pool.submit(run_package, starter, runs + candidate_runs)
        reference_out, starter_out = ref_future.result(), start_future.result()
    original = {rel: text for rel, text in starter.items()
                if rel.startswith(("tests/", "examples/")) or rel == "pyproject.toml"}

    # The worked examples on the desk page
    example_out = reference_out[-1]
    assert example_out[0] == 0 and not example_out[2], example_out
    example_decisions = {d["id"]: d for d in parse_lines(example_out[1])}
    page = room["docs/desk/release-alerts.md"]
    pairs = desk_page_examples(page)
    by_id = {e["id"]: e for e in feeds["release"]}
    assert [event["id"] for event, _ in pairs] == RELEASE_EXAMPLES
    for event, decision in pairs:
        assert event == by_id[event["id"]] and json.dumps(event) in examples["examples/feed-release.jsonl"]
        assert json.dumps(decision) in page and example_decisions[event["id"]] == decision, event["id"]
        mine = independent_release(event, ROOM)
        assert {"level": decision["level"], "reasons": decision["reasons"], "message": decision["message"]} == mine
    reference_out = reference_out[:-1]
    parts = split_outputs(cases, reference_out)
    start_parts = split_outputs(cases, starter_out[:len(runs)])
    candidate_out = starter_out[len(runs):]

    # The reference against the independent rules, and the expected decisions
    for feed, room_out, hidden_out in zip(rel_feeds, parts["room"], parts["hidden"]):
        events = parse_lines(feed["feed"])
        state = json.loads(feed["state"])
        for config, got, thresholds, window in (("room", room_out, ROOM, ROOM_STALE),
                                                ("hidden", hidden_out, HIDDEN, HIDDEN_STALE)):
            assert got[0] == 0 and not got[2], (feed["name"], config, got[2][-500:])
            mine = independent_decisions(events, state, alerts, thresholds, window, {})
            assert parse_lines(got[1]) == mine, (feed["name"], config)
            feed[config] = mine
    for feed, got, cand in zip(mix_feeds, parts["mixed"], candidate_out):
        events = parse_lines(feed["feed"])
        assert got[0] == 0 and not got[2] and cand[0] == 0, feed["name"]
        mine = independent_decisions(events, json.loads(feed["state"]), alerts, ROOM, ROOM_STALE,
                                     candidates(cand[1], events))
        assert parse_lines(got[1]) == mine, feed["name"]
        feed["expected"] = mine
    pairs = [(feed, name) for feed in old_feeds for name in ("room", "hidden")]
    for feed in old_feeds:
        feed["expected"] = {}
    for (feed, name), mine, start in zip(pairs, parts["existing"], start_parts["existing"]):
        assert start[0] == 0 and not start[2], (feed["name"], name, start[2])
        assert mine[:2] == start[:2], (feed["name"], name)
        feed["expected"][name] = [start[0], start[1]]

    # Original tests: the starter and the reference pass them all
    with ThreadPoolExecutor(WORKERS) as pool:
        start_tests, ref_tests = pool.map(lambda p: original_tests(p, original), (starter, reference))
    assert start_tests and set(start_tests.values()) == {"passed"}, start_tests
    assert ref_tests == start_tests, {t: s for t, s in ref_tests.items() if s != "passed"}
    cases["original_tests"] = sorted(start_tests)

    # Coverage and the hidden config's effect
    room_rows = [d for f in rel_feeds for d in f["room"]]
    hidden_rows = [d for f in rel_feeds for d in f["hidden"]]
    events = [e for f in rel_feeds for e in parse_lines(f["feed"])]
    assert {e["unit"] for e in events} == {"pct", "k", "bn"} and {e["importance"] for e in events} == {"high", "medium", "low"}
    assert any(e["consensus"] is None for e in events) and any(e["revised"] is None for e in events)
    assert any(e["revised"] is not None and e["revised"] == e["previous"] for e in events)
    assert {d["level"] for d in room_rows} == {None, "info", "warning", "critical"}
    assert {tuple(r for r in d["reasons"] if r in ("surprise", "revision")) for d in room_rows} == {
        (), ("surprise",), ("revision",), ("surprise", "revision")}
    assert {d["reasons"][-1] for d in room_rows if d["level"] and not d["sent"]} == {
        "stale", "muted", "quiet_hours", "cooldown", "daily_cap"}
    sent_messages = [d["message"] for d in room_rows if d["sent"]]
    for pattern in ("surprise +", "surprise -", "revision +", "revision -", "%", "k ", "bn", ",", "INFO", "WARNING",
                    "CRITICAL"):
        assert any(pattern in m for m in sent_messages), pattern
    assert any(d["level"] == "critical" and d["sent"] and d["reasons"] for d in room_rows)
    changed = [a["id"] for a, b in zip(room_rows, hidden_rows)
               if (a["sent"], a["level"], a["reasons"]) != (b["sent"], b["level"], b["reasons"])]
    by_stale = [a["id"] for a, b in zip(room_rows, hidden_rows)
                if b["reasons"][-1:] == ["stale"] and a["reasons"][-1:] != ["stale"]]
    assert len(changed) >= 10 and by_stale and set(changed) - set(by_stale), (changed, by_stale)

    # Doing nothing and the wrong solutions fail exactly their declared checks
    toml = tomllib.loads((HERE / "deliverbench.toml").read_text(encoding="utf-8"))
    declared = {c["script"]: set(c["fails"]) for c in toml.get("cheats", [])}
    packages = {"[nop]": starter, **{w["script"]: apply_edits(reference, w["edits"]) for w in WRONG}}

    def judge(item):
        name, package = item
        return name, failing_checks(cases, run_package(package, runs), original_tests(package, original))

    with ThreadPoolExecutor(WORKERS) as pool:
        verdicts = dict(pool.map(judge, packages.items()))
    assert failing_checks(cases, reference_out, ref_tests) == set(), "the reference fails a check"
    wrong_declared = []
    for name, fails in verdicts.items():
        ids = {CHECKS[f] for f in fails}
        want = set(toml.get("nop", {}).get("fails", [])) if name == "[nop]" else declared.get(name)
        if ids != want:
            wrong_declared.append(f"{name}: fails {sorted(ids)}, declared {sorted(want) if want else want}")
    assert not wrong_declared, "\n".join(wrong_declared)

    # [settings] are what is generated here
    lines = sum(text.count("\n") for text in starter.values())
    facts = {
        "codebase_files": len(starter),
        "codebase_lines": lines,
        "code_lines": sum(t.count("\n") for r, t in starter.items() if r.startswith("alertd/") and r.endswith(".py")),
        "original_tests": len(cases["original_tests"]),
        "alert_kinds": 4,
        "suppressions": 5,
        "desk_examples": len(RELEASE_EXAMPLES),
        "release_feeds": len(rel_feeds),
        "release_events": len(events),
        "hidden_config_changes": len(changed),
        "hidden_stale_after_minutes": HIDDEN_STALE,
        "mixed_feeds": len(mix_feeds),
        "mixed_events": sum(len(parse_lines(f["feed"])) for f in mix_feeds),
        "mixed_release_events": sum(e["kind"] == "release" for f in mix_feeds for e in parse_lines(f["feed"])),
        "existing_feeds": len(old_feeds),
        "existing_events": sum(len(parse_lines(f["feed"])) for f in old_feeds),
        "existing_configs": 2,
        "wrong_solutions": len(WRONG),
    }
    settings = toml.get("settings", {})
    assert settings == facts, {k: (settings.get(k), v) for k, v in facts.items() if settings.get(k) != v}

    outputs = {
        **{f"environment/app/{rel}": text for rel, text in examples.items()},
        **{f"cheats/{w['script'][len('cheats/'):]}": cheat_script(w, starter, packages[w["script"]]) for w in WRONG},
        "tests/data/cases.json": json.dumps(cases, indent=1) + "\n",
        "tests/original/bundle.json": json.dumps({"_canary": CANARY, "files": original}, indent=1, sort_keys=True) + "\n",
    }
    for rel, text in outputs.items():
        path = out_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        if rel.startswith("cheats/"):
            path.chmod(0o755)
    print(f"T14: the room has {len(starter)} files and {lines:,} lines ({facts['code_lines']:,} in alertd's code), "
          f"{facts['original_tests']} original tests; {len(events)} hidden release events in {len(rel_feeds)} feeds "
          f"({len(changed)} decided otherwise under the hidden config), {facts['mixed_events']} events in "
          f"{len(mix_feeds)} mixed feeds, {facts['existing_events']} in {len(old_feeds)} feeds of the existing kinds; "
          f"{len(WRONG)} wrong solutions, each failing exactly its declared checks")


if __name__ == "__main__":
    main()
