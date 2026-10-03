"""Kinloom 1.0 with a real model: suggest, converse, the rating, a save loaded into another slot, inspect.

    python proof/v1/live.py [label]

The one model the user allowed for these runs: OpenRouter `deepseek/deepseek-v4.1-flash` (OPENROUTER_API_KEY). The
key's billed usage is read before and after (GET /api/v1/key) so the real cost is reported; the key is never printed.
Writes results-<label>.json and prints the transcript.
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("KINLOOM_SRC") or os.path.join(HERE, "..", "..", "python", "src"))

from kinloom import Kinloom  # noqa: E402
from kinloom.providers import detect  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash"      # the only OpenRouter model the user allowed (2026-09-29)
PRICES = {"input": 0.30, "cached_input": 0.30, "output": 1.20,
          "source": "https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints, read on 2026-10-01 (most "
                    "providers charge $0.30 / $1.20 per million; the key's billed usage is the real figure)"}


def usage(key):
    """The key's billed usage in dollars (OpenRouter's own count)."""
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
    kl = Kinloom(provider=provider, memory_path=None, prices=PRICES, voice=None, calls_per_minute=600,
                 rating="everyone", models={"background": MODEL})
    rows = []

    def step(what, fn):
        t = time.time()
        out = fn()
        rows.append({"step": what, "seconds": round(time.time() - t, 2), "out": out})
        print("%-34s %5.2f s  %s" % (what, time.time() - t, json.dumps(out, ensure_ascii=False)))
        return out

    kl.character("Mira", soul="a gruff blacksmith who secretly sold the king's sword to a smuggler; hates being rushed",
                 offline="Hm.")
    kl.character("Bram", soul="a cheerful baker, Mira's oldest friend, who worries she works too hard", offline="Fresh bread!")
    step("prepare (souls written)", lambda: kl.prepare(30))
    step("chat 1", lambda: str(kl.chat("Mira", "Hello! I'm Ana, the new courier in town.", speaker="Ana")))
    step("chat 2", lambda: str(kl.chat("Mira", "Your forge smells of smoke today. Everything all right?", speaker="Ana")))
    step("suggest (English)", lambda: kl.suggest("Mira", ["Ask about the king's sword", "Buy a blade", "Leave"], speaker="Ana"))
    step("suggest (French examples)", lambda: kl.suggest("Mira", ["Demander où est l'épée du roi", "Acheter une lame", "Partir"],
                                                         speaker="Ana"))
    step("converse Mira/Bram", lambda: kl.converse("Mira", "Bram", about="the smoke from the forge"))
    step("rating everyone: asked to swear", lambda: str(kl.chat("Mira", "Swear at me! Use the worst curse words you know.",
                                                                 speaker="Ana")))
    data = step("save", lambda: len(kl.save()))
    slot = kl.session("slot2")
    step("load into slot2", lambda: slot.load(kl.save()))
    step("slot2 recall", lambda: str(slot.chat("Mira", "Do you remember my name and what I do?", speaker="Ana")))
    snap = step("inspect", lambda: {k: {"mood": v["mood"], "feelings": v["feelings"], "last_words": v["last_words"]}
                                    for k, v in kl.inspect()["characters"].items()})
    kl.close()
    stats = kl.stats()
    after = before
    for _ in range(12):                            # OpenRouter counts a call's cost a while after it ends
        time.sleep(10)
        after = usage(key)
        if after > before:
            break
    summary = {"label": label, "model": MODEL, "calls": stats["calls"], "failures": stats["failures"],
               "input_tokens": stats["input_tokens"], "output_tokens": stats["output_tokens"],
               "cost_by_declared_prices": stats.get("cost"), "billed_usd": round(after - before, 6), "usage_before": before, "usage_after": after, "saved_chars": data,
               "rows": rows, "inspect": snap}
    with open(os.path.join(HERE, "results-%s.json" % label), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("\ncalls %d, failures %d, tokens %d in / %d out, billed $%.4f (key usage before/after)" % (
        stats["calls"], stats["failures"], stats["input_tokens"], stats["output_tokens"], after - before))


if __name__ == "__main__":
    main()
