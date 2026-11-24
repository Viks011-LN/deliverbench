#!/usr/bin/env python3
"""Monthly growth-and-inflation regime table, straight from Woodgrove Macro Data.

Growth is industrial production, year on year (series IP_YOY); inflation is CPI, year on year (series CPI_OLD).
For every month: each series' change over three months (this month's figure minus the figure three calendar
months earlier, to 4 decimal places), and a regime from the signs of the two changes.

Settings (README.md):
  MACRO_API_URL  the vendor's base address  (default http://localhost:8090)
  REGIMES_OUT    where the table is written  (default output/regimes.csv; a relative path is from the repo root)

Exit status 0 only when the table has been written; anything else raises an alert on the desk.

Vendor behaviour handled (docs/vendor/macro-api.md):
  - pages of up to 24 observations, followed through `next_page` until it is null              (2.1)
  - every vintage is kept; the figure as it stands today is a month's latest vintage, and a
    month's vintages may continue on the next page, so all pages are read before choosing     (4)
  - "." means no figure was published; it is not zero                                          (3)
  - a retired series answers 410 with `replaced_by`; the successor is followed at run time,
    through a chain if need be, and is never written into this file                           (5)
  - 429 with Retry-After: nothing is sent until that many seconds after the 429 arrived        (6, 7)
  - 500, 502, 503 are passing errors: the same request is sent again                           (6)
  - the gateway may answer with the page before the one asked for: the answer's `page` is
    checked and the page asked for is requested again                                         (6)
  - one request at a time                                                                      (7)
  - the series information endpoint is used to check that every month was received            (2.2)
"""

import csv
import http.client
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# The series, named only by the ids the ticket gives. Successors of retired ids are found at run time.
GROWTH_SERIES = "IP_YOY"
INFLATION_SERIES = "CPI_OLD"

DEFAULT_API_URL = "http://localhost:8090"
DEFAULT_OUT = "output/regimes.csv"
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

LOOKBACK_MONTHS = 3
FOUR_DP = Decimal("0.0001")
COLUMNS = ["month", "growth_change", "inflation_change", "regime"]
MISSING = "."  # the vendor's "no figure was published" marker (section 3)

# Retry policy. One request at a time, always; these only bound how long we keep trying one request.
REQUEST_TIMEOUT = 120.0     # seconds to wait for an answer (answers normally take under a second)
PASSING_STATUSES = {500, 502, 503}
MAX_PASSING_RETRIES = 12    # consecutive passing errors or lost connections for one request
MAX_RATE_LIMITS = 30        # consecutive 429s for one request
MAX_STALE_PAGES = 12        # consecutive "page before" answers for one page
MAX_SUCCESSORS = 10         # longest replaced_by chain followed
RETRY_AFTER_MARGIN = 1.0    # seconds added to Retry-After, so we are never early
RETRY_AFTER_FALLBACK = 10   # seconds, only if a 429 ever came without a usable Retry-After

MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


class PipelineError(Exception):
    """Anything that stops the job from producing a table it can stand behind."""


def log(message):
    print(f"[regimes] {message}", file=sys.stderr, flush=True)


def backoff(attempt):
    """Pause before resending after the n-th consecutive passing failure: 0.5s, 1s, 2s, 4s, then 8s."""
    return min(0.5 * 2 ** (attempt - 1), 8.0)


# --------------------------------------------------------------------------------------------------------------
# The vendor's API
# --------------------------------------------------------------------------------------------------------------

