"""The macro data vendor's service for T13: the one source of the room's sidecar and of the grading re-run's
service (generate.py copies it to environment/macro-api/macro_api.py and tests/macro_api.py), and of the
generator's in-process simulation (Vendor below, without HTTP).

GET /series/<id>?page=<n>   one page of 24 observations (date, value, vintage), with next_page
GET /series/<id>/meta       the series' title, first and last month, and number of months
GET /health                 {"ok": true}; never counted, never quirky

The data file sets everything the service does: the series and their metadata, the retired ids, and the quirks.
The quirks are deterministic, driven by the count of requests, never by clock or chance. They repeat in a cycle
of `cycle` counted requests, so every full run of a pipeline meets every kind, whatever came before it:
  - rate_limited {slot: seconds}  the request in that slot answers 429 with Retry-After: seconds;
  - passing {slot: status}        the request in that slot answers 500, 502 or 503;
  - repeat [slot, ...]            arms a repeated page: the next page request for page 2 or later (in that slot or
                                  after it) is answered with the page before the one asked for (its `page` says so);
  - a retired id answers 410 with {"replaced_by": <successor>}.
Every counted request is logged as a JSON line. `early`: it arrived before a 429's Retry-After had passed (counted
from the moment the 429 was sent, less TOLERANCE). `overlap`: it arrived while another request was in flight.

Run: python macro_api.py --data DATA.json --port 8090 --log LOG
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PAGE_SIZE = 24
TOLERANCE = 0.25   # seconds of grace on Retry-After
LATENCY = 0.025    # seconds each counted answer takes: a real vendor is not instant, and requests sent at once overlap
REASONS = {500: "internal error, try again", 502: "bad gateway, try again", 503: "service busy, try again"}


class Vendor:
    """The service's behaviour without HTTP: request() answers one counted request, sent() records that a 429 went
    out (its Retry-After counts from then)."""

    def __init__(self, data):
        self.series = data["series"]
        self.meta = data["meta"]
        self.retired = data["retired"]
        quirks = data["quirks"]
        self.cycle = int(quirks["cycle"])
        self.limited = {int(k): int(v) for k, v in quirks["rate_limited"].items()}
        self.passing = {int(k): int(v) for k, v in quirks["passing"].items()}
        self.arms = {int(k) for k in quirks["repeat"]}
        self.count = 0
        self.free_at = 0.0
        self.armed = False

    def pages(self, series_id):
        return -(-len(self.series[series_id]) // PAGE_SIZE)

    def page_body(self, series_id, page):
        last = self.pages(series_id)
        return {"id": series_id, "page": page,
                "observations": self.series[series_id][(page - 1) * PAGE_SIZE: page * PAGE_SIZE],
                "next_page": page + 1 if page < last else None}

    def request(self, target, now):
        """Answer GET target arriving at time now: (status, body, headers, log record)."""
        self.count += 1
        n = self.count
        slot = (n - 1) % self.cycle + 1
        early = now < self.free_at - TOLERANCE
        if slot in self.arms:
            self.armed = True
        repeated = False
        if slot in self.limited:
            seconds = self.limited[slot]
            status, body, headers = 429, {"error": "rate limit reached"}, {"Retry-After": str(seconds)}
        elif slot in self.passing:
            status = self.passing[slot]
            body, headers = {"error": REASONS[status]}, {}
        else:
            status, body, repeated = self.serve(target)
            headers = {}
        record = {"n": n, "t": round(now, 4), "path": target, "status": status, "early": early,
                  "overlap": False, "repeated": repeated}
        return status, body, headers, record

    def sent(self, status, headers, now):
        if status == 429:
            self.free_at = max(self.free_at, now + int(headers["Retry-After"]))

    def serve(self, target):
        url = urlsplit(target)
        parts = [p for p in url.path.split("/") if p]
        if len(parts) not in (2, 3) or parts[0] != "series" or (len(parts) == 3 and parts[2] != "meta"):
            return 404, {"error": "no such endpoint"}, False
        series_id = parts[1]
        if series_id in self.retired:
            return 410, {"error": "series retired", "replaced_by": self.retired[series_id]}, False
        if series_id not in self.series:
            return 404, {"error": "no such series"}, False
        if len(parts) == 3:
            return 200, self.meta[series_id], False
        raw = parse_qs(url.query).get("page", ["1"])[0]
        try:
            page = int(raw)
        except ValueError:
            return 400, {"error": "page must be a whole number"}, False
        if not 1 <= page <= self.pages(series_id):
            return 404, {"error": "no such page"}, False
        if self.armed and page >= 2:
            self.armed = False
            return 200, self.page_body(series_id, page - 1), True
        return 200, self.page_body(series_id, page), False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        vendor = Vendor(json.load(fh))
    lock = threading.Lock()
    state = {"open": 0}
    open(args.log, "a").close()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlsplit(self.path).path.rstrip("/") == "/health":
                return self._send(200, {"ok": True}, {})
            with lock:
                overlap = state["open"] > 0
                state["open"] += 1
                status, body, headers, record = vendor.request(self.path, time.monotonic())
                record["overlap"] = overlap
            time.sleep(LATENCY)
            with lock:
                state["open"] -= 1  # before the answer goes out: the client's next request can only follow it
                vendor.sent(status, headers, time.monotonic())
                with open(args.log, "a", encoding="utf-8") as log:
                    log.write(json.dumps(record) + "\n")
            self._send(status, body, headers)

        def _send(self, status, body, headers):
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

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
