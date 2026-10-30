"""Minds that learn with a real model vs without one: the `kinloom demo` skirmish, same seeds, same simulated minutes.

    python proof/depth/llm.py openrouter 0 1 2        # seeds; the one OpenRouter model used for every real run (cents)
    python proof/depth/llm.py offline 0 1 2           # the same runs with no model

With a model, the model writes the first variants and rewrites the worst one at each learning step; when a call
fails or is over budget, the step falls back to the offline change (counted). Writes proof/depth/llm-<mode>.json.
"""
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python", "src"))

from kinloom import Kinloom, demo  # noqa: E402
from kinloom.providers import detect  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash"      # the one model used for every real-model run here (comparable, cheap)
PRICES = {"input": 0.30, "cached_input": 0.30, "output": 1.20,
          "source": "https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints, read on 2026-10-01: providers charge $0.0243-$0.60 in and $0.40-$2.40 out per million; most charge $0.30 / $1.20 (used here; the key's billed usage that day matched it, the /models price is the cheapest provider's)"}
MINUTES = 30


def one(seed, provider):
    clock = demo._Clock()
    kl = Kinloom(provider=provider, memory_path=None, clock=clock, prices=PRICES if provider else None,
                 calls_per_minute=600, voice=None)
    kl.mind("fighter", "a soldier who wants to win the fight and stay alive", demo.SENSES, demo.ACTIONS, rules=demo.NAIVE,
            variants=4, learn=5.0)
    kl.wait_idle(120)
    rnd = random.Random(seed)
    fights = [demo.Skirmish(rnd) for _ in range(40)]
    stretch, rows = [], []
    started = time.time()
    for step in range(int(MINUTES * 60 / 0.5)):
        for i, fight in enumerate(fights):
            who = "unit-%d" % i
            choice = kl.think("fighter", fight.senses(), who=who)
            reward, done, result = fight.step(choice["action"])
            kl.reward(who, reward, done=done)
            if done:
                stretch.append(result)
                fights[i] = demo.Skirmish(rnd)
        clock.t += 0.5
        kl.wait_idle(120)
        if (step + 1) % 120 == 0:
            rows.append({"minute": (step + 1) // 120, "fights": len(stretch), "win": stretch.count("win") / max(1, len(stretch)),
                         "generation": kl.mind_report("fighter")["generation"]})
            print("seed %d minute %2d won %3.0f%% generation %d (%.0f s)" % (seed, rows[-1]["minute"], 100 * rows[-1]["win"],
                                                                         rows[-1]["generation"], time.time() - started), flush=True)
            stretch = []
    learns = [e["text"] for e in kl.journal(500) if e["kind"] == "learn"]
    stats = kl.stats()
    best = max(kl.mind_report("fighter")["variants"], key=lambda v: v["mean"] if v["mean"] is not None else -9)
    kl.close()
    return {"seed": seed, "rows": rows, "last5": sum(r["win"] for r in rows[-5:]) / 5,
            "learning_steps": len(learns), "by_model": sum("the model's rewrite" in t for t in learns),
            "calls": stats["calls"], "failures": stats["failures"], "input_tokens": stats["input_tokens"],
            "output_tokens": stats["output_tokens"], "cost_usd": stats.get("cost"), "seconds": round(time.time() - started),
            "best_rules": best["rules"]}


def main():
    mode = sys.argv[1]
    seeds = [int(x) for x in sys.argv[2:]] or [0, 1, 2]
    provider = None
    if mode == "openrouter":
        provider = detect({"OPENROUTER_API_KEY": os.environ["OPENROUTER_API_KEY"], "KINLOOM_MODEL": MODEL}, probe_ollama=False)
    runs = [one(s, provider) for s in seeds]
    summary = {"mode": mode, "model": MODEL if provider else None, "minutes": MINUTES,
               "last5_per_seed": [round(r["last5"], 3) for r in runs],
               "last5_mean": round(sum(r["last5"] for r in runs) / len(runs), 3),
               "learning_steps": [r["learning_steps"] for r in runs], "by_model": [r["by_model"] for r in runs],
               "calls": sum(r["calls"] for r in runs), "failures": sum(r["failures"] for r in runs),
               "cost_usd": round(sum(r["cost_usd"] or 0 for r in runs), 6) if provider else 0,
               "price_source": PRICES["source"] if provider else None}
    print(json.dumps(summary, indent=2))
    with open(os.path.join(HERE, "llm-%s.json" % mode), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "runs": runs}, f, indent=2)


if __name__ == "__main__":
    main()
