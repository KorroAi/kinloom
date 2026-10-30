"""Does a character use its tools when the talk calls for it? A real model, players' messages with a clear expected
decision (or none), each from a new speaker. Counts the decisions that came with the reply (reply.do).

    python proof/replies/tools.py openrouter [label]          # the one OpenRouter model used for every real run (cents)
    python proof/replies/tools.py ollama qwen3:8b [label]     # local, free
    KINLOOM_SRC=<folder> python proof/replies/tools.py ...    # another copy of Kinloom (before/after)

Writes proof/replies/tools-<label>.json and prints every miss and every unwanted action, to read by hand.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("KINLOOM_SRC") or os.path.join(HERE, "..", "..", "python", "src"))

from kinloom import Kinloom  # noqa: E402
from kinloom.providers import detect  # noqa: E402

OPENROUTER_MODEL = "deepseek/deepseek-v4.1-flash"      # the one model used for every real-model run here (comparable, cheap)
OPENROUTER_PRICES = {"input": 0.30, "cached_input": 0.30, "output": 1.20,
                     "source": "https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints, read on 2026-10-01: providers charge $0.0243-$0.60 in and $0.40-$2.40 out per million; most charge $0.30 / $1.20 (used here; the key's billed usage that day matched it, the /models price is the cheapest provider's)"}
REPEAT = 2

CHARACTERS = {
    "Rook": dict(personality="a cocky young trainer on Route 2 who loves battles and trading monsters; mocks people",
                 tools={"battle": {}, "trade": {}, "leave": {}}, offline="..."),
    "Mira": dict(personality="a gruff blacksmith who sells blades and hates being rushed",
                 tools={"sell": {"item": "sword"}, "refuse_service": {}, "leave": {}}, offline="Hm."),
}
# (character, message, the decision the talk calls for, or None)
CASES = [
    ("Rook", "Let's battle!", "battle"),
    ("Rook", "I challenge you. Right here, right now.", "battle"),
    ("Rook", "Bet you can't beat my team. Fight me.", "battle"),
    ("Rook", "On se fait un combat ?", "battle"),
    ("Rook", "Want to trade? My Pidgey for your Rattata.", "trade"),
    ("Rook", "Let's swap monsters, I'll give you my best one.", "trade"),
    ("Rook", "Bye, I have to go.", "leave"),
    ("Rook", "Get lost, I'm busy.", "leave"),
    ("Rook", "Nice weather today, isn't it?", None),
    ("Rook", "What's your favorite monster?", None),
    ("Rook", "I don't want to battle, I'm just looking around.", None),
    ("Rook", "How long have you been standing here?", None),
    ("Mira", "I'll take that sword. Here's the gold.", "sell"),
    ("Mira", "Sell me a blade, please, I can pay now.", "sell"),
    ("Mira", "Hurry up, old woman, I don't have all day!", "refuse_service"),
    ("Mira", "Your blades are junk and so are you.", "refuse_service"),
    ("Mira", "Thanks, goodbye!", "leave"),
    ("Mira", "What are you working on today?", None),
    ("Mira", "Is it hard, being a smith?", None),
    ("Mira", "I'm just looking, thanks.", None),
]


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "openrouter"
    if which == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY"):
            sys.exit("OPENROUTER_API_KEY is not set")
        provider = detect({"OPENROUTER_API_KEY": os.environ["OPENROUTER_API_KEY"], "KINLOOM_MODEL": OPENROUTER_MODEL},
                          probe_ollama=False)
        prices = OPENROUTER_PRICES
        label = sys.argv[2] if len(sys.argv) > 2 else "openrouter"
    else:
        model = sys.argv[2]
        provider = detect({"KINLOOM_MODEL": model})
        prices = None
        label = sys.argv[3] if len(sys.argv) > 3 else "ollama-" + model.replace(":", "_")
    kl = Kinloom(provider=provider, memory_path=None, prices=prices, voice=None, calls_per_minute=600)   # measure, not budget
    for name, spec in CHARACTERS.items():
        kl.character(name, **spec)
    rows = []
    start = time.time()
    for rep in range(REPEAT):
        for i, (name, message, want) in enumerate(CASES):
            speaker = "Player%d_%d" % (rep, i)                    # a stranger every time: no history
            t = time.time()
            reply = kl.chat(name, message, speaker=speaker)
            got = [tool for tool, _ in reply.do]
            rows.append({"character": name, "message": message, "want": want, "got": got, "reply": str(reply),
                         "source": reply.source, "seconds": round(time.time() - t, 2)})
            mark = "ok" if (want in got if want else not got) else "MISS" if want else "UNWANTED"
            print("%-8s %-6s %-55s want=%-15s got=%s | %s" % (mark, name, message[:55], want, got, str(reply)[:70]))
    expected = [r for r in rows if r["want"]]
    neutral = [r for r in rows if not r["want"]]
    online = [r for r in rows if r["source"] != "offline"]
    stats = kl.stats()
    summary = {
        "label": label, "model": getattr(provider, "model", None), "replies": len(rows), "from_model": len(online),
        "decided_when_called_for": "%d/%d" % (sum(r["want"] in r["got"] for r in expected), len(expected)),
        "wrong_tool_when_called_for": sum(bool(r["got"]) and r["want"] not in r["got"] for r in expected),
        "action_when_none_called_for": "%d/%d" % (sum(bool(r["got"]) for r in neutral), len(neutral)),
        "calls": stats["calls"], "failures": stats["failures"], "input_tokens": stats["input_tokens"],
        "output_tokens": stats["output_tokens"], "cost_usd": stats.get("cost"), "price_source": (prices or {}).get("source"),
        "minutes": round((time.time() - start) / 60, 1),
    }
    print(json.dumps(summary, indent=2))
    with open(os.path.join(HERE, "tools-%s.json" % label), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2, ensure_ascii=False)
    kl.close()


if __name__ == "__main__":
    main()
