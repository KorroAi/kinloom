"""Does create's check= help with a real model? The same ten building requests on a crowded plot, without and with the
game's rules in the loop (the plan must fit the free tiles and stand next to something that exists).

    python proof/rules/run.py [label]

The one model used for every real-model run here: OpenRouter `deepseek/deepseek-v4.1-flash` (OPENROUTER_API_KEY). The
key's billed usage is read before and after (GET /api/v1/key) so the real cost is reported; the key is never printed.
Writes results-<label>.json and prints one line per request.
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("KINLOOM_SRC") or os.path.join(HERE, "..", "..", "python", "src"))

from kinloom import Kinloom  # noqa: E402
from kinloom.providers import detect  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash"      # the one model used for every real-model run here (comparable, cheap)
FREE_TILES = 16                             # one 4 x 4 hole left on the plot
TOWN = ["Old Well", "Oak", "Tavern"]
EXAMPLE = {"name": "Cottage", "width": [1, 12], "depth": [1, 12], "near": "Old Well", "say": "A cozy cottage."}
OFFLINE = {"name": "Hut", "width": 3, "depth": 3, "near": "Old Well", "say": "A small hut by the well."}
REQUESTS = ["a huge castle with four towers", "a grand cathedral next to the harbour", "a market square by the old mill",
            "a giant statue of the founder", "a cozy cottage near the well", "a lighthouse by the docks",
            "a big barn next to the farm", "a second tavern next to the tavern", "a palace for the queen",
            "a tiny shrine by the oak"]


def broken(plan):
    """The game's rules: "" when the plan fits, else why not."""
    if plan["width"] * plan["depth"] > FREE_TILES:
        return "it takes %d tiles and only %d are free: make it at most %d tiles" % (plan["width"] * plan["depth"], FREE_TILES, FREE_TILES)
    if plan["near"] not in TOWN:
        return '"%s" is not in town: near must be one of %s' % (plan["near"], ", ".join(TOWN))
    return ""


def usage(key):
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return float(json.loads(r.read().decode("utf-8"))["data"]["usage"])


def main():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set")
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    before = usage(key)
    provider = detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": MODEL}, probe_ollama=False)
    context = {"town": TOWN, "free tiles": FREE_TILES, "rule": "the building must fit in the free tiles and stand near "
               "something already in town"}
    rows = []
    for mode in ("plain", "check"):
        kl = Kinloom(provider=provider, memory_path=None, voice=None, calls_per_minute=600)
        for text in REQUESTS:
            calls0 = kl.stats()["calls"]
            what = 'the building the player asked for: "%s"' % text
            if mode == "plain":
                plan = kl.create(what, EXAMPLE, context)
            else:
                plan = kl.create(what, EXAMPLE, context, check=broken, offline=OFFLINE)
            calls = kl.stats()["calls"] - calls0
            why = broken(plan)
            source = "offline" if plan == OFFLINE else "model"
            rows.append({"mode": mode, "request": text, "plan": plan, "calls": calls, "fits": not why, "why": why, "source": source})
            print("%-5s %-40s %s calls  %s  %s" % (mode, text[:40], calls, "fits" if not why else "BREAKS: " + why[:60], source))
        kl.close()
    after = usage(key)
    summary = {}
    for mode in ("plain", "check"):
        mine = [r for r in rows if r["mode"] == mode]
        summary[mode] = {"requests": len(mine), "fit the rules": sum(r["fits"] for r in mine),
                         "model answers that fit": sum(r["fits"] and r["source"] == "model" for r in mine),
                         "offline (refused twice or no answer)": sum(r["source"] == "offline" for r in mine),
                         "calls": sum(r["calls"] for r in mine)}
    out = {"model": MODEL, "free_tiles": FREE_TILES, "town": TOWN, "rows": rows, "summary": summary,
           "billed_usd": round(after - before, 6)}
    with open(os.path.join(HERE, "results-%s.json" % label), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1))
    print("billed: $%.6f (the key's usage before and after)" % (after - before))


if __name__ == "__main__":
    main()
