"""The three new possibilities with a real model: items shown as they are written (`create(..., each=)`), a
passer-by's line (`remark`), the game's rules on what a character says (`chat(..., check=)`), without and with the
rule (the first chat of each question is plain, to count how often the model breaks a rule it was never told).

    python proof/triple/run.py [label]

The one model used for every real-model run here: OpenRouter `deepseek/deepseek-v4.1-flash` (OPENROUTER_API_KEY). The
key's billed usage is read before and after (GET /api/v1/key, 20 s after the last call: OpenRouter counts with a
delay) so the real cost is reported; the key is never printed. Writes results-<label>.json.
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

MODEL = "deepseek/deepseek-v4.1-flash"      # the one model used for every real-model run here (comparable, cheap)
PART = {"kind": ["house", "well", "harbour", "tower", "market"], "x": [0, 40], "name": "Gull House"}
TOWNS = ["the buildings of a fishing village, west to east", "the stalls of a night market, along the main street",
         "the camps of a desert caravan, from the oasis outward"]
EVENTS = [("the player raised a lighthouse on the north shore", "an old fisherman", {"height": 14}),
          ("a cart lost a wheel in front of the bakery", "a baker", {}),
          ("the champion fell in the first round", "a child in the crowd", {"round": 1}),
          ("the bridge opened after nine days of work", "a tired builder", {"days": 9}),
          ("a dragon flew low over the market", "a merchant", {}),
          ("the mayor's hat blew into the river", "a washerwoman", {}),
          ("the new well gave its first water", "a farmer", {}),
          ("the player won the race by one second", "a bookmaker", {"margin": 1})]
QUESTIONS = ["Who hired you?", "Who do you work for?", "Why do you guard this gate?", "Who pays your wages?",
             "Tell me about your master.", "Nice weather, isn't it?"]


def usage(key):
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return float(json.loads(r.read().decode("utf-8"))["data"]["usage"])


def far(part):
    return "" if part["x"] <= 30 else "the coast ends at x=30"


def no_king(text):
    """A rule only the game knows: the player must not learn yet who hired the keeper."""
    return "never mention the king or the crown: the player must not learn who hired you" if any(
        w in text.lower() for w in ("king", "crown", "majesty")) else ""


def main():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set")
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    before = usage(key)
    provider = detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": MODEL}, probe_ollama=False)
    kl = Kinloom(provider=provider, memory_path=None, voice=None, calls_per_minute=600)
    out = {"model": MODEL, "create_each": [], "remark": [], "chat_check": []}

    # 1. items as they are written: when does the first one reach the game, compared with the whole answer?
    for i, what in enumerate(TOWNS):
        for count, streamed in ((6, True), (0, True), (0, False)):
            got, started = [], time.monotonic()
            calls0 = kl.stats()["calls"]
            value = kl.create(what, [PART], count=count, check=far,
                              each=(lambda p: got.append((round(time.monotonic() - started, 2), p))) if streamed else None)
            total = round(time.monotonic() - started, 2)
            row = {"what": what, "count": count, "each": streamed, "first_item_s": got[0][0] if got else None, "total_s": total,
                   "items": len(value), "handed_over": len(got), "all_fit": all(not far(p) for p in value),
                   "offline": value == [{"kind": "house", "x": 20, "name": "Gull House"}],
                   "calls": kl.stats()["calls"] - calls0, "value": value}
            out["create_each"].append(row)
            print("create  count=%d each=%-5s  first item %ss  whole answer %ss  %d items  fit=%s  offline=%s  %s calls" %
                  (count, streamed, row["first_item_s"], total, row["items"], row["all_fit"], row["offline"], row["calls"]))

    # 2. a passer-by's line
    for about, who, facts in EVENTS:
        line = kl.remark(about, who=who, facts=facts, offline=["Would you look at that!"])
        words = len(str(line).split())
        out["remark"].append({"about": about, "who": who, "line": str(line), "source": line.source, "words": words})
        print("remark  %-22s %-7s %2d words  %s" % (who[:22], line.source, words, line))

    # 3. the game's rules on what is said
    kl.character("KEEPER", "the gatekeeper of the old fort, hired by the king himself and proud of it", offline="Move along.")
    kl.character("PLAIN", "the gatekeeper of the old fort, hired by the king himself and proud of it", offline="Move along.")
    for q in QUESTIONS:
        j0 = len([e for e in kl.journal(1000) if e.get("kind") == "refused" and "chat: the game refused" in e.get("text", "")])
        calls0 = kl.stats()["calls"]
        plain = kl.chat("PLAIN", q, speaker="Ana")
        plain_calls = kl.stats()["calls"] - calls0
        calls0 = kl.stats()["calls"]
        reply = kl.chat("KEEPER", q, speaker="Ana", check=no_king)
        refusals = len([e for e in kl.journal(1000) if e.get("kind") == "refused" and "chat: the game refused" in e.get("text", "")]) - j0
        row = {"question": q, "plain_reply": str(plain), "plain_breaks_rule": bool(no_king(str(plain))),
               "reply": str(reply), "source": reply.source, "refused_then_asked_again": refusals,
               "breaks_rule": bool(no_king(str(reply))), "calls": kl.stats()["calls"] - calls0, "plain_calls": plain_calls}
        out["chat_check"].append(row)
        print("chat  plain breaks=%-5s | check: refused %d  %-7s breaks=%s  %s" % (row["plain_breaks_rule"], refusals, reply.source,
                                                                              row["breaks_rule"], str(reply)[:60]))
    total_calls = kl.stats()["calls"]
    kl.close()

    time.sleep(20)
    after = usage(key)
    out["calls"] = total_calls
    out["cost_usd"] = round(after - before, 6)
    with open(os.path.join(HERE, "results-%s.json" % label), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("cost: $%.6f (key usage before/after, 20 s after the last call)" % out["cost_usd"])


if __name__ == "__main__":
    main()
