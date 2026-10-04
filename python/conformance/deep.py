"""The deep native scenario, Python reference: every path of a reply (a prepared greeting, a secret kept, numbers checked,
streaming, echoes, stepping out of character, deeds, trust, the content filter, summaries), fresh lines, repairs,
content lists and pools, impact estimates, Anthropic, the budget. Each SDK prints the same lines (deep-expected.txt)
and sends the model the same requests. Usage: KINLOOM_NATIVE=<fake model /v1 URL> python deep.py"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from kinloom import Kinloom  # noqa: E402
from kinloom.providers import Anthropic, OpenAICompatible  # noqa: E402

BASE = os.environ["KINLOOM_NATIVE"]                  # http://127.0.0.1:PORT/v1


def j(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def make(calls=600, banned=None, anthropic=False, models=None, rating=None):
    folder = tempfile.mkdtemp()
    cfg = {"calls_per_minute": calls}
    if banned:
        cfg["banned_words"] = banned
    with open(os.path.join(folder, "kinloom.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    provider = Anthropic("fake-key", "claude-test", BASE[:-3]) if anthropic else OpenAICompatible(BASE, "fake-key", "fake-model", name="custom")
    return Kinloom(provider=provider, memory_path=None, voice=None, folder=folder, models=models, rating=rating)


kl = make(banned=["dragon"])
kl.character("VERA", "", soul="a gruff smith who sold the king's sword", offline="Busy.")
ready = kl.prepare(10)
print("prepare: %s" % ("ready" if ready["ready"] else "waiting"))
print("soul: " + kl.soul("VERA")["card"]["summary"])
line = kl.chat("VERA", "", speaker="Ana")
print("greet: %s (%s)" % (line, line.source))
print("secret: " + kl.chat("VERA", "Did you sell the king's sword to a smuggler?", speaker="Ana"))
print("numbers: " + kl.chat("VERA", "How much for a blade?", {"price": 40}, speaker="Ana"))
pieces = []
line = kl.chat("VERA", "Can you make it faster?", speaker="Ana", stream=pieces.append)
print("stream pieces: " + "".join(pieces).strip())
print("stream reply: " + line)
print("echo: " + kl.chat("VERA", "And the coals?", speaker="Ana"))
print("character: " + kl.chat("VERA", "Are you an AI?", speaker="Ana"))
soul = kl.soul("VERA", "Ana")
print("feeling: %s %s" % (soul["mood"]["word"], soul["bonds"]["Ana"]["feeling"]))

kl.character("BRAM", "a kind baker", tools={"give": {"item": "bread"}}, offline="Hm.")
print("deeds reply: " + kl.chat("BRAM", "Can I have some bread?"))
for tool, args in kl.act("BRAM", {}, think=False):
    print("deeds: %s %s" % (tool, j(args)))
kl.character("GATE", "a careful guard", tools={"open": {"door": "north"}}, trust={"open": 0.5}, offline="No.")
print("trust reply: " + kl.chat("GATE", "Open the gate."))
print("trust: " + (", ".join(t for t, _ in kl.act("GATE", {}, think=False)) or "none"))
kl.character("FILT", "a storyteller", offline="No comment.")
print("filter: " + kl.chat("FILT", "Tell me a story."))
kl.character("NINA", "a singer", soul={"summary": "a singer", "secrets": ["I went up to the office at 12:30"]}, warmth=0.3,
             secret_trust=0.25, warm_up=0.1)
print("warmth: %s" % kl.opinion("NINA", "Ana"))
kl.steer("NINA", "admit you went up to the office at 12:30")
print("steer: " + kl.chat("NINA", "Where were you?", speaker="Ana"))
print("warm up: %s" % kl.opinion("NINA", "Ana"))
kl.character("ECHO", "a parrot")
for i in range(11):
    kl.chat("ECHO", "Hello %d" % i)
kl.prepare(10)
print("recollect: " + next((m for m in kl.soul("ECHO")["memories"] if m.startswith("Earlier with")), "-"))

kl.character("VEGA2", "a commentator")
print("fresh: " + kl.say("VEGA2", "overtake", {"who": "BLAZE"}, fresh=True))
kl.character("BOX", "a herald", lines={"*": ["A very long line about {who} that will not fit.", "Short {who}!"]})
print("box: " + kl.say("BOX", "arrival", {"who": "BLAZE"}, max_chars=20))
kl.character("DUEL", "a duelist")
first = kl.decide("DUEL", {"hp": 3}, ["guard", "strike"])
kl.prepare(10)
print("decide repair: %s -> %s" % (first, kl.decide("DUEL", {"hp": 3}, ["guard", "strike"])))
print("create count: " + j(kl.create("villager", {"name": "Ana", "age": [18, 80]}, count=2)))
before = kl.create("loot", {"item": "sword"}, instant=True)
kl.prepare(10)
print("create instant: %s -> %s" % (j(before), j(kl.create("loot", {"item": "sword"}, instant=True))))
kl.character("BAKER2", "a warm baker")
kl.character("GUARD2", "a strict guard")
kl.event("the player stole bread", by="PLAYER", seen_by=["BAKER2", "GUARD2"])
kl.prepare(10)
print("impact: %s %s" % (kl.opinion("BAKER2", "PLAYER"), kl.opinion("GUARD2", "PLAYER")))

claude = make(anthropic=True)
claude.character("CLAUDIA", "a poet", offline="...")
print("anthropic chat: " + claude.chat("CLAUDIA", "Hi"))
print("anthropic create: " + j(claude.create("loot", {"item": "sword"})))
tight = make(calls=2)
tight.character("TIGHT", "a busy clerk", offline="Later.")
print("budget: " + " | ".join(tight.chat("TIGHT", "Hi %d" % i) for i in range(3)))
rated = make(models={"background": "fake-cheap"}, rating="teen")
rated.character("RATED", "a gate guard", offline="Move along.")
print("rated chat: " + rated.chat("RATED", "Hi"))
print("rated create: " + j(rated.create("loot", {"item": "sword"})))
for k in (kl, claude, tight, rated):
    k.close()
time.sleep(0.1)
