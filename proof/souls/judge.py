"""A stand-in for the blind test, NOT a replacement: models read each scene twice (Kinloom souls, naive prompt), in both
orders, and say which character feels more like a real person. Only a human verdict (blind.html) settles it.

    python proof/souls/judge.py ollama qwen3:8b       # local judge, free
    python proof/souls/judge.py openrouter            # the same OpenRouter model (cents; it also wrote the replies)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python", "src"))

from kinloom.brain import _STAGE, _unstage  # noqa: E402
from kinloom.providers import detect  # noqa: E402

LINES = {"A": ("Mira", "Ana"), "B": ("Orrin", "Ana"), "D": ("Juno", "Sam")}
SYSTEM = ("You judge dialogue for a video game. Two transcripts of the same scene follow, X and Y: the same player lines,"
          " different replies from the character. Which character feels more like a real, specific person (voice,"
          " memory of what was said, reactions, an inner life), not a generic chatbot? Answer with one letter, X or Y,"
          " then one short sentence why.")


SCORE = ("You judge dialogue for a video game. Rate how much the character in this transcript feels like a real, specific"
         " person (voice, memory of what was said, reactions, an inner life) rather than a generic chatbot, from 1 to 10."
         " Answer with the number only.")


def transcript(rows, speaker, name):
    return "\n".join("%s: %s\n%s: %s" % (speaker, m or "(walks up)", name, r) for m, r in rows)


def main(kind="ollama", model="qwen3:8b"):
    if kind == "ollama":
        p = detect({"KINLOOM_BASE_URL": "http://127.0.0.1:11434/v1", "KINLOOM_MODEL": model}, probe_ollama=False)
    else:
        key = os.environ.get("OPENROUTER_API_KEY") or sys.exit("OPENROUTER_API_KEY is not set")
        p = detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": "deepseek/deepseek-v4.1-flash"}, probe_ollama=False)
    data = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
    votes, rows_out = {"souls": 0, "naive": 0, "unclear": 0}, []
    for scene, (name, speaker) in LINES.items():
        souls = [(e["message"], e["reply"]) for e in data["log"] if e["scene"] == scene]
        naive = [(e["message"], " ".join(_STAGE.sub(_unstage, e["reply"]).split())) for e in data["results"]["naive"][scene]]
        for order in (("souls", "naive"), ("naive", "souls")):
            pair = {"souls": souls, "naive": naive}
            user = "X:\n%s\n\nY:\n%s\n" % (transcript(pair[order[0]], speaker, name), transcript(pair[order[1]], speaker, name))
            r = p.complete(SYSTEM, user, max_tokens=120, temperature=0.0, timeout=120)
            m = re.match(r"\W*([XY])\b", r.text or "")
            pick = {"X": order[0], "Y": order[1]}[m.group(1)] if m else "unclear"
            votes[pick] += 1
            rows_out.append({"scene": scene, "order": list(order), "pick": pick, "why": (r.text or r.error or "")[:300]})
            print(scene, order, "->", pick, "|", (r.text or r.error or "").strip()[:160])
    print(json.dumps(votes))
    # Pairs gave the second transcript every time (position bias): each one is also scored alone, three times.
    scores = {"souls": [], "naive": []}
    for scene, (name, speaker) in LINES.items():
        souls = [(e["message"], e["reply"]) for e in data["log"] if e["scene"] == scene]
        naive = [(e["message"], " ".join(_STAGE.sub(_unstage, e["reply"]).split())) for e in data["results"]["naive"][scene]]
        for label, rows in (("souls", souls), ("naive", naive)):
            for _ in range(3):
                r = p.complete(SCORE, transcript(rows, speaker, name), max_tokens=20, temperature=0.7, timeout=120)
                m = re.search(r"\b(10|[1-9])\b", r.text or "")
                if m:
                    scores[label].append(int(m.group(1)))
                    rows_out.append({"scene": scene, "scored": label, "score": int(m.group(1))})
    mean = {k: round(sum(v) / len(v), 2) if v else None for k, v in scores.items()}
    print("scores alone:", json.dumps(mean), {k: len(v) for k, v in scores.items()})
    out = os.path.join(HERE, "judge-%s-%s.json" % (kind, re.sub(r"[^\w.-]+", "_", p.model)))
    json.dump({"judge": p.describe(), "votes": votes, "mean_scores": mean, "rows": rows_out},
              open(out, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
