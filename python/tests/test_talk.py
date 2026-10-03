"""Talk in a game loop: never blocks, streams, brings actions back; the Pygame box (when Pygame is installed)."""
import os
import time

import pytest

from kinloom.talk import Talk
from test_brain import make, model


def loop(talk, seconds=3.0):
    end = time.monotonic() + seconds
    while talk.waiting and time.monotonic() < end:
        talk.update()
        time.sleep(0.01)
    talk.update()


def slow_model(delay, *answers):
    queue = list(answers)
    p = model(chat=None)
    original = p.fn

    def fn(kind, system, user):
        if "task: chat" in system:
            time.sleep(delay)
            return queue.pop(0)
        return original(kind, system, user)
    p.fn = fn
    return p


def test_send_returns_at_once_and_the_reply_comes_in_later():
    kl = make(slow_model(0.3, 'Hmph. What?\n~~~\n{"mood": "annoyed"}', "Fine. Take the wood.\n~~~\n" +
                         '{"do": [{"tool": "give", "args": {"item": "wood"}}]}'))
    kl.character("MIRA", "a blacksmith", tools={"give": {"item": "wood"}}, offline="Busy.")
    got = []
    talk = Talk(kl, "MIRA", speaker="Ana", on_action=lambda tool, args: got.append((tool, args)))
    t = time.monotonic()
    talk.open()
    assert time.monotonic() - t < 0.1 and talk.waiting
    loop(talk)
    assert talk.lines == [("MIRA", "Hmph. What?")] and talk.mood == "annoyed" and not talk.waiting
    assert talk.send("I need wood.")
    loop(talk)
    assert talk.lines[-1] == ("MIRA", "Fine. Take the wood.") and got == [("give", {"item": "wood"})]


def test_offline_the_box_still_answers():
    kl = make(None)
    kl.character("MIRA", "a blacksmith", offline="Busy. Come back later.")
    talk = Talk(kl, "MIRA", speaker="Ana")
    talk.send("hello")
    loop(talk)
    assert talk.lines[-1] == ("MIRA", "Busy. Come back later.")


def test_facts_can_be_read_at_the_moment_of_speaking():
    p = model(chat="Aye.\n~~~\n{}")
    kl = make(p)
    kl.character("MIRA", "a blacksmith")
    fire = [0.2]
    talk = Talk(kl, "MIRA", speaker="Ana", facts=lambda: {"fire": fire[0]})
    fire[0] = 0.9
    talk.send("How is the fire?")
    loop(talk)
    assert '"fire": 0.9' in [u for t, s, u in p.calls if t == "chat"][0]


def test_the_pygame_box_types_sends_and_draws():
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    from kinloom.talk import PygameTalkBox
    kl = make(model(chat="Well met.\n~~~\n{}"))
    kl.character("MIRA", "a blacksmith")
    box = PygameTalkBox(kl, "MIRA", speaker="Ana")
    box.open(speak_first=False)
    box.update()                                          # the next frame: typing goes in
    for ch in "hi":
        assert box.handle(pygame.event.Event(pygame.TEXTINPUT, text=ch))
    assert box.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    loop(box)
    box.draw(screen)
    assert box.lines == [("Ana", "hi"), ("MIRA", "Well met.")] and box.typed == ""
    assert box.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) and not box.is_open
    assert not box.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))
    pygame.quit()


def test_a_message_sent_while_she_is_still_talking_waits_its_turn():
    kl = make(slow_model(0.3, "Evening.\n~~~\n{}", "Aye, the fire holds.\n~~~\n{}"))
    kl.character("MIRA", "a blacksmith")
    talk = Talk(kl, "MIRA", speaker="Ana")
    talk.open()
    assert talk.send("How is the fire?")                  # she is still speaking: queued, shown at once
    assert not talk.send("Hello?")                        # one message waits at most
    assert talk.lines == [("Ana", "How is the fire?")]
    loop(talk)
    loop(talk)
    assert talk.lines == [("MIRA", "Evening."), ("Ana", "How is the fire?"), ("MIRA", "Aye, the fire holds.")]


def test_the_key_that_opens_the_box_is_not_typed_into_it():
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))
    from kinloom.talk import PygameTalkBox
    kl = make(model(chat="Hm.\n~~~\n{}"))
    kl.character("MIRA", "a blacksmith")
    box = PygameTalkBox(kl, "MIRA", speaker="Ana")
    box.open(speak_first=False)                           # opened on the T key down...
    box.handle(pygame.event.Event(pygame.TEXTINPUT, text="t"))   # ...whose text event comes in the same frame
    box.update()
    box.handle(pygame.event.Event(pygame.TEXTINPUT, text="h"))
    assert box.typed == "h"
    pygame.quit()


