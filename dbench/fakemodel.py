"""A scripted, OpenAI-compatible streaming model server for offline tests.

Used by the unit tests, and by dbench selftest to replay a scripted reference (solution/calls.json)
through the real agent.

Each POST to /v1/chat/completions takes a step from the script. In "sequence" mode (the default) it
takes the next one; in "by_turn" mode it takes the step numbered by how many assistant messages the
conversation already has, so several conversations can replay the same script at the same time.
Steps:
    {"say": "text"}                         plain content
    {"think": "text"}                       a reasoning field (named by "field", default reasoning_content)
    {"calls": [("bash", {...}), ...]}       tool calls; arguments are streamed in two pieces
    {"calls": [("bash", "raw text")]}       a raw (possibly malformed) arguments string
    {"finish_reason": "length"}             override the finish reason
    {"error": 500, "message": "..."}        an HTTP error instead of a stream
    {"hang": 2.0}                           send one chunk, then go silent for that many seconds
    {"hang_headers": 2.0}                   accept the request, then wait that long before answering at all
    {"stream_error": "message"}             send one chunk, then an error event inside the stream
    {"no_usage": true}                      leave out the usage chunk at the end of the stream
    {"usage": {"prompt_tokens": ...}}       report this usage instead of the default (100 in, 20 out)
Steps can be combined, e.g. {"think": "...", "calls": [...]}. Every request body is kept in .requests.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeModel:
    def __init__(self, script: list[dict], mode: str = "sequence", model_id: str = "fake-model",
                 context: int = 131072):
        self.script = list(script)
        self.mode = mode
        self.model_id = model_id
        self.context = context
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def _next(self, body: dict) -> dict:
        with self._lock:
            self.requests.append(body)
            if self.mode == "by_turn":
                turn = sum(1 for m in body.get("messages", []) if m.get("role") == "assistant")
                return self.script[turn] if turn < len(self.script) else {"say": "(script ran out)"}
            return self.script.pop(0) if self.script else {"say": "(script ran out)"}

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path.rstrip("/").endswith("/models"):
                    payload = json.dumps({"data": [{"id": fake.model_id, "max_model_len": fake.context}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                step = fake._next(body)
                if step.get("hang_headers"):
                    time.sleep(step["hang_headers"])
                if "error" in step:
                    payload = json.dumps({"error": {"message": step.get("message", "server error"),
                                                    "type": "error", "code": step["error"]}}).encode()
                    self.send_response(step["error"])
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    for chunk in fake._chunks(step):
                        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                        self.wfile.flush()
                        if step.get("stream_error"):
                            error = {"error": {"message": step["stream_error"], "type": "InternalServerError"}}
                            self.wfile.write(f"data: {json.dumps(error)}\n\n".encode())
                            self.wfile.flush()
                            return
                        if step.get("hang"):
                            time.sleep(step["hang"])
                            step = {**step, "hang": 0}
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        return Handler

    @staticmethod
    def _chunks(step: dict):
        def chunk(delta=None, finish=None, usage=None):
            c = {"id": "fake", "object": "chat.completion.chunk", "created": 0, "model": "fake-model",
                 "choices": [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]}
            if usage:
                c["usage"] = usage
            return c

        yield chunk({"role": "assistant", "content": ""})
        if step.get("think"):
            field = step.get("field", "reasoning_content")
            half = len(step["think"]) // 2
            yield chunk({field: step["think"][:half]})
            yield chunk({field: step["think"][half:]})
        if step.get("say"):
            yield chunk({"content": step["say"]})
        for i, (name, args) in enumerate(step.get("calls", [])):
            text = args if isinstance(args, str) else json.dumps(args)
            yield chunk({"tool_calls": [{"index": i, "id": f"call_{i}", "type": "function",
                                         "function": {"name": name, "arguments": ""}}]})
            yield chunk({"tool_calls": [{"index": i, "function": {"arguments": text[: len(text) // 2]}}]})
            yield chunk({"tool_calls": [{"index": i, "function": {"arguments": text[len(text) // 2:]}}]})
        finish = step.get("finish_reason") or ("tool_calls" if step.get("calls") else "stop")
        yield chunk({}, finish=finish)
        if not step.get("no_usage"):
            yield chunk(None, usage=step.get("usage") or {"prompt_tokens": 100, "completion_tokens": 20,
                                                          "total_tokens": 120})
