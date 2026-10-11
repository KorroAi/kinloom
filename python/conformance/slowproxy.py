"""A proxy between a client and `kinloom serve` that holds every character declaration a moment, as a slow network
would, and notes any call that must wait for declarations but came first: `prepare` while one is still on its way (found
by proof/mod: Character() then Prepare() answered "ready" before the server knew the characters, so nothing was written
ahead), or a call naming a character whose declaration has not reached the server.

    proxy = SlowProxy(upstream_port); proxy.port ... proxy.problems ... proxy.close()"""
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOLD = 0.3           # seconds each /v1/character waits before it is passed on
HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization",
       "proxy-authenticate", "content-length"}


class SlowProxy:
    def __init__(self, upstream, hold=HOLD):
        self.upstream, self.hold = upstream, hold
        self.lock = threading.Lock()
        self.flying = {}            # session -> {name: number of declarations on their way}
        self.known = {}             # session -> names the server was told about
        self.problems = []
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"         # one request per connection, the body ends when it closes

            def log_message(self, *a):
                pass

            def do_GET(self):
                self._pass("GET", b"")

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self._pass("POST", body)

            def do_OPTIONS(self):
                self._pass("OPTIONS", b"")

            def _pass(self, method, body):
                verb = self.path.split("?")[0].rsplit("/", 1)[-1]
                session = self.headers.get("X-Kinloom-Session") or "default"
                try:
                    data = json.loads(body) if body else {}
                except ValueError:
                    data = {}
                name = data.get("name") if isinstance(data, dict) and isinstance(data.get("name"), str) else None
                if method == "POST" and verb == "character" and name:
                    with proxy.lock:
                        f = proxy.flying.setdefault(session, {})
                        f[name] = f.get(name, 0) + 1
                    time.sleep(proxy.hold)
                elif method == "POST" and verb in ("prepare", "save", "inspect"):
                    with proxy.lock:
                        waiting = sorted(n for n, k in proxy.flying.get(session, {}).items() if k)
                    if waiting:
                        proxy.note("%s sent while %s was still being declared" % (verb, ", ".join(waiting)))
                try:
                    status, headers, stream = proxy.forward(method, self.path, self.headers, body)
                finally:
                    if method == "POST" and verb == "character" and name:
                        with proxy.lock:
                            proxy.flying[session][name] -= 1
                            proxy.known.setdefault(session, set()).add(name)
                self.send_response(status)
                for k, v in headers:
                    if k.lower() not in HOP:
                        self.send_header(k, v)
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while True:
                        chunk = stream.read1(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except OSError:
                    pass
                finally:
                    stream.close()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def note(self, problem):
        with self.lock:
            if problem not in self.problems:
                self.problems.append(problem)

    def forward(self, method, path, headers, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.upstream, timeout=240)
        out = {k: v for k, v in headers.items() if k.lower() not in HOP}
        out["Host"] = "127.0.0.1:%d" % self.upstream
        if body or method == "POST":
            out["Content-Length"] = str(len(body))
        conn.request(method, path, body=body or None, headers=out)
        r = conn.getresponse()
        return r.status, r.getheaders(), r

    def close(self):
        self.server.shutdown()
        self.server.server_close()
