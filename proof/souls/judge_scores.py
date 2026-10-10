"""More scores for judge.py's single-transcript rating (no pairs: the pairs only measured position bias): each scene's
Kinloom souls and naive transcripts rated N times by the one allowed OpenRouter model. Not a verdict: the human
blind test (blind.html) is.

    python proof/souls/judge_scores.py 15      # 3 scenes x 2 sides x 15 = 90 short calls (about $0.002)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import judge  # noqa: E402
from kinloom.brain import _STAGE, _unstage  # noqa: E402
from kinloom.providers import detect  # noqa: E402


def main(n=15):
    key = os.environ.get("OPENROUTER_API_KEY") or sys.exit("OPENROUTER_API_KEY is not set")
    p = detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": "deepseek/deepseek-v4.1-flash"}, probe_ollama=False)
    data = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
    out = {}
    for scene, (name, speaker) in judge.LINES.items():
        souls = [(e["message"], e["reply"]) for e in data["log"] if e["scene"] == scene]
        naive = [(e["message"], " ".join(_STAGE.sub(_unstage, e["reply"]).split())) for e in data["results"]["naive"][scene]]
        for label, rows in (("souls", souls), ("naive", naive)):
            got = []
            for _ in range(n):
                r = p.complete(judge.SCORE, judge.transcript(rows, speaker, name), max_tokens=20, temperature=0.7, timeout=120)
                m = re.search(r"\b(10|[1-9])\b", r.text or "")
                if m:
                    got.append(int(m.group(1)))
            out.setdefault(scene, {})[label] = got
            print(scene, label, got, flush=True)
    summary = {}
    for label in ("souls", "naive"):
        allv = [v for s in out.values() for v in s[label]]
        summary[label] = {"mean": round(sum(allv) / len(allv), 2), "n": len(allv)}
    per_scene = {s: {k: round(sum(v) / len(v), 2) for k, v in d.items() if v} for s, d in out.items()}
    print("per scene:", json.dumps(per_scene))
    print("overall:", json.dumps(summary))
    json.dump({"judge": p.describe(), "repeats": n, "scores": out, "per_scene": per_scene, "overall": summary},
              open(os.path.join(HERE, "judge-scores-run5.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15)
