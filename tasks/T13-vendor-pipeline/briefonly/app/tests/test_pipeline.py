"""Tests for pipeline.py against a fake Woodgrove gateway that misbehaves the way docs/vendor/macro-api.md says it may.

Run from the repo root: python -m pytest -q tests
"""
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipeline  # noqa: E402


# --------------------------------------------------------------------------------------------------------------
# A fake vendor: pages, vintages, 410s, and gateway faults; it records any breach of "one request at a time" and
# any request sent before a Retry-After wait was over.
# --------------------------------------------------------------------------------------------------------------

class FakeVendor:
    def __init__(self, series, retired=None, faults=None, page_size=4, retire_at=None, retry_after=1):
        self.series = series                # id -> observations, in order of date then vintage
        self.retired = dict(retired or {})  # id -> replaced_by
        self.faults = dict(faults or {})    # request number -> "429" | "500" | "502" | "503" | "stale"
        self.retire_at = retire_at          # (request number, id, successor): retire an id mid-run
        self.page_size = page_size
        self.retry_after = retry_after
        self.lock = threading.Lock()
        self.count = 0
        self.in_flight = 0
        self.not_before = 0.0
        self.breaches = []
        self.requests = []

    def answer(self, number, path):
        parts = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qs(parts.query)
        segments = parts.path.strip("/").split("/")
        fault = self.faults.get(number)
        if fault == "429":
            return 429, {"Retry-After": str(self.retry_after)}, {"error": "allowance used up"}
        if fault in ("500", "502", "503"):
            return int(fault), {}, {"error": "gateway busy"}
        if self.retire_at and number >= self.retire_at[0]:
            self.retired[self.retire_at[1]] = self.retire_at[2]
        if len(segments) < 2 or segments[0] != "series":
            return 404, {}, {"error": "no such endpoint"}
        sid = segments[1]
        if sid in self.retired:
            return 410, {}, {"error": "series retired", "replaced_by": self.retired[sid]}
        if sid not in self.series:
            return 404, {}, {"error": "no such series"}
        obs = self.series[sid]
        if len(segments) == 3 and segments[2] == "meta":
            months = sorted({o["date"] for o in obs})
            return 200, {}, {"id": sid, "first": months[0], "last": months[-1], "months": len(months),
                             "last_updated": max(o["vintage"] for o in obs)}
        page = int(query.get("page", ["1"])[0])
        if fault == "stale" and page > 1:
            page -= 1
        pages = max(1, -(-len(obs) // self.page_size))
        if page > pages:
            return 404, {}, {"error": "no such page"}
        chunk = obs[(page - 1) * self.page_size: page * self.page_size]
        return 200, {}, {"id": sid, "page": page, "observations": chunk,
                         "next_page": page + 1 if page < pages else None}

    def serve(self):
        vendor = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                with vendor.lock:
                    vendor.count += 1
                    number = vendor.count
                    if vendor.in_flight:
                        vendor.breaches.append(("overlap", number, self.path))
                    if time.monotonic() < vendor.not_before:
                        vendor.breaches.append(("early", number, self.path))
                    vendor.in_flight += 1
                    vendor.requests.append(self.path)
                time.sleep(0.02)  # long enough for an overlapping request to be caught
                status, headers, body = vendor.answer(number, self.path)
                with vendor.lock:
                    if status == 429:
                        vendor.not_before = time.monotonic() + vendor.retry_after
                    vendor.in_flight -= 1
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


@pytest.fixture
def run_job(tmp_path, monkeypatch):
    servers = []

    def run(vendor):
        server = vendor.serve()
        servers.append(server)
        out = tmp_path / "out" / "regimes.csv"
        monkeypatch.setenv("MACRO_API_URL", f"http://127.0.0.1:{server.server_address[1]}/")
        monkeypatch.setenv("REGIMES_OUT", str(out))
        status = pipeline.main()
        assert vendor.breaches == []
        return status, out

    yield run
    for server in servers:
        server.shutdown()


def obs(date, value, vintage):
    return {"date": date, "value": value, "vintage": vintage}


# Growth: 2020-01..2020-11. 2020-01 and 2020-07 revised (latest counts); 2020-05 never published.
GROWTH = [
    obs("2020-01", "0.80", "2020-02-16"), obs("2020-01", "1.00", "2020-03-16"),
    obs("2020-02", "2.00", "2020-03-16"),
    obs("2020-03", "0.50", "2020-04-16"),
    obs("2020-04", "1.00", "2020-05-16"),
    obs("2020-05", ".", "2020-06-16"),
    obs("2020-06", "0.75", "2020-07-16"),
    obs("2020-07", "1.20", "2020-08-16"), obs("2020-07", "1.10", "2020-09-16"), obs("2020-07", "1.50", "2021-03-27"),
    obs("2020-08", "1.00", "2020-09-16"),
    obs("2020-09", "0.20", "2020-10-16"),
    obs("2020-10", "1.60", "2020-11-16"),
    obs("2020-11", "2.00", "2020-12-16"),
]
# Inflation: 2019-12..2020-10. 2020-04 revised.
INFLATION = [
    obs("2019-12", "1.00", "2020-01-12"),
    obs("2020-01", "2.00", "2020-02-12"),
    obs("2020-02", "2.50", "2020-03-12"),
    obs("2020-03", "3.00", "2020-04-12"),
    obs("2020-04", "2.40", "2020-05-12"), obs("2020-04", "2.10", "2020-06-12"),
    obs("2020-05", "2.00", "2020-06-12"),
    obs("2020-06", "3.00", "2020-07-12"),
    obs("2020-07", "1.99", "2020-08-12"),
    obs("2020-08", "2.00", "2020-09-12"),
    obs("2020-09", "2.50", "2020-10-12"),
    obs("2020-10", "2.10", "2020-11-12"),
]
# Worked by hand from the figures above.
EXPECTED = (
    "month,growth_change,inflation_change,regime\n"
    "2020-04,0.0000,0.1000,stagflation\n"   # growth 1.00-1.00 is not above zero
    "2020-06,0.2500,0.0000,goldilocks\n"    # inflation 3.00-3.00 is not above zero
    "2020-07,0.5000,-0.1100,goldilocks\n"
    "2020-09,-0.5500,-0.5000,deflation\n"
    "2020-10,0.1000,0.1100,reflation\n"
)


def test_table_through_gateway_faults_and_a_chain_of_retirements(run_job):
    vendor = FakeVendor(
        {"IP_YOY": GROWTH, "CPI_MID": INFLATION, "CPI_NEW": INFLATION},
        retired={"CPI_OLD": "CPI_MID", "CPI_MID": "CPI_NEW"},
        faults={1: "503", 2: "429", 4: "stale", 5: "stale", 7: "500", 9: "502", 11: "stale", 13: "429"},
    )
    status, out = run_job(vendor)
    assert status == 0
    assert out.read_text(encoding="utf-8") == EXPECTED


def test_series_retired_mid_run_is_followed(run_job):
    # CPI_OLD answers its first pages, then is retired; its successor carries the same history.
    vendor = FakeVendor({"IP_YOY": GROWTH, "CPI_OLD": INFLATION, "CPI_YOY": INFLATION},
                        retire_at=(8, "CPI_OLD", "CPI_YOY"))
    status, out = run_job(vendor)
    assert status == 0
    assert out.read_text(encoding="utf-8") == EXPECTED


def test_unknown_series_alerts_and_writes_nothing(run_job):
    status, out = run_job(FakeVendor({"IP_YOY": GROWTH}))
    assert status == 1
    assert not out.exists()


def test_missing_months_alert(run_job):
    gappy = [o for o in GROWTH if o["date"] != "2020-03"]
    status, out = run_job(FakeVendor({"IP_YOY": gappy, "CPI_OLD": INFLATION}))
    assert status == 1
    assert not out.exists()


def test_replaced_by_loop_alerts(run_job):
    vendor = FakeVendor({"IP_YOY": GROWTH}, retired={"CPI_OLD": "CPI_A", "CPI_A": "CPI_OLD"})
    status, out = run_job(vendor)
    assert status == 1
    assert not out.exists()


def test_latest_vintage_wins_across_pages():
    figures = pipeline.latest_vintages("X", [
        obs("2020-01", "1.00", "2020-02-01"), obs("2020-01", "1.20", "2020-03-01"),
        obs("2020-01", ".", "2020-01-20"),
    ])
    assert figures == {"2020-01": ("2020-03-01", "1.20")}


def test_change_uses_calendar_months_and_never_prints_negative_zero():
    figures = {"2020-01": Decimal("-0.00"), "2020-02": Decimal("1.00"), "2020-03": None,
               "2020-04": Decimal("0.00"), "2020-05": Decimal("3.00")}
    assert format(pipeline.three_month_change(figures, "2020-04"), "f") == "0.0000"
    assert pipeline.three_month_change(figures, "2020-05") == Decimal("2.0000")
    assert pipeline.three_month_change(figures, "2020-06") is None  # 2020-03 has no figure
    assert pipeline.three_month_change({"2019-11": Decimal("1"), "2020-02": Decimal("2")}, "2020-02") == 1


@pytest.mark.parametrize("g, i, name", [
    ("0.01", "0.01", "reflation"), ("0.01", "0", "goldilocks"), ("0", "0.01", "stagflation"),
    ("0", "0", "deflation"), ("-0.01", "-0.01", "deflation"),
])
def test_regime(g, i, name):
    assert pipeline.regime(Decimal(g), Decimal(i)) == name
