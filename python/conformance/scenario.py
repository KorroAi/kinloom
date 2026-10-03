"""Conformance from Python: the HTTP contract with a minimal urllib client (like any engine), then the Python library
offline. Usage: python scenario.py <port>"""
import json
import os
import sys
import time
import urllib.request


def post(base, verb, body):
    req = urllib.request.Request(base + "/v1/" + verb, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("KINLOOM_SCENARIO_TIMEOUT", 5))) as r:
            return json.loads(r.read().decode())
    except OSError:
        return None


def j(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


base = "http://127.0.0.1:%s" % sys.argv[1]
post(base, "character", {"name": "VEGA", "personality": "commentator", "lines": {"*": ["What a race, {who}!"]},
                         "events": {"overtake": ["who", "whom"]}})
post(base, "character", {"name": "THEO", "personality": "engineer", "offline": "Copy."})
post(base, "character", {"name": "BLAZE", "personality": "rival", "tools": {"boost": {"seconds": [0.5, 2.5]}}})
facts = {"who": "BLAZE", "whom": "NOVA"}
line = ""
for _ in range(100):
    line = post(base, "say", {"name": "VEGA", "event": "overtake", "facts": facts})["text"]
    if "passes" in line:
        break
    time.sleep(0.05)
print("say: " + line)
print("chat: " + post(base, "chat", {"name": "THEO", "message": "gap?", "facts": {"position": 3}})["text"])
choices = {"strategy": ["attack", "block"], "aggression": [0.0, 1.0]}
first = post(base, "decide", {"name": "BLAZE", "situation": {"lap": 1}, "choices": choices})["decision"]
print("decide first: " + j(first))
later = first
for _ in range(100):
    later = post(base, "decide", {"name": "BLAZE", "situation": {"lap": 1}, "choices": choices})["decision"]
    if later != first:
        break
    time.sleep(0.05)
print("decide later: " + j(later))
for _ in range(100):
    actions = post(base, "act", {"name": "BLAZE", "situation": {"lap": 1}})["actions"]
    if actions:
        for a in actions:
            print("act later: %s %s" % (a["tool"], j(a["args"])))
        break
    time.sleep(0.05)
print("create: " + j(post(base, "create", {"what": "race", "example": {"challenge": "Win clean", "sky": "#ff7a45"}})["value"]))
# Offline: the Python library itself, with no model.
sys.path.insert(0, __file__.rsplit("conformance", 1)[0] + "src")
from kinloom import Kinloom  # noqa: E402
kl = Kinloom(provider=None, memory_path=None)
kl.character("VEGA", "commentator", lines={"*": ["What a race, {who}!"]})
kl.character("THEO", "engineer", offline="Copy.")
print("offline say: " + kl.say("VEGA", "overtake", facts))
print("offline chat: " + kl.chat("THEO", "gap?", {"position": 3}))
print("offline decide: " + j(kl.decide("BLAZE", {"lap": 1}, choices)))
print("offline create: " + j(kl.create("race", {"challenge": "Win clean", "sky": "#ff7a45"})))

# ---------------- minds and the world (the depth layer), over raw HTTP ----------------
def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return json.loads(r.read().decode())
    except OSError:
        return None


RAIDER = {"senses": {"hp": [0, 1], "dist": [0, 40], "armed": True, "enemy": ["idle", "alert"]},
          "actions": {"charge": {"speed": [0.5, 3.0]}, "shoot": {"burst": [1, 5]}, "retreat": {}},
          "rules": {"retreat": ["hp low"], "shoot": ["armed", "dist below 20"], "charge": {"score": 0.5, "args": {"speed": "dist high"}}},
          "variants": 1}
mind = post(base, "mind", dict(RAIDER, name="raider", personality="a cunning raider"))["mind"]
post(base, "mind", {"name": "scout", "personality": "a timid scout", "senses": {"noise": [0, 1]}, "actions": {"run": {}, "hide": {}},
                    "variants": 2})
think = lambda senses, who, name="raider": post(base, "think", {"name": name, "senses": senses, "who": who})
print("think retreat: " + j(think({"hp": 0.1, "dist": 30, "armed": True}, "u1")))
print("think shoot: " + j(think({"hp": 0.9, "dist": 8, "armed": True, "enemy": "alert"}, "u2")))
print("think charge: " + j(think({"hp": 0.9, "dist": 10, "armed": False}, "u3")))
print("think sticky: " + think({"hp": 0.52, "dist": 30, "armed": True}, "u1")["action"])
print("think fresh: " + j(think({"hp": 0.52, "dist": 30, "armed": True}, "u4")))
learned = ""
for _ in range(100):
    learned = think({"noise": 0.5}, "s1", "scout")["action"]
    if learned == "hide":
        break
    time.sleep(0.1)
print("think learned: " + learned)
post(base, "reward", {"rewards": [{"who": w, "mind": "raider", "variant": 0, "id": mind["ids"][0], "reward": r}
                                  for w, r in (("u1", 1), ("u2", 0.5), ("u3", 0))]})
print("rewards: %d" % sum(v["rewards"] for v in get(base, "/v1/mind?name=raider")["report"]["variants"]))
post(base, "character", {"name": "BAKER", "personality": "a warm baker", "group": "village"})
post(base, "character", {"name": "GUARD", "personality": "a strict guard", "group": "guards"})
print("knows before: " + j(post(base, "knows", {"name": "GUARD", "tag": "theft"})["knows"]))
post(base, "event", {"text": "the player stole bread", "by": "PLAYER", "seen_by": ["BAKER"], "tag": "theft", "impact": -0.8})
shared = post(base, "meet", {"a": "BAKER", "b": "GUARD"})["shared"]
print("meet: " + ", ".join("%s -> %s" % (s["from"], s["to"]) for s in shared))
print("knows after: " + j(post(base, "knows", {"name": "GUARD", "tag": "theft"})["knows"]))
print("opinion: %s" % post(base, "opinion", {"a": "GUARD", "b": "PLAYER"})["opinion"])
print("reputation: %s" % post(base, "reputation", {"target": "PLAYER", "group": "village"})["reputation"])
post(base, "character", {"name": "MIRA", "soul": {"summary": "a gruff smith", "mood": "wary"}, "offline": "Hm.",
                         "tools": {"give": {"item": "wood"}}})
mira = post(base, "chat", {"name": "MIRA", "message": "Nice toy hammer.", "speaker": "Ana", "do": True})
print("soul chat: " + mira["text"])
soul = post(base, "soul", {"name": "MIRA", "speaker": "Ana"})
print("lore: %d" % post(base, "lore", {"lines": ["The village is Brookmere.", "The king died last winter."]})["lines"])
print("soul: %s %s %s" % (soul["mood"]["word"], "dislikes" if soul["bonds"]["Ana"]["feeling"] < 0 else "likes", soul["card"]["summary"]))
import base64  # noqa: E402
spoken = post(base, "speak", {"name": "GUARD", "text": "Halt."})
print("speak: " + ("wav" if base64.b64decode(spoken["audio"])[:4] == b"RIFF" else "?"))
print("listen: " + post(base, "listen", {"audio": spoken["audio"]})["text"])
kl.mind("raider", "a cunning raider", RAIDER["senses"], RAIDER["actions"], RAIDER["rules"], 1)
print("offline think: " + j(kl.think("raider", {"hp": 0.1, "dist": 30, "armed": True}, "u1")))
print("offline think charge: " + j(kl.think("raider", {"hp": 0.9, "dist": 10, "armed": False}, "u3")))
print("offline knows: " + j(kl.knows("GUARD", "theft")))
kl.character("MIRA", soul={"summary": "a gruff smith"}, offline="Hm.")
print("offline soul chat: " + kl.chat("MIRA", "Nice toy hammer.", speaker="Ana"))
print("offline speak: " + ("none" if kl.speak("GUARD", "Halt.") is None else "audio"))
print("offline listen: " + (kl.listen(base64.b64decode(spoken["audio"])) or "-"))

# ---------------- what came back: where it came from, actions with the reply, events described in words ----------------
post(base, "character", {"name": "ANA", "personality": "a trainer",
                         "lines": {"challenge": {"when": "challenging someone to a battle", "lines": ["{other}, fight!"]}}})
print("when say: " + post(base, "say", {"name": "ANA", "event": "challenge", "facts": {"other": "BEN"}})["text"])
print("say source: " + post(base, "say", {"name": "VEGA", "event": "overtake", "facts": facts})["source"])
print("chat source: " + mira["source"])
for a in mira["do"]:
    print("chat do: %s %s" % (a["tool"], j(a["args"])))
kl.character("ANA", "a trainer", lines={"challenge": {"when": "challenging someone to a battle", "lines": ["{other}, fight!"]}})
line = kl.say("ANA", "challenge", {"other": "BEN"})
print("offline when say: " + line)
print("offline source: " + line.source)

# ---------------- the game's tools, pictures, ready before play ----------------
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP4z8AARAwQCgAf7gP9i18U1AAAAABJRU5ErkJggg=="
print("tools: " + ", ".join(post(base, "tools", {"tools": {"open_door": {"door": "north"}}})["tools"]))
post(base, "character", {"name": "KEEPER", "personality": "a gatekeeper", "tools": ["open_door"]})
for _ in range(100):
    acts = post(base, "act", {"name": "KEEPER", "situation": {}})["actions"]
    if acts:
        for a in acts:
            print("tools act: %s %s" % (a["tool"], j(a["args"])))
        break
    time.sleep(0.05)
post(base, "character", {"name": "LOOK", "personality": "a painter", "offline": "Blind."})
print("chat image: " + post(base, "chat", {"name": "LOOK", "message": "What is this?", "image": PNG})["text"])
created = post(base, "create", {"what": "race", "example": {"challenge": "Win clean", "sky": "#ff7a45"}, "image": PNG})
print("create image: " + j(created["value"]))
ready = post(base, "prepare", {"timeout": 10})
print("prepare: %s %s" % ("ready" if ready["ready"] else "waiting", "online" if ready["online"] else "offline"))
print("offline tools: " + ", ".join(kl.tools({"open_door": {"door": "north"}})))
kl.character("LOOK", "a painter", offline="Blind.")
print("offline chat image: " + kl.chat("LOOK", "What is this?", image=PNG))
print("offline create image: " + j(kl.create("race", {"challenge": "Win clean", "sky": "#ff7a45"}, image=PNG)))
ready = kl.prepare(1)
print("offline prepare: %s %s" % ("ready" if ready["ready"] else "waiting", "online" if ready["online"] else "offline"))
t0 = time.monotonic()
gone = Kinloom(url="http://127.0.0.1:9")
gone.character("THEO", "engineer", offline="Copy.")
fast = gone.chat("THEO", "gap?") == "Copy." and gone.chat("THEO", "gap?") == "Copy." and gone.say("THEO", "x") == ""
print("offline fast: " + ("yes" if fast and time.monotonic() - t0 < 1.5 else "no (%.1f s)" % (time.monotonic() - t0)))
gone.close()

# ---------------- v1: the player's choices, characters talking together, a snapshot, saves ----------------
CHOICES = ["Ask about the sword", "Buy something", "Leave"]
print("suggest: " + " | ".join(post(base, "suggest", {"name": "MIRA", "examples": CHOICES, "speaker": "Ana"})["replies"]))
print("offline suggest: " + " | ".join(kl.suggest("MIRA", CHOICES, speaker="Ana")))
talk = post(base, "converse", {"a": "MIRA", "b": "BAKER", "about": "the smoke"})["lines"]
print("converse: " + " | ".join("%s: %s" % (x["who"], x["text"]) for x in talk))
print("offline converse: %d" % len(kl.converse("MIRA", "BAKER")))
snap = post(base, "inspect", {})["characters"]["MIRA"]
print("inspect: MIRA %s %s" % (snap["mood"]["word"], snap["last_words"]))
saved = post(base, "save", {})["data"]
post(base, "load", {"data": saved, "session": "slot2"})
print("load: MIRA %s Ana" % ("dislikes" if post(base, "opinion", {"a": "MIRA", "b": "Ana", "session": "slot2"})["opinion"] < 0 else "likes"))