class VendorClient:
    """Sends one request at a time and rides out the gateway: 429 waits, passing errors, lost connections."""

    def __init__(self, base_url, timeout=REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._not_before = 0.0  # monotonic time before which no request may be sent
        self.stats = {"requests": 0, "rate_limited": 0, "passing_errors": 0, "network_errors": 0}

    def hold(self, seconds):
        """Send nothing for at least `seconds` from now."""
        self._not_before = max(self._not_before, time.monotonic() + seconds)

    def _send(self, url):
        """One GET, waiting for its whole answer. Returns (status, headers, body bytes)."""
        request = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "macro-desk-regimes/1.0"})
        self.stats["requests"] += 1
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as err:
            try:
                body = err.read()
            except (OSError, http.client.HTTPException):
                body = b""
            finally:
                err.close()
            return err.code, err.headers, body

    def get(self, path, params=None):
        """GET `path`, retrying what the gateway says to retry. Returns (status, parsed JSON body)."""
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        passing = 0
        limited = 0
        while True:
            wait = self._not_before - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                status, headers, raw = self._send(url)
            except (OSError, http.client.HTTPException) as err:
                # No answer at all (refused, reset, timed out). Treat it like a passing error.
                self.stats["network_errors"] += 1
                passing += 1
                if passing > MAX_PASSING_RETRIES:
                    raise PipelineError(f"GET {url}: no answer after {passing} tries ({err})") from err
                pause = max(backoff(passing), 2.0)
                log(f"GET {url}: no answer ({err.__class__.__name__}: {err}); trying again in {pause:.1f}s")
                self.hold(pause)
                continue
            arrived = time.monotonic()

            if status == 429:
                # The wait counts from the moment the 429 arrives; a 429'd request was not served.
                self.stats["rate_limited"] += 1
                limited += 1
                if limited > MAX_RATE_LIMITS:
                    raise PipelineError(f"GET {url}: still rate-limited after {limited} waits")
                retry_after = parse_retry_after(headers.get("Retry-After"))
                self._not_before = max(self._not_before, arrived + retry_after + RETRY_AFTER_MARGIN)
                log(f"GET {url}: 429, waiting {retry_after}s (+{RETRY_AFTER_MARGIN:g}s margin)")
                continue

            if status in PASSING_STATUSES:
                self.stats["passing_errors"] += 1
                passing += 1
                if passing > MAX_PASSING_RETRIES:
                    raise PipelineError(f"GET {url}: {status} on {passing} tries in a row")
                pause = backoff(passing)
                log(f"GET {url}: passing error {status}; sending it again in {pause:.1f}s")
                self._not_before = max(self._not_before, arrived + pause)
                continue

            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as err:
                if status == 200:
                    # A 200 we cannot read is no answer; ask again rather than guess.
                    passing += 1
                    if passing > MAX_PASSING_RETRIES:
                        raise PipelineError(f"GET {url}: unreadable 200 answer on {passing} tries") from err
                    log(f"GET {url}: 200 with a body that is not JSON; asking again")
                    self._not_before = max(self._not_before, arrived + backoff(passing))
                    continue
                body = {"error": raw[:200].decode("utf-8", "replace")}
            return status, body


def parse_retry_after(value):
    """Retry-After is a whole number of seconds (section 7)."""
    try:
        seconds = int(str(value).strip())
        if seconds >= 0:
            return seconds
    except (TypeError, ValueError):
        pass
    log(f"429 without a usable Retry-After ({value!r}); waiting {RETRY_AFTER_FALLBACK}s")
    return RETRY_AFTER_FALLBACK


def error_text(body):
    if isinstance(body, dict) and body.get("error"):
        return str(body["error"])
    return json.dumps(body)[:200]


def successor_of(retired_id, body, chain):
    """The id a 410 names in `replaced_by`, checked, and added to `chain`."""
    successor = body.get("replaced_by") if isinstance(body, dict) else None
    if not isinstance(successor, str) or not successor.strip():
        raise PipelineError(f"series {retired_id} is retired (410) but names no successor: {error_text(body)}")
    successor = successor.strip()
    if successor in chain:
        raise PipelineError(f"replaced_by chain loops: {' -> '.join(chain + [successor])}")
    if len(chain) > MAX_SUCCESSORS:
        raise PipelineError(f"replaced_by chain too long: {' -> '.join(chain + [successor])}")
    chain.append(successor)
    log(f"series {retired_id} is retired; following replaced_by to {successor}")
    return successor


def series_path(series_id, suffix=""):
    return "/series/" + urllib.parse.quote(series_id, safe="") + suffix


