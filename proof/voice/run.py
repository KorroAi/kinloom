"""Voice with the operating system only (no key, no network, free): how fast lines are spoken, how fast and how well
the system hears them back. Windows only (System.Speech); the recognizer is the one of the system's language.

    python proof/voice/run.py            # writes results.json next to this file

Every line is spoken by the system voice to a WAV, then that WAV is heard by the system recognizer: a clean recording
(a machine voice, no room noise), so the scores are an upper bound for a real microphone.
"""
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python", "src"))

from kinloom.voice import SystemVoice, wav_seconds  # noqa: E402

LINES = {
    "fr": ["Apporte-moi trois bûches avant la tombée de la nuit.",
           "Je veux acheter la lanterne, combien coûte-t-elle ?",
           "Ouvre la porte du nord, les gardes sont partis.",
           "Est-ce que tu as vu le voleur passer par ici ?",
           "Le forgeron m'a dit que tu connaissais le chemin.",
           "Donne-moi ton épée et je te laisse partir.",
           "Nous partirons à l'aube vers la montagne.",
           "Je n'ai pas d'argent mais je peux travailler pour toi.",
           "Qui a éteint le feu cette nuit ?",
           "Merci pour ton aide, je reviendrai demain."],
    "en": ["Bring me three logs before night falls.",
           "How much for the lantern on the wall?",
           "The guards left the north gate open."],
}


def words(text):
    return re.findall(r"[a-zà-ÿœ0-9]+", (text or "").lower())


def overlap(said, heard):
    """Share of the said words found in what was heard, in order (a simple word accuracy, not a formal WER)."""
    a, b = words(said), words(heard)
    if not a:
        return 0.0
    # longest common subsequence of words
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1] / len(a)


def main():
    if not sys.platform.startswith("win"):
        sys.exit("Windows only")
    s = SystemVoice()
    start = time.monotonic()
    voices = s.voices()
    first = time.monotonic() - start
    rows = []
    for lang, lines in LINES.items():
        for line in lines:
            t = time.monotonic()
            wav, err = s.speak(line, {"seed": "MIRA", "language": lang})
            spoke = time.monotonic() - t
            row = {"lang": lang, "said": line, "speak_s": round(spoke, 3), "error": err,
                   "audio_s": round(wav_seconds(wav), 2) if wav else 0}
            if wav and s._hears == lang:
                t = time.monotonic()
                heard, err = s.listen(wav, "wav", lang)
                row.update(heard=heard, listen_s=round(time.monotonic() - t, 3), words=round(overlap(line, heard), 3),
                           error=err)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    s.close()
    spoken = [r["speak_s"] for r in rows if not r["error"] or "heard" in r]
    heard = [r for r in rows if "heard" in r]
    summary = {"voices": voices, "recognizer": s._hears, "worker_start_s": round(first, 2),
               "speak_s_median": round(statistics.median(spoken), 3), "speak_s_max": round(max(spoken), 3),
               "listen_s_median": round(statistics.median([r["listen_s"] for r in heard]), 3) if heard else None,
               "words_heard_mean": round(statistics.mean([r["words"] for r in heard]), 3) if heard else None,
               "exact": sum(1 for r in heard if r["words"] == 1.0), "heard_lines": len(heard)}
    json.dump({"date": time.strftime("%Y-%m-%d"), "summary": summary, "rows": rows},
              open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
