"""Every native SDK with a real model: each SDK runs the conformance scenario (python/conformance) with its own brain,
its model calls going to OpenRouter (deepseek/deepseek-v4.1-flash) through a small local proxy that adds the key,
the model name and `reasoning: {"enabled": false}` (what the SDKs send themselves when their URL is OpenRouter's).
Voice requests go to the conformance fake (no voice key). Python is run the same way (`kinloom serve`, its model the
proxy) as the reference.

    OPENROUTER_API_KEY=... python proof/sdks/live.py [sdk ...]      # results-<date>.json next to this file

Reported per SDK: the scenario finished, its model requests and how many the model answered (HTTP 200), latency,
tokens, and the transcript to read. The key's billed usage is read before and after (GET /api/v1/key); the key is
never printed or saved.
"""
import datetime
import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "..", "..", "python", "conformance")
sys.path.insert(0, CONF)
import fakemodel  # noqa: E402
import native  # noqa: E402
import run as relay  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash"
UPSTREAM = "https://openrouter.ai/api/v1"
KEY = os.environ.get("OPENROUTER_API_KEY", "")


def usage():
    req = urllib.request.Request(UPSTREAM + "/key", headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return float(json.loads(r.read().decode("utf-8"))["data"]["usage"])


class Log:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = []
        self.sdk = "-"

    def add(self, **e):
        with self.lock:
            self.entries.append(dict(e, sdk=self.sdk))


LOG = Log()


def proxy(fake_base):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if not self.path.endswith("/chat/completions"):          # voice: the conformance fake
                req = urllib.request.Request(fake_base + self.path, data=body, method="POST",
                                             headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
                return self._relay(req, None)
            data = json.loads(body.decode("utf-8"))
            data["model"] = MODEL
            data["reasoning"] = {"enabled": False}
            data["usage"] = {"include": True}
            req = urllib.request.Request(UPSTREAM + "/chat/completions", data=json.dumps(data).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
            return self._relay(req, data)

        def _relay(self, req, chat):
            t = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    status, ctype, out = r.status, r.headers.get("Content-Type", ""), r.read()
            except urllib.error.HTTPError as e:
                status, ctype, out = e.code, e.headers.get("Content-Type", ""), e.read()
            except Exception as e:                                    # noqa: BLE001: reported, the SDK sees a 502
                status, ctype, out = 502, "text/plain", str(e).encode("utf-8")
            if chat is not None:
                tokens = {}
                for line in out.decode("utf-8", "replace").splitlines():
                    line = line[5:].strip() if line.startswith("data:") else line
                    try:
                        u = json.loads(line).get("usage") if line.startswith("{") else None
                    except ValueError:
                        u = None
                    if u:
                        tokens = {"in": u.get("prompt_tokens"), "out": u.get("completion_tokens")}
                first = next((m.get("content") for m in chat.get("messages", []) if m.get("role") == "system"), "")
                LOG.add(status=status, seconds=round(time.monotonic() - t, 2), stream=bool(chat.get("stream")),
                        task=" ".join(str(first).split())[:70],
                        answer=out.decode("utf-8", "replace")[-1500:] if os.environ.get("LIVE_ANSWERS") else None,
                        request=chat.get("messages") if os.environ.get("LIVE_ANSWERS") else None,
                        json_mode="response_format" in chat, **tokens)
            self.send_response(status)
            self.send_header("Content-Type", ctype or "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", relay.free_port()), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d/v1" % server.server_address[1]


def main(argv):
    if not KEY:
        print("set OPENROUTER_API_KEY")
        return 2
    only = [a for a in argv if not a.startswith("--")]
    fake = fakemodel.serve(relay.free_port(), os.path.join(CONF, "script.json"))
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    _, base = proxy("http://127.0.0.1:%d" % fake.server_address[1])
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.endswith("_BASE_URL")
           and not k.startswith("KINLOOM_")}
    env["PYTHONPATH"] = os.path.join(relay.ROOT, "src")
    env["PYTHONIOENCODING"] = "utf-8"
    env["KINLOOM_VECTORS"] = os.path.join(CONF, "vectors.json")     # the scenarios end with the shared vectors
    env["KINLOOM_SCENARIO_TIMEOUT"] = "30"        # the Python scenario's own client waits 5 s (made for the fake)
    expected = open(os.path.join(CONF, "expected.txt"), encoding="utf-8").read().strip().splitlines()
    before = usage()
    results = []

    def record(name, code, out, err, seconds):
        mine = [e for e in LOG.entries if e["sdk"] == name]
        res = {"sdk": name, "exit": code, "seconds": round(seconds, 1), "requests": len(mine),
               "answered": sum(1 for e in mine if e["status"] == 200),
               "tasks": [e.get("task") for e in mine],
               "errors": sorted({e["status"] for e in mine if e["status"] != 200}),
               "latency_median": sorted(e["seconds"] for e in mine)[len(mine) // 2] if mine else None,
               "tokens_in": sum(e.get("in") or 0 for e in mine), "tokens_out": sum(e.get("out") or 0 for e in mine),
               "transcript_lines": len(out), "expected_lines": len(expected), "transcript": out,
               "stderr_tail": err[-1500:] if code else ""}
        results.append(res)
        print("%-14s exit %s, %d/%d requests answered, %d transcript lines (scripted run: %d), %.0f s" % (
            name, code, res["answered"], res["requests"], len(out), len(expected), seconds))

    if not only or "python" in only:                     # the reference: Python's brain in kinloom serve
        LOG.sdk = "python"
        port = relay.free_port()
        server = relay.start_server(dict(env, KINLOOM_BASE_URL=base, KINLOOM_MODEL="fake-model", KINLOOM_API_KEY="proxy",
                                         KINLOOM_VOICE_BASE_URL=base, KINLOOM_SPEAK_MODEL="fake-tts",
                                         KINLOOM_LISTEN_MODEL="fake-stt", KINLOOM_VOICE_API_KEY="proxy"), port)
        t = time.monotonic()
        try:
            r = subprocess.run([sys.executable, os.path.join(CONF, "scenario.py"), str(port)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600, env=dict(env, KINLOOM_VOICE="off"))
        finally:
            server.kill()
        record("python", r.returncode, r.stdout.replace("\r\n", "\n").splitlines(), r.stderr, time.monotonic() - t)
    for name, make, parse in native.native_runs():
        if only and name not in only:
            continue
        LOG.sdk = name
        t = time.monotonic()
        r = subprocess.run(make(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           env=dict(env, KINLOOM_NATIVE=base, KINLOOM_VOICE="off"))
        record(name, r.returncode, parse(r.stdout.replace("\r\n", "\n")), r.stderr + r.stdout[-1500:], time.monotonic() - t)
    time.sleep(5)                                         # OpenRouter's usage count lags a little
    after = usage()
    total = {"model": MODEL, "date": datetime.date.today().isoformat(), "requests": len(LOG.entries),
             "answered": sum(1 for e in LOG.entries if e["status"] == 200),
             "billed_usd": round(after - before, 6), "results": results}
    path = os.path.join(HERE, "results-%s.json" % total["date"])
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(total, f, indent=1, ensure_ascii=False)
    print("\n%d requests, %d answered, billed $%.4f (key usage before/after) -> %s" % (
        total["requests"], total["answered"], total["billed_usd"], path))
    return 0 if all(r["exit"] == 0 for r in results) and total["answered"] == total["requests"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