def fetch_observations(client, series_id):
    """Every observation of a series, all vintages, all pages.

    Returns (chain of ids followed, observations). The first id in the chain is the one we were given;
    the last is the one that answered.
    """
    chain = [series_id]
    current = series_id
    page = 1
    observations = []
    stale = 0
    while True:
        status, body = client.get(series_path(current), {"page": page})

        if status == 410:
            # The successor carries the whole history, revisions included, in the same pages. Start it from
            # page 1 so every observation we keep comes from the one series that answered.
            current = successor_of(current, body, chain)
            page, observations, stale = 1, [], 0
            continue
        if status == 404:
            raise PipelineError(f"series {current} page {page}: 404 ({error_text(body)})")
        if status != 200:
            raise PipelineError(f"series {current} page {page}: unexpected {status} ({error_text(body)})")
        if not isinstance(body, dict):
            raise PipelineError(f"series {current} page {page}: answer is not a JSON object")

        held = body.get("page")
        if isinstance(held, bool) or not isinstance(held, int):
            raise PipelineError(f"series {current} page {page}: answer has no page number ({held!r})")
        if held != page:
            # The gateway answered with another page (normally the one before). Ask for ours again.
            stale += 1
            if stale > MAX_STALE_PAGES:
                raise PipelineError(f"series {current}: asked for page {page} {stale} times, got page {held}")
            log(f"series {current}: asked for page {page}, got page {held}; asking again")
            client.hold(backoff(stale))
            continue
        stale = 0

        if body.get("id") not in (None, current):
            log(f"series {current} page {page}: answer is labelled {body.get('id')!r}")
        batch = body.get("observations")
        if not isinstance(batch, list):
            raise PipelineError(f"series {current} page {page}: no observations list")
        observations.extend(batch)

        next_page = body.get("next_page")
        if next_page is None:
            break
        if isinstance(next_page, bool) or not isinstance(next_page, int) or next_page <= page:
            raise PipelineError(f"series {current} page {page}: bad next_page {next_page!r}")
        page = next_page

    log(f"series {series_id}: {len(observations)} observations on {page} pages from {current}")
    return chain, observations


def fetch_meta(client, series_id):
    """Series information (section 2.2), following any 410. Returns None if the endpoint is not there."""
    chain = [series_id]
    current = series_id
    while True:
        status, body = client.get(series_path(current, "/meta"))
        if status == 410:
            current = successor_of(current, body, chain)
            continue
        if status == 200 and isinstance(body, dict):
            return body
        if status == 404:
            log(f"series {current}: no series information ({error_text(body)}); skipping that cross-check")
            return None
        raise PipelineError(f"series {current} meta: unexpected {status} ({error_text(body)})")


# --------------------------------------------------------------------------------------------------------------
# Figures as they stand today
# --------------------------------------------------------------------------------------------------------------

def month_index(month):
    match = MONTH_RE.match(month)
    if not match:
        raise PipelineError(f"not a YYYY-MM month: {month!r}")
    return int(match.group(1)) * 12 + int(match.group(2)) - 1


def month_name(index):
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def parse_value(series_id, month, value):
    """A figure as a Decimal, or None where the vendor published no figure (".", section 3)."""
    if isinstance(value, str):
        text = value.strip()
        if text == MISSING:
            return None
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        text = repr(value)
    elif value is None:
        log(f"series {series_id} {month}: null value, taken as no figure")
        return None
    else:
        raise PipelineError(f"series {series_id} {month}: unreadable value {value!r}")
    try:
        figure = Decimal(text)
    except InvalidOperation as err:
        raise PipelineError(f"series {series_id} {month}: unreadable value {value!r}") from err
    if not figure.is_finite():
        raise PipelineError(f"series {series_id} {month}: unreadable value {value!r}")
    return figure


def latest_vintages(series_id, observations):
    """Each month's latest vintage: {month: (vintage, raw value)}."""
    latest = {}
    for order, obs in enumerate(observations):
        if not isinstance(obs, dict):
            raise PipelineError(f"series {series_id}: observation is not an object: {obs!r}")
        month, vintage, value = obs.get("date"), obs.get("vintage"), obs.get("value")
        if not isinstance(month, str) or not MONTH_RE.match(month):
            raise PipelineError(f"series {series_id}: observation with a bad date: {obs!r}")
        if vintage is not None and (not isinstance(vintage, str) or not DATE_RE.match(vintage)):
            raise PipelineError(f"series {series_id} {month}: bad vintage {vintage!r}")
        key = (vintage or "", order)
        held = latest.get(month)
        if held is not None and held[0][0] == key[0] and held[1] != value:
            log(f"series {series_id} {month}: two figures with vintage {vintage} "
                f"({held[1]!r}, {value!r}); keeping the later one in the vendor's order")
        if held is None or key >= held[0]:
            latest[month] = (key, value)
    return {month: (key[0], value) for month, (key, value) in latest.items()}


