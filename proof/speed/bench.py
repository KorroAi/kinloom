"""Speed of a real conversation with a soul: time to the first word, whole reply, tokens sent and cached, per turn.

    python proof/speed/bench.py ollama qwen3:8b          # local model, free (Ollama running)
    python proof/speed/bench.py openrouter               # the one OpenRouter model the user allowed (spends cents)

Writes proof/speed/results-<provider>-<model>.json and prints a summary. The model answers for real: every number
is measured, nothing is estimated.
"""
import json
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("KINLOOM_SRC") or os.path.join(HERE, "..", "..", "python", "src"))

from kinloom import Kinloom  # noqa: E402
from kinloom.providers import detect  # noqa: E402

OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"      # the only OpenRouter model the user allowed (2026-09-29)
OPENROUTER_PRICES = {"input": 0.30, "cached_input": 0.006, "output": 1.20,
                     "source": "https://openrouter.ai/api/v1/models, deepseek/deepseek-v4.1-flash, read on 2026-09-29"}
TURNS = ["", "Nice toy hammer.", "Sorry, I was joking. Everyone says you're the best smith in town.",
         "What are you working on today?", "That sword on the wall... it looks like the king's. Is it?",
         "Do you have family here?", "What do you do when the forge is cold?", "Can you fix my shovel? It's bent.",
         "How much would a new blade cost?", "Who taught you the trade?", "Do you remember my name?",
         "Thanks. See you tomorrow."]


def provider_for(kind, model):
    if kind == "ollama":
        return detect({"KINLOOM_BASE_URL": "http://127.0.0.1:11434/v1", "KINLOOM_MODEL": model}, probe_ollama=False), {}
    if kind == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            sys.exit("OPENROUTER_API_KEY is not set")
        return detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": OPENROUTER_MODEL}, probe_ollama=False), OPENROUTER_PRICES
    sys.exit("provider: ollama or openrouter")


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def main(kind="ollama", model="qwen3:8b"):
    provider, prices = provider_for(kind, model)
    memory = os.path.join(tempfile.mkdtemp(), "memory.json")
    kl = Kinloom(provider=provider, memory_path=memory, prices=prices or None, call_timeout=60)
    start = time.monotonic()
    kl.character("Mira", soul="a widowed blacksmith, gruff and proud, who secretly sold the king's sword to pay her debts",
                 offline="Busy.", tools={"give": {"item": "sword"}}, trust={"give": 0.3})
    kl.wait_idle(120)
    ready = time.monotonic() - start
    rows = []
    for message in TURNS:
        t = time.monotonic()
        first = []
        before = kl.stats()
        reply = kl.chat("Mira", message, speaker="Ana", stream=lambda _: first or first.append(time.monotonic() - t))
        total = time.monotonic() - t
        after = kl.stats()
        rows.append({"message": message, "reply": reply, "first_word_s": round(first[0], 3) if first else None,
                     "total_s": round(total, 3), "input_tokens": after["input_tokens"] - before["input_tokens"],
                     "cached_tokens": after["cached_tokens"] - before["cached_tokens"],
                     "offline": after["offline_answers"] > before["offline_answers"]})
        r = rows[-1]
        print("Ana: %s\nMira: %s\n   [first word %ss, %.2fs, %d tokens in, %d cached%s]" % (
            message or "(walks up)", reply, r["first_word_s"], total, r["input_tokens"], r["cached_tokens"],
            ", OFFLINE" if r["offline"] else ""))
        sys.stdout.flush()
    kl.wait_idle(120)
    s = kl.stats()
    summary = {"provider": provider.describe(), "card_and_greeting_ready_s": round(ready, 2), "turns": len(rows),
               "offline_answers": sum(r["offline"] for r in rows),
               "first_word_p50_s": pct([r["first_word_s"] for r in rows], 0.5),
               "first_word_p95_s": pct([r["first_word_s"] for r in rows], 0.95),
               "total_p50_s": pct([r["total_s"] for r in rows], 0.5), "total_p95_s": pct([r["total_s"] for r in rows], 0.95),
               "input_tokens": s["input_tokens"], "cached_tokens": s["cached_tokens"], "output_tokens": s["output_tokens"],
               "calls": s["calls"], "failures": s["failures"], "hedged": s["hedged"], "cost_usd": s.get("cost")}
    print(json.dumps(summary, indent=1))
    name = "results-%s-%s%s.json" % (kind, re.sub(r"[^\w.-]+", "_", provider.model),
                                     "-before" if os.environ.get("KINLOOM_SRC") else "")
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(*sys.argv[1:])
