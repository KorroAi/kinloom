"""Kinloom answered by the developer's coding agent (its subscription), measured live.

    python proof/agents/run.py [claude-code] [model]       (default: claude-code haiku)

One soul character, its first greeting, five replies (time to the first word and to the whole reply), one create()
with a picture (a solid red PNG: does the model see it?). Prints a JSON summary; nothing is written to the game.
"""
import json
import os
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python", "src"))

from kinloom.brain import Brain  # noqa: E402
from kinloom.harness import Harness  # noqa: E402


def red_png(size=32):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * size for _ in range(size))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "claude-code"
    model = sys.argv[2] if len(sys.argv) > 2 else ("haiku" if kind == "claude-code" else None)
    h = Harness(kind, model)
    if h.missing:
        print(h.missing)
        return 1
    b = Brain(provider=h, memory_path=None, voice=None, call_timeout=60.0)
    t = time.monotonic()
    b.character("s", "Mira", soul="a gruff blacksmith in a mountain village who secretly writes poetry")
    ready = b.prepare("s", 120)
    out = {"agent": h.describe(), "prepare_s": round(time.monotonic() - t, 2), "ready": ready["ready"], "replies": []}
    for message in ["", "Can you fix my sword?", "How much will it cost?", "Do you ever write anything?",
                    "Thanks, see you tomorrow."]:
        first = []
        start = time.monotonic()
        said = b.chat("s", "Mira", message, speaker="Ana",
                      stream=lambda piece: first.append(time.monotonic() - start) if not first else None)
        out["replies"].append({"message": message, "reply": str(said), "source": said.source,
                               "first_word_s": round(first[0], 2) if first else None,
                               "whole_s": round(time.monotonic() - start, 2)})
    start = time.monotonic()
    seen = b.create("s", "the main color of this picture, one lowercase word", {"color": "blue"}, image=red_png(),
                    timeout=60)
    out["picture"] = {"answer": seen, "s": round(time.monotonic() - start, 2)}
    stats = b.stats()
    out["calls"] = stats.get("calls")
    out["failures"] = stats.get("failures")
    out["hedged"] = stats.get("hedged")
    out["problems"] = [e["text"] for e in b.journal(500) if e["kind"] in ("error", "refused", "cut", "empty")]
    b.close()
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
