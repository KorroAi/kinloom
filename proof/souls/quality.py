"""Does a Kinloom soul read more like a real person than a plain prompt? A model stand-in for the human blind test,
used to compare versions of Kinloom's prompt, not to replace a human verdict. Spends cents (one OpenRouter model).

    python proof/souls/quality.py [label]        # writes quality-<label>.json

Six scenes, the same player lines for both sides, the same model (deepseek/deepseek-v4.1-flash on OpenRouter):
Kinloom (soul, memory, mood) against the naive prompt a developer writes in five minutes (one sentence, the whole
conversation so far). Judging, by the same model:
- each transcript scored alone, 1-10, three times (no position to be biased by);
- each pair judged in both orders; a pick counts only when it survives the swap (else it is a tie).
Stage directions are cleaned from both sides the same way, as on the blind page.
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
from kinloom.brain import _STAGE, _unstage  # noqa: E402
from kinloom.providers import detect  # noqa: E402

MODEL = "deepseek/deepseek-v4.1-flash"
PRICES = {"input": 0.30, "cached_input": 0.006, "output": 1.20,
          "source": "https://openrouter.ai/api/v1/models, deepseek/deepseek-v4.1-flash, read on 2026-09-29"}
DAY = "(the next day)"
SCENES = {
    "smith": ("Mira", "a widowed blacksmith, gruff and proud, who secretly sold the king's sword to pay her debts", None,
              "Ana", ["", "Nice toy hammer.", "Sorry, I was joking. Everyone says you're the best smith in town.",
                      "That sword on the wall... it looks like the king's. Is it?",
                      "My village is attacked every night. I need a blade. I can pay you tomorrow, I swear."]),
    "keeper": ("Orrin", "an old lighthouse keeper who talks to the sea and hides a letter he never sent", None,
               "Ana", ["", "I'm Ana. I'll bring you lamp oil tomorrow, I promise.", "What do you do all night up here?",
                       DAY, "Sorry... I forgot the oil."]),
    "rival": ("Juno", "une pilote rivale arrogante qui fait semblant de s'en moquer mais veut ton respect", "French",
              "Sam", ["", "T'as eu de la chance aujourd'hui.", "Tu veux une revanche demain ?", DAY,
                        "Bon, t'avais raison. T'es meilleure que moi."]),
    "return": ("Hesper", "a tired innkeeper who has seen too many adventurers die and pretends not to care", None,
               "Tomas", ["", "A room for the night, please. I'm heading into the mines tomorrow.",
                         "Is it true nobody comes back from the lower levels?", DAY,
                         "I made it back. Barely. My friend didn't."]),
    "kindness": ("Pell", "a shy apprentice alchemist who blew up his master's workshop and is afraid of being sent home",
                 None, "Ana", ["", "Hey, are you okay? You look like you haven't slept.",
                               "I heard about the workshop. Everyone makes mistakes.",
                               "If you want, I can help you clean up tomorrow.", DAY,
                               "I'm here, as promised. Where do we start?"]),
    "merchant": ("Vesk", "a sly desert merchant who loves haggling and never gives anything for free", None,
                 "Kai", ["", "What's the price of that lantern?", "That's robbery. I'll give you half.",
                         "Fine. I'll add a story from the northern roads if you lower it.",
                         "Once, I saw the sea freeze in a single night. Ships stuck like flies in amber."]),
}
SYSTEM_JUDGE_ONE = ("You judge dialogue for a video game. Rate how much the character in this transcript feels like a"
                    " real, specific person (a voice of their own, memory of what was said, feelings that move with"
                    " how they are treated, an inner life) rather than a generic chatbot, from 1 to 10. Answer with the"
                    " number only.")
SYSTEM_JUDGE_PAIR = ("You judge dialogue for a video game. Two transcripts of the same scene follow, X and Y: the same"
                     " player lines, different replies from the character. Which character feels more like a real,"
                     " specific person (a voice of their own, memory, feelings that move, an inner life)? Answer with"
                     " one letter: X or Y.")


def clean(text):
    return " ".join(_STAGE.sub(_unstage, text or "").split())


def naive(provider, name, sentence, language, speaker, lines):
    system = "You are %s, %s. Stay in character and reply briefly.%s" % (
        name, sentence, (" Answer in %s." % language) if language else "")
    history, out = [], []
    for m in lines:
        if m == DAY:
            history.append(m)
            out.append((m, ""))
            continue
        user = "\n".join(history + ["%s: %s" % (speaker, m or "(walks up)")]) + "\n%s:" % name
        r = provider.complete(system, user, max_tokens=300, timeout=25)
        text = clean(r.text) if r.ok else ""
        history += ["%s: %s" % (speaker, m or "(walks up)"), "%s: %s" % (name, text)]
        out.append((m, text))
    return out


def souls(kl, name, speaker, lines, wall):
    out = []
    for m in lines:
        if m == DAY:
            wall[0] += 86400
            out.append((m, ""))
            continue
        out.append((m, kl.chat(name, m, speaker=speaker)))
    return out


def transcript(rows, speaker, name):
    parts = []
    for m, r in rows:
        if m == DAY:
            parts.append(DAY)
        else:
            parts.append("%s: %s\n%s: %s" % (speaker, m or "(walks up)", name, r))
    return "\n".join(parts)


def main(label="current"):
    key = os.environ.get("OPENROUTER_API_KEY") or sys.exit("OPENROUTER_API_KEY is not set")
    p = detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": MODEL}, probe_ollama=False)
    kl = Kinloom(provider=p, memory_path=os.path.join(tempfile.mkdtemp(), "m.json"), prices=PRICES, call_timeout=25,
                 calls_per_minute=200)
    wall = [time.time()]
    kl.brain.wall = lambda: wall[0]
    for scene, (name, sentence, language, speaker, lines) in SCENES.items():
        kl.character(name, soul=sentence, language=language, offline="...")
    kl.wait_idle(90)
    results, scores, pairs = {}, {"souls": [], "naive": []}, {"souls": 0, "naive": 0, "tie": 0}
    judge_calls = 0
    for scene, (name, sentence, language, speaker, lines) in SCENES.items():
        a = souls(kl, name, speaker, lines, wall)
        b = naive(p, name, sentence, language, speaker, lines)
        ta, tb = transcript(a, speaker, name), transcript(b, speaker, name)
        s = {"souls": [], "naive": []}
        for label_, t in (("souls", ta), ("naive", tb)):
            for _ in range(3):
                r = p.complete(SYSTEM_JUDGE_ONE, t, max_tokens=10, temperature=0.7, timeout=60)
                judge_calls += 1
                m = re.search(r"\b(10|[1-9])\b", r.text or "")
                if m:
                    s[label_].append(int(m.group(1)))
                    scores[label_].append(int(m.group(1)))
        picks = []
        for first, second in (("souls", "naive"), ("naive", "souls")):
            pair = {"souls": ta, "naive": tb}
            r = p.complete(SYSTEM_JUDGE_PAIR, "X:\n%s\n\nY:\n%s" % (pair[first], pair[second]), max_tokens=5,
                           temperature=0.0, timeout=60)
            judge_calls += 1
            m = re.match(r"\W*([XY])\b", r.text or "")
            picks.append({"X": first, "Y": second}[m.group(1)] if m else None)
        verdict = picks[0] if picks[0] == picks[1] and picks[0] else "tie"
        pairs[verdict] += 1
        results[scene] = {"souls": a, "naive": b, "scores": s, "pair_picks": picks, "pair": verdict}
        print("%-9s souls %s naive %s | pair %s %s" % (scene, s["souls"], s["naive"], picks, verdict))
        sys.stdout.flush()
    mean = {k: round(sum(v) / len(v), 2) if v else None for k, v in scores.items()}
    stats = kl.stats()
    summary = {"label": label, "mean_scores": mean, "pairs_consistent": pairs, "judge_calls": judge_calls,
               "kinloom_cost_usd": stats["cost"], "kinloom_calls": stats["calls"], "offline": stats["offline_answers"]}
    print(json.dumps(summary, indent=1))
    with open(os.path.join(HERE, "quality-%s.json" % label), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "scenes": results}, f, indent=1, ensure_ascii=False)
    kl.close()


if __name__ == "__main__":
    main(*sys.argv[1:])
