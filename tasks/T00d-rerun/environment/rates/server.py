"""Mock rates service. GET /rate returns a fixed rate; every request is logged as one JSON line."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = "/srv/log/requests.log"
os.makedirs(os.path.dirname(LOG), exist_ok=True)
open(LOG, "a").close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            with open(LOG, "a") as fh:
                fh.write(json.dumps({"t": time.time(), "method": "GET", "path": self.path}) + "\n")
        if self.path == "/rate":
            self._send(200, {"rate": "0.0425", "basis": "Actual/365"})
        elif self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
