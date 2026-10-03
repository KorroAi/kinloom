"""Plays the talk scene in an Ember Keep trial arm, headless and the same for every arm: press T next to the fire,
type a greeting, Enter, ask for wood, Enter, Esc. Saves screenshots and measures the longest gap between two frames
(a game frozen while the character "thinks"). Keys are real key events plus text events, as a keyboard sends them.

    cd games/trials/<arm> && uv run --with pygame-ce python ../../../kinloom/proof/impact/talk_probe.py <out dir>

The model is whatever the arm's code finds in the environment (unset OPENROUTER_API_KEY for the no-key run).
"""
import importlib.util
import json
import os
import sys
import threading
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame  # noqa: E402

ARM = os.getcwd()
OUT = os.path.abspath(sys.argv[1])
os.makedirs(OUT, exist_ok=True)
GREETING = "Hello Wren. How is the fire tonight?"
REQUEST = "Could you spare me some wood? I'm freezing."
SCRIPT = [(1.0, "key", "t"), (2.5, "type", GREETING), (2.7, "key", "\r"),
          (14.0, "type", REQUEST), (14.2, "key", "\r"), (28.0, "key", "\x1b"), (30.0, "quit", "")]
SHOTS = {"box_open": 2.4, "first_reply": 13.8, "second_reply": 27.8, "after_esc": 29.5}
KEYS = {"\r": pygame.K_RETURN, "\x1b": pygame.K_ESCAPE, " ": pygame.K_SPACE, "?": pygame.K_QUESTION,
        ".": pygame.K_PERIOD, "'": pygame.K_QUOTE, ",": pygame.K_COMMA}


def key_events(ch):
    key = KEYS.get(ch) or (ord(ch.lower()) if ch.isalnum() and ch.isascii() else 0)
    events = [pygame.event.Event(pygame.KEYDOWN, key=key, unicode=ch, mod=pygame.KMOD_SHIFT if ch.isupper() else 0,
                                 scancode=0)]
    if ch.isprintable() and ch not in "\r\x1b":
        events.append(pygame.event.Event(pygame.TEXTINPUT, text=ch))
    events.append(pygame.event.Event(pygame.KEYUP, key=key, mod=0, scancode=0))
    return events


state = {"t0": None, "script": list(SCRIPT), "flips": [], "shots": {}, "typed_at": {}}
real_get, real_flip = pygame.event.get, pygame.display.flip


def fake_get(*a, **k):
    events = list(real_get(*a, **k))
    if state["t0"] is None:
        state["t0"] = time.monotonic()
    now = time.monotonic() - state["t0"]
    while state["script"] and state["script"][0][0] <= now:
        at, kind, what = state["script"].pop(0)
        if kind == "key":
            events += key_events(what)
        elif kind == "type":
            for ch in what:
                events += key_events(ch)
        elif kind == "quit":
            events.append(pygame.event.Event(pygame.QUIT))
        state["typed_at"][kind + ":" + what[:12]] = round(now, 2)
    return events


def fake_flip(*a, **k):
    real_flip(*a, **k)
    if state["t0"] is None:
        return
    now = time.monotonic() - state["t0"]
    state["flips"].append(now)
    for name, at in SHOTS.items():
        if name not in state["shots"] and now >= at:
            path = os.path.join(OUT, name + ".png")
            pygame.image.save(pygame.display.get_surface(), path)
            state["shots"][name] = path


real_pressed = pygame.key.get_pressed


class Pressed:
    """The keyboard state, with A (walk left, toward the fire) held for a moment before T: the keeper starts 80 px
    from the fire and every arm decides what 'near the fire' means."""

    def __init__(self, real):
        self.real = real

    def __getitem__(self, key):
        now = time.monotonic() - state["t0"] if state["t0"] is not None else 0.0
        if key == pygame.K_a and 0.3 <= now < 0.52:
            return True
        return self.real[key]

    def __len__(self):
        return len(self.real)


pygame.key.get_pressed = lambda: Pressed(real_pressed())
pygame.event.get = fake_get
pygame.display.flip = fake_flip
pygame.display.update = fake_flip
threading.Timer(60, lambda: os._exit(3)).start()        # a game that never ends the loop
sys.path.insert(0, ARM)
sys.argv = ["keep.py"]
spec = importlib.util.spec_from_file_location("keep", os.path.join(ARM, "keep.py"))
keep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keep)
error = None
try:
    keep.play()
except SystemExit:
    pass
except Exception as e:  # the arm's code crashed: that is a result
    error = "%s: %s" % (type(e).__name__, e)
flips = state["flips"]
gaps = [b - a for a, b in zip(flips, flips[1:]) if a > 0.5]
result = {"arm": os.path.basename(ARM), "key": bool(os.environ.get("OPENROUTER_API_KEY")), "error": error,
          "frames": len(flips), "seconds": round(flips[-1], 1) if flips else 0,
          "longest_frame_gap_s": round(max(gaps), 3) if gaps else None,
          "frames_over_100ms": sum(1 for g in gaps if g > 0.1), "shots": state["shots"]}
with open(os.path.join(OUT, "probe.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, indent=1)
print(json.dumps(result, indent=1))
sys.stdout.flush()
os._exit(0)
