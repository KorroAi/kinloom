"""Live check against the real model found in the environment (spends a few tenths of a cent with DeepSeek).
    uv run python examples/live_smoke.py
"""
import json
import time

from kinloom import Kinloom

PRICES = json.load(open(__file__.replace("python\\examples\\live_smoke.py", "proof\\impact\\prices.json").replace(
    "python/examples/live_smoke.py", "proof/impact/prices.json"), encoding="utf-8"))
p = PRICES["usd_per_million_tokens"]
kl = Kinloom(memory_path=None, prices={"input": p["input"], "cached_input": p["cached_input"], "output": p["output"],
                                       "source": PRICES["source"] + " read " + PRICES["read_on"]})
print("status:", kl.status())
t0 = time.monotonic()
kl.character("VEGA", "an over-excited race commentator", events={"overtake": ["who", "whom", "gap"], "crash": ["who"]})
kl.character("THEO", "a calm race engineer who only states facts", offline="Copy.")
kl.character("BLAZE", "a hot-headed rival driver who holds grudges")
kl.event("the player rammed BLAZE twice last race", about=["BLAZE"])
kl.wait_idle(30)
print("banks warmed in %.1f s" % (time.monotonic() - t0))
for i in range(5):
    s = time.monotonic()
    line = kl.say("VEGA", "overtake", {"who": "BLAZE", "whom": "NOVA", "gap": 0.37 + i / 10})
    print("say (%.1f ms): %s" % ((time.monotonic() - s) * 1000, line))
print("crash:", kl.say("VEGA", "crash", {"who": "MINT"}))
s = time.monotonic()
print("chat (%.2f s): %s" % (time.monotonic() - s, kl.chat("THEO", "how far is the leader?", {"position": 3, "gap_to_leader": 1.24, "laps_left": 2})))
choices = {"strategy": ["attack", "block", "save_boost"], "aggression": (0.0, 1.0), "target": ["player", "NOVA", "MINT"]}
print("decide now:", kl.decide("BLAZE", {"lap": 2, "gap_to_player": -0.6}, choices))
kl.wait_idle(20)
print("decide after:", kl.decide("BLAZE", {"lap": 2, "gap_to_player": -0.6}, choices))
s = time.monotonic()
race = kl.create("the next race of an arcade racer at sunset",
                 {"challenge": "Win without touching a wall", "sky": "#ff7a45", "rival_speed": (0.9, 1.1)})
print("create (%.2f s): %s" % (time.monotonic() - s, race))
print("stats:", json.dumps(kl.stats()))
