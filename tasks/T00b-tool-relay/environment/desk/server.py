"""Mock trading desk. Tool calls must carry the relay key; every call is logged, accepted or not."""
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = "/srv/log/desk.log"
KEY_FILE = "/run/dbench/relay-header"
KEY = secrets.token_hex(16)

os.makedirs(os.path.dirname(LOG), exist_ok=True)
open(LOG, "a").close()
os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
fd = os.open(KEY_FILE + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, f"X-Relay-Token: {KEY}\n".encode())
os.close(fd)
os.replace(KEY_FILE + ".tmp", KEY_FILE)

PRICES = {"ABC": "101.25"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._send(200, {"ok": True}) if self.path == "/health" else self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = None
        key_ok = secrets.compare_digest(self.headers.get("X-Relay-Token", ""), KEY)
        with open(LOG, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "path": self.path, "body": body, "key_ok": key_ok}) + "\n")
        if not key_ok:
            return self._send(403, {"error": "this desk only accepts calls made through the tools"})
        if self.path == "/tools/get_price":
            symbol = (body or {}).get("symbol")
            if symbol not in PRICES:
                return self._send(404, {"error": f"unknown symbol {symbol!r}"})
            return self._send(200, {"symbol": symbol, "price": PRICES[symbol]})
        if self.path == "/tools/book_ticket":
            return self._send(200, {"ticket_id": "TKT-0001", "status": "booked", **(body or {})})
        return self._send(404, {"error": "unknown tool"})

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


ThreadingHTTPServer(("127.0.0.1", 9000), Handler).serve_forever()
