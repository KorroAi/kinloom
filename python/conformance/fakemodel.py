"""A fake model server for the native SDK conformance: OpenAI-compatible (/v1/chat/completions, streamed or not,
/v1/audio/speech, /v1/audio/transcriptions) and Anthropic (/v1/messages). Answers come from a script per task (the
"Kinloom task: X" line of the system prompt), like KINLOOM_SCRIPT: a list is used in order (its last answer repeats),
a single answer repeats forever; the answer "!fail" is a failed call (HTTP 422). Every request is recorded; GET /log returns them, POST /reset starts again.

    python fakemodel.py <port> <script.json>
"""
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from kinloom.voice import tone  # noqa: E402

_TASK = re.compile(r"Kinloom task: (\w+)")


class Script:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.queues = {k: (list(v) if isinstance(v, list) else [v]) for k, v in self.data.items()}
            self.single = {k for k, v in self.data.items() if not isinstance(v, list)}
            self.log = []

    def answer(self, task):
        with self.lock:
            own = self.queues.get(task)
            if own and task in self.single:
                a = own[0]
            elif own:
                a = own.pop(0) if len(own) > 1 else own[0]
            else:
                shared = self.queues.get("*")
                if not shared:
                    return None
                a = shared.pop(0) if len(shared) > 1 else shared[0]
        return a if isinstance(a, str) else json.dumps(a)


def _text(content):
    """The text of a message content (a string, or OpenAI/Anthropic parts); pictures counted apart."""
    if isinstance(content, str):
        return content, 0
    texts, pictures = [], 0
    for part in content if isinstance(content, list) else []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            texts.append(str(part.get("text", "")))
        elif part.get("type") in ("image_url", "image"):
            pictures += 1
    return "\n".join(texts), pictures


def _pieces(text):
    """A streamed answer in small pieces (word by word), like a real model."""
    return re.findall(r"\S+\s*|\s+", text) or [text]


def make(script):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, status, payload, ctype="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/log":
                with script.lock:
                    self._send(200, list(script.log))
            else:
                self._send(404, {"error": "not found"})

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def do_POST(self):
            raw = self._body()
            path = self.path.split("?")[0]
            if path == "/reset":
                script.reset()
                self._send(200, {"ok": True})
                return
            if path.endswith("/audio/speech"):
                body = json.loads(raw.decode("utf-8"))
                text = str(body.get("input", ""))
                self._record({"api": "speech", "task": "speak", "input": text, "voice": body.get("voice"),
                              "instructions": body.get("instructions")})
                self._send(200, tone(0.1 + 0.02 * min(len(text), 100)), "audio/wav")
                return
            if path.endswith("/audio/transcriptions"):
                data, fmt = _file_part(raw, self.headers.get("Content-Type", ""))
                self._record({"api": "transcription", "task": "listen", "bytes": len(data), "format": fmt})
                self._send(200, {"text": "I heard %d bytes of %s" % (len(data), fmt or "audio")})
                return
            try:
                body = json.loads(raw.decode("utf-8"))
            except ValueError:
                self._send(400, {"error": {"message": "invalid json"}})
                return
            if path.endswith("/chat/completions"):
                self._openai(body)
            elif path.endswith("/messages"):
                self._anthropic(body)
            else:
                self._send(404, {"error": {"message": "unknown path %s" % path}})

        def _record(self, entry):
            with script.lock:
                script.log.append(entry)

        def _openai(self, body):
            messages = body.get("messages") or []
            system = next((m.get("content") for m in messages if m.get("role") == "system"), "")
            user, pictures = _text(next((m.get("content") for m in messages if m.get("role") == "user"), ""))
            task = (_TASK.search(system or "") or [None, "*"])[1]
            stream = bool(body.get("stream"))
            self._record({"api": "openai", "task": task, "system": system, "user": user, "pictures": pictures,
                          "json": body.get("response_format") == {"type": "json_object"},
                          "max_tokens": body.get("max_tokens", body.get("max_completion_tokens")), "stream": stream,
                          "model": body.get("model")})
            answer = script.answer(task)
            if answer is None or answer == "!fail":
                self._send(422, {"error": {"message": "no scripted answer for task %s" % task}})
                return
            usage = {"prompt_tokens": (len(system) + len(user)) // 4, "completion_tokens": len(answer) // 4}
            if not stream:
                self._send(200, {"choices": [{"message": {"role": "assistant", "content": answer}}], "usage": usage})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            for piece in _pieces(answer):
                self.wfile.write(("data: %s\n\n" % json.dumps({"choices": [{"delta": {"content": piece}}]})).encode("utf-8"))
            self.wfile.write(("data: %s\n\n" % json.dumps({"choices": [], "usage": usage})).encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True

        def _anthropic(self, body):
            system = body.get("system")
            if isinstance(system, list):
                system = "\n".join(str(b.get("text", "")) for b in system if isinstance(b, dict))
            messages = body.get("messages") or []
            user, pictures = _text(messages[0].get("content") if messages else "")
            task = (_TASK.search(system or "") or [None, "*"])[1]
            stream = bool(body.get("stream"))
            self._record({"api": "anthropic", "task": task, "system": system, "user": user, "pictures": pictures,
                          "json": False, "max_tokens": body.get("max_tokens"), "stream": stream, "model": body.get("model")})
            answer = script.answer(task)
            if answer is None or answer == "!fail":
                self._send(422, {"type": "error", "error": {"message": "no scripted answer for task %s" % task}})
                return
            usage = {"input_tokens": (len(system or "") + len(user)) // 4, "output_tokens": len(answer) // 4}
            if not stream:
                self._send(200, {"content": [{"type": "text", "text": answer}], "stop_reason": "end_turn", "usage": usage})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            events = [{"type": "message_start", "message": {"usage": {"input_tokens": usage["input_tokens"]}}}]
            events += [{"type": "content_block_delta", "delta": {"type": "text_delta", "text": p}} for p in _pieces(answer)]
            events += [{"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": usage["output_tokens"]}},
                       {"type": "message_stop"}]
            for e in events:
                self.wfile.write(("event: %s\ndata: %s\n\n" % (e["type"], json.dumps(e))).encode("utf-8"))
            self.wfile.flush()
            self.close_connection = True

    return Handler


def _file_part(raw, ctype):
    """The uploaded file of a multipart body and its format (from the file name)."""
    m = re.search(r"boundary=(.+)", ctype)
    if not m:
        return raw, None
    boundary = ("--" + m.group(1).strip()).encode("utf-8")
    for part in raw.split(boundary):
        head, _, data = part.partition(b"\r\n\r\n")
        name = re.search(rb'filename="([^"]*)"', head)
        if name:
            fmt = name.group(1).decode("utf-8", "replace").rsplit(".", 1)[-1] if b"." in name.group(1) else None
            return data[:-2] if data.endswith(b"\r\n") else data, fmt
    return b"", None


def serve(port, script_path):
    server = ThreadingHTTPServer(("127.0.0.1", port), make(Script(script_path)))
    server.daemon_threads = True
    server.handle_error = lambda request, address: None     # a client gone mid-request is not news
    return server


if __name__ == "__main__":
    srv = serve(int(sys.argv[1]), sys.argv[2])
    srv.serve_forever()