def figures_today(series_id, observations, meta):
    """{month: Decimal or None} from each month's latest vintage, after checking nothing is missing."""
    latest = latest_vintages(series_id, observations)
    if not latest:
        raise PipelineError(f"series {series_id}: no observations")

    # Every month from first to last appears in the series (section 3): a gap means data went missing.
    indices = sorted(month_index(m) for m in latest)
    first, last = month_name(indices[0]), month_name(indices[-1])
    if len(indices) != indices[-1] - indices[0] + 1:
        have = set(indices)
        gaps = [month_name(i) for i in range(indices[0], indices[-1] + 1) if i not in have]
        raise PipelineError(f"series {series_id}: months missing between {first} and {last}: {gaps[:12]}")

    if meta is not None:
        expected = (meta.get("first"), meta.get("last"), meta.get("months"))
        if expected != (first, last, len(indices)):
            raise PipelineError(
                f"series {series_id}: received {first}..{last} ({len(indices)} months), but the series "
                f"information says {expected[0]}..{expected[1]} ({expected[2]} months)")
        newest = max((v for v, _ in latest.values() if v), default="")
        updated = meta.get("last_updated")
        if isinstance(updated, str) and newest < updated:
            raise PipelineError(f"series {series_id}: newest vintage received is {newest}, "
                                f"but the series was last updated {updated}")
        if newest != updated:
            log(f"series {series_id}: newest vintage {newest}, series information says {updated}")

    figures = {month: parse_value(series_id, month, value) for month, (_, value) in latest.items()}
    published = sum(1 for f in figures.values() if f is not None)
    log(f"series {series_id}: {first}..{last}, {len(figures)} months, {published} with a figure today")
    return figures


# --------------------------------------------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------------------------------------------

def three_month_change(figures, month):
    """This month's figure minus the figure three calendar months earlier, to 4 dp; None if either is missing."""
    now = figures.get(month)
    before = figures.get(month_name(month_index(month) - LOOKBACK_MONTHS))
    if now is None or before is None:
        return None
    change = (now - before).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
    return change if change != 0 else Decimal("0.0000")  # never "-0.0000"


def regime(growth_change, inflation_change):
    growth_up = growth_change > 0
    inflation_up = inflation_change > 0
    if growth_up and inflation_up:
        return "reflation"
    if growth_up:
        return "goldilocks"
    if inflation_up:
        return "stagflation"
    return "deflation"


def build_table(growth, inflation):
    rows = []
    for month in sorted(set(growth) & set(inflation), key=month_index):
        g = three_month_change(growth, month)
        i = three_month_change(inflation, month)
        if g is None or i is None:
            continue
        rows.append((month, g, i, regime(g, i)))
    return rows


def render_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for month, g, i, name in rows:
        writer.writerow([month, format(g, "f"), format(i, "f"), name])
    return buffer.getvalue()


def output_path():
    path = os.environ.get("REGIMES_OUT") or DEFAULT_OUT
    if not os.path.isabs(path):
        path = os.path.join(REPO_ROOT, path)
    return path


def main():
    base_url = os.environ.get("MACRO_API_URL") or DEFAULT_API_URL
    out = output_path()
    client = VendorClient(base_url)
    try:
        figures = {}
        for role, series_id in (("growth", GROWTH_SERIES), ("inflation", INFLATION_SERIES)):
            chain, observations = fetch_observations(client, series_id)
            meta = fetch_meta(client, chain[-1])
            figures[role] = figures_today(series_id, observations, meta)
        rows = build_table(figures["growth"], figures["inflation"])
        text = render_csv(rows)

        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except PipelineError as err:
        log(f"FAILED: {err}")
        log("nothing written")
        return 1
    except Exception as err:  # anything unexpected must still alert, not pass silently
        log(f"FAILED unexpectedly: {err.__class__.__name__}: {err}")
        log("nothing written")
        return 1

    counts = {}
    for row in rows:
        counts[row[3]] = counts.get(row[3], 0) + 1
    span = f"{rows[0][0]}..{rows[-1][0]}" if rows else "no months"
    log(f"wrote {len(rows)} rows ({span}) to {out}; regimes {counts}")
    log("requests {requests}, 429s {rate_limited}, passing errors {passing_errors}, "
        "lost connections {network_errors}".format(**client.stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
