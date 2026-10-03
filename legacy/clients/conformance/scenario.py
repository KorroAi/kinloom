"""Conformance scenario for the Python client: python scenario.py <port>. Prints the transcript compared with expected.txt."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
from kinloom_client import Kinloom, KinloomError  # noqa: E402

port = sys.argv[1]
log = []
kl = Kinloom.connect(f"ws://localhost:{port}/ws")
effects, said = [], []
kl.handle("set", effects.append)
kl.handle("say", said.append)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json"), encoding="utf-8") as f:
    manifest = json.load(f)
log.append("declare errors: %d" % len(kl.declare(manifest)))
log.append("bad declare errors: %s" % str(len(kl.declare({"things": [{"id": "x", "type": "Ghost"}]})) > 0).lower())
kl.update("player", {"idle_seconds": 2})
kl.event("overtake", {"who": "player"})
for _ in range(300):
    if effects:
        break
    kl.tick(1)
    time.sleep(0.01)
for e in effects:
    log.append("effect %s %s.%s %s from %s" % (e["kind"], e["thing"], e["member"], json.dumps(e["args"]["value"]), e["source"]))

pending = kl.ask_async("rex", "Nice truck.", "player")
while not pending.done():  # a game keeps playing while the role thinks
    kl.poll()
    time.sleep(0.01)
reply = pending.result()
for _ in range(100):
    if said:
        break
    kl.poll()
    time.sleep(0.01)
log.append("said by %s: %s" % (said[0]["thing"], said[0]["text"]) if said else "said by None: None")
log.append("reply: %s" % reply["reply"])

g = kl.generate("name", {"style": "loud"})
log.append("generated: %s %s" % (str(g["ok"]).lower(), (g.get("value") or {}).get("name")))
state = kl.save()
log.append("saved: %s" % str('"version":1' in state).lower())
kl.load(state)
log.append("loaded")
log.append("remove missing: %s" % str(kl.remove("nobody")).lower())
try:
    kl._request("fly", {})
    log.append("unknown method error: none")
except KinloomError as e:
    log.append("unknown method error: %s" % e.code)
kl.close()
print("\n".join(log))
