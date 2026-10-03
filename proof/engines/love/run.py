"""Kinloom's Lua client in a real LÖVE game (11.5): offline, relay and native, through love.thread.

    python proof/engines/love/run.py <path to lovec.exe or love>

The model is the conformance fake (python/conformance/fakemodel.py): no key, nothing spent. Prints the game's results.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "..", "..", "..", "python", "conformance")
sys.path.insert(0, CONF)
import fakemodel  # noqa: E402
import run as relay  # noqa: E402


def main(love):
    fake = fakemodel.serve(relay.free_port(), os.path.join(CONF, "script.json"))
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    model = "http://127.0.0.1:%d/v1" % fake.server_address[1]
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.endswith("_BASE_URL")
           and not k.startswith("KINLOOM_")}
    env["PYTHONPATH"] = os.path.join(relay.ROOT, "src")
    port = relay.free_port()
    server = relay.start_server(dict(env, KINLOOM_BASE_URL=model, KINLOOM_MODEL="fake-model", KINLOOM_API_KEY="fake-key"), port)
    game = tempfile.mkdtemp()
    shutil.copy(os.path.join(HERE, "main.lua"), game)
    shutil.copy(os.path.join(relay.CLIENTS, "lua", "kinloom.lua"), game)
    out = os.path.join(game, "results.txt")
    try:
        r = subprocess.run([love, game, str(port), model, out], capture_output=True, text=True, timeout=90)
    finally:
        server.kill()
    if not os.path.exists(out):
        print("no results; LÖVE said:\n" + (r.stdout + r.stderr)[-3000:])
        return 1
    text = open(out, encoding="utf-8").read()
    print(text, end="")
    lines = text.splitlines()
    ok = ("pending at the end: 0" in text and "relay transport: love.thread" in lines and "native transport: love.thread" in lines
          and any(l.startswith("relay chat: ") and l.endswith("(model)") for l in lines)
          and any(l.startswith("native chat: ") and l.endswith("(model)") for l in lines)
          and "offline chat: Busy. (offline)" in lines)
    print("LÖVE: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
