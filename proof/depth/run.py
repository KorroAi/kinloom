"""Measures the depth layer (minds that learn, the world), offline and free: no key, no model, no network.

    python proof/depth/run.py            # everything (about 1 minute)
    python proof/depth/run.py learning   # the learning curves only

Prints a markdown report; the numbers in proof/depth/README.md come from this script."""
import json
import os
import random
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "python", "src"))
from kinloom import Kinloom, demo  # noqa: E402

HAND = {"advance": {"score": 2, "when": ["dist above 8"]}, "take_cover": {"score": 1.8, "when": ["not in_cover", "dist below 9"]},
        "shoot": {"score": 1.5, "when": ["ammo above 0"]}, "reload": {"score": 1.6, "when": ["ammo below 1"]}}


def learning(seeds=8, minutes=30):
    print("## Learning without a key (`kinloom demo`, %d seeds, %d simulated minutes, 40 units)\n" % (seeds, minutes))
    print("| seed | won, minute 1 | won, minute 10 | won, minute 20 | won, last 5 minutes | generations | model calls |")
    print("|---|---|---|---|---|---|---|")
    finals, firsts = [], []
    started = time.perf_counter()
    for seed in range(seeds):
        r = demo.run(minutes=minutes, seed=seed, report=lambda s: None)
        w = [x["win"] for x in r["rows"]]
        last5 = sum(w[-5:]) / 5
        finals.append(last5)
        firsts.append(w[0])
        print("| %d | %.0f%% | %.0f%% | %.0f%% | %.0f%% | %d | %d |" % (seed, 100 * w[0], 100 * w[9], 100 * w[19], 100 * last5,
                                                             r["rows"][-1]["generation"], r["model_calls"]))
    print("\nMean: %.0f%% in the first minute, %.0f%% in the last five (min %.0f%%, max %.0f%%); %.0f s of computing for all runs.\n"
          % (100 * statistics.mean(firsts), 100 * statistics.mean(finals), 100 * min(finals), 100 * max(finals),
             time.perf_counter() - started))
    for name, rules in (("the naive rules, no learning", demo.NAIVE), ("hand-written good rules, no learning", HAND)):
        saved = demo.NAIVE
        demo.NAIVE = rules
        wins = [x["win"] for seed in range(3) for x in demo.run(minutes=3, seed=seed, learn=0, report=lambda s: None)["rows"]]
        demo.NAIVE = saved
        print("- %s: %.0f%% won (3 seeds x 3 minutes)" % (name, 100 * statistics.mean(wins)))
    print()


def speed():
    print("## Speed of `think` (1,000 units, 5 senses, 4 actions, 3 variants)\n")
    kl = Kinloom(provider=None, memory_path=None)
    senses = {"hp": (0.0, 1.0), "dist": (0.0, 40.0), "allies": (0, 10), "armed": True, "target": ["idle", "alert", "fleeing"]}
    actions = {"charge": {"speed": (1.0, 3.0)}, "shoot": {"burst": (1, 5)}, "flank": {}, "retreat": {}}
    rules = {"retreat": ["hp low"], "shoot": ["armed", "dist below 20"], "flank": {"score": 0.8, "when": ["allies above 2", "target is alert"]},
             "charge": {"score": 0.5, "args": {"speed": "dist high"}}}
    kl.mind("raider", "", senses, actions, rules, variants=3)
    rnd = random.Random(1)
    units = [{"hp": rnd.random(), "dist": rnd.uniform(0, 40), "allies": rnd.randint(0, 10), "armed": rnd.random() < .8,
              "target": rnd.choice(["idle", "alert", "fleeing"])} for _ in range(1000)]
    best = 1e9
    for _ in range(5):
        t = time.perf_counter()
        for i, u in enumerate(units):
            kl.think("raider", u, who=i)
        best = min(best, time.perf_counter() - t)
    print("- Python %s: %.2f ms per 1,000 thinks" % (sys.version.split()[0], best * 1e3))
    js = os.path.join(ROOT, "python", "src", "kinloom", "clients", "web", "kinloom.js").replace("\\", "/")
    code = ("import('file:///%s').then(({compileMind, runMind}) => {const c = compileMind({name: 'r', senses: %s, actions: %s, rules: %s,"
            " variants: 3}); const rnd = () => Math.random(); const units = Array.from({length: 1000}, (_, i) => ({hp: rnd(), dist: rnd() * 40,"
            " allies: Math.floor(rnd() * 10), armed: rnd() < .8, target: ['idle', 'alert', 'fleeing'][i %% 3]})); const m = new Map();"
            " let best = 1e9; for (let k = 0; k < 50; k++) { const t = performance.now(); units.forEach((u, i) => runMind(c, u, 'u' + i, m));"
            " best = Math.min(best, performance.now() - t); } console.log(best.toFixed(2)); });"
            % (js, json.dumps({k: list(v) if isinstance(v, tuple) else v for k, v in senses.items()}),
               json.dumps({"charge": {"speed": [1.0, 3.5]}, "shoot": {"burst": [1, 5]}, "flank": {}, "retreat": {}}), json.dumps(rules)))
    try:
        out = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60).stdout.strip()
        version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
        print("- JavaScript (Node %s): %s ms per 1,000 thinks" % (version, out))
    except (OSError, subprocess.SubprocessError):
        print("- JavaScript: node not found")
    print("\nThe mind runs in the game process: no model call, no network, whatever the number of units.\n")


def world():
    print("## Rumors (a village of 40, one witness, `spread` rounds)\n")
    kl = Kinloom(provider=None, memory_path=None)
    for i in range(40):
        kl.character("V%02d" % i, "a villager", group="village")
    kl.event("the player stole from the temple", by="PLAYER", seen_by=["V00"], tag="theft", impact=-0.8)
    print("| rounds of talk | villagers who know | village's opinion of the player |")
    print("|---|---|---|")
    for rounds in range(1, 7):
        kl.spread("village", 1)
        knowing = sum(kl.knows("V%02d" % i, "theft") for i in range(40))
        print("| %d | %d / 40 | %+.2f |" % (rounds, knowing, kl.reputation("PLAYER", "village")))
    print("\nNo model call: knowledge travels only through characters who meet, fainter with each hop and weighted by trust.\n")


if __name__ == "__main__":
    what = sys.argv[1:] or ["learning", "speed", "world"]
    if "learning" in what:
        learning()
    if "speed" in what:
        speed()
    if "world" in what:
        world()
