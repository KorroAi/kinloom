import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class FakeHTTP:
    """A local HTTP server answering from a queue of (status, body, headers); records every request."""

    def __init__(self):
        self.requests = []
        self.answers = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format, *args):
                pass

            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else ""
                outer.requests.append({"peer": self.client_address[1], "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": json.loads(body) if body else None})
                status, payload, headers = outer.answers.pop(0) if len(outer.answers) > 1 else outer.answers[0]
                if callable(payload):
                    payload = payload(outer.requests[-1])
                data = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                if "Content-Type" not in (headers or {}):
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = _answer
            do_POST = _answer

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(self, status=200, body=None, headers=None):
        self.answers.append((status, body if body is not None else {}, headers))
        return self

    def close(self):
        self.server.shutdown()


@pytest.fixture
def http():
    fake = FakeHTTP()
    yield fake
    fake.close()


def openai_reply(text, prompt=10, completion=3, cached=None):
    usage = {"prompt_tokens": prompt, "completion_tokens": completion}
    if cached is not None:
        usage["prompt_cache_hit_tokens"] = cached
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": usage}


@pytest.fixture(autouse=True)
def no_real_model(request, monkeypatch):
    """Tests never reach a real model: keys, model names and servers from the developer's environment are hidden,
    and a local Ollama is not probed (a test marked `ollama` fakes it itself)."""
    import os
    for var in list(os.environ):
        if var.endswith("_API_KEY") or var.startswith("KINLOOM_") or var.endswith("_BASE_URL"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("kinloom.harness._which", lambda exe: None)    # no real coding agent is ever started
    if request.node.get_closest_marker("ollama") is None:
        monkeypatch.setattr("kinloom.providers._ollama_models", lambda *a, **k: [])