# ---------------- voice ----------------

class _Streaming:
    """A model that writes its reply piece by piece, like a real one streaming."""
    name = model_name = "streaming"

    def __init__(self, pieces, pause=0.15):
        self.pieces, self.pause = pieces, pause

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None):
        from kinloom.providers import Reply
        if "task: chat" not in system:
            return Reply(False, error="only chat here")
        for p in self.pieces:
            if on_text:
                on_text(p)
            time.sleep(self.pause)
        return Reply(True, "".join(self.pieces), None, 10, 0, 10, 0.1)

    def describe(self):
        return "streaming"

    def local(self):
        return True


def test_talk_speaks_each_sentence_as_soon_as_it_is_written():
    from kinloom.voice import ScriptedVoice
    v = ScriptedVoice()
    # (the first 48 characters are held until known to be in character: a real reply is longer than that)
    kl = make(_Streaming(["Hello there, traveller from the far northern roads. ", "How are you? ", "Fine.\n~~~\n{}"]), voice=v)
    kl.character("MIRA", "a blacksmith", voice="low")
    got, early = [], []
    talk = Talk(kl, "MIRA", speaker="Ana", voice=True, on_audio=got.append)
    talk.send("Hi Mira.")                       # (a first line to a stranger is prepared ahead: not streamed)
    end = time.monotonic() + 5
    while talk.waiting and time.monotonic() < end:
        talk.update()
        if got and not early:
            early.append(talk.waiting)          # the first sentence was heard while the reply was still coming
        time.sleep(0.01)
    for _ in range(100):
        talk.update()
        if len(got) == 3:
            break
        time.sleep(0.02)
    said = ["Hello there, traveller from the far northern roads.", "How are you?", "Fine."]
    assert [t for t, _ in v.spoken] == said
    assert [a.text for a in got] == said and early == [True]


def test_offline_replies_are_spoken_and_what_the_player_says_is_sent():
    from kinloom.voice import ScriptedVoice, tone
    v = ScriptedVoice(listen_fn=lambda data, fmt, lang: "I need wood")
    kl = make(None, voice=v)
    kl.character("MIRA", "a blacksmith", offline="Busy. Come back later.")
    got = []
    talk = Talk(kl, "MIRA", speaker="Ana", voice=True, on_audio=got.append)
    assert talk.hear(tone(0.5)) and not talk.hear(tone(0.5))      # one recording at a time
    for _ in range(200):
        talk.update()
        if len(got) >= 1 and not talk.waiting:
            break
        time.sleep(0.01)
    assert talk.heard == "I need wood" and talk.lines == [("Ana", "I need wood"), ("MIRA", "Busy. Come back later.")]
    assert [a.text for a in got] == ["Busy. Come back later."]


def test_without_voice_nothing_is_spoken():
    from kinloom.voice import ScriptedVoice
    v = ScriptedVoice()
    kl = make(None, voice=v)
    kl.character("MIRA", "a blacksmith", offline="Busy.")
    talk = Talk(kl, "MIRA", speaker="Ana")
    talk.send("hi")
    loop(talk)
    assert talk.lines[-1] == ("MIRA", "Busy.") and v.spoken == []


def test_the_pygame_box_speaks_and_records_while_the_key_is_held():
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    from kinloom.talk import PygameTalkBox
    from kinloom.voice import ScriptedVoice
    v = ScriptedVoice(listen_fn=lambda data, fmt, lang: "hello smith")
    kl = make(model(chat="Well met. What do you need?\n~~~\n{}"), voice=v)
    kl.character("MIRA", "a blacksmith")
    box = PygameTalkBox(kl, "MIRA", speaker="Ana", voice=True)
    box.open(speak_first=False)
    box.update()
    assert box.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    box.draw(screen)                                         # "(listening...)" or the microphone's problem, never a crash
    assert box.handle(pygame.event.Event(pygame.KEYUP, key=pygame.K_TAB)) and not box.recording
    box.hear(__import__("kinloom.voice", fromlist=["tone"]).tone(0.5))       # what a real microphone would give
    for _ in range(300):
        box.update()
        if box.lines and box.lines[-1][0] == "MIRA" and v.spoken:
            break
        time.sleep(0.01)
    box.draw(screen)
    assert box.lines == [("Ana", "hello smith"), ("MIRA", "Well met. What do you need?")]
    assert [t for t, _ in v.spoken] == ["Well met. What do you need?"]
    box.close()
    pygame.quit()
