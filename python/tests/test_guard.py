"""The tail guard on conversations: a slow first word starts a second request (the first to speak wins); a reply that
stalls or runs past its deadline ends with the sentences already said. Fake providers with controlled timing."""
import threading
import time

from kinloom import Kinloom
from kinloom.providers import Reply


class Timed:
    """Each call follows the next plan: [(delay, piece), ...]; the reply is the pieces joined."""
    name = "timed"
    model = "timed"

    def __init__(self, *plans):
        self.plans = list(plans)
        self.started = 0
        self.lock = threading.Lock()

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None):
        with self.lock:
            plan = self.plans.pop(0) if self.plans else [(0.0, "Fine.")]
            self.started += 1
        start = time.monotonic()
        text = ""
        for delay, piece in plan:
            time.sleep(delay)
            if time.monotonic() - start > timeout:
                return Reply(False, error="timed out", latency=time.monotonic() - start)
            text += piece
            if on_text:
                on_text(piece)
        return Reply(True, text, None, 100, 0, 20, time.monotonic() - start)


def make(p, **kw):
    kl = Kinloom(provider=p, memory_path=None, **kw)
    kl.brain.hedge_after, kl.brain.stall_after = 0.3, 0.4
    return kl


def test_a_slow_first_word_starts_a_second_request_and_the_first_to_speak_wins():
    p = Timed([(2.0, "Too late.")], [(0.05, "Quick "), (0.05, "answer.")])
    kl = make(p)
    start = time.monotonic()
    pieces = []
    assert kl.chat("Mira", "hi", stream=pieces.append) == "Quick answer."
    assert time.monotonic() - start < 1.0 and p.started == 2
    assert "".join(pieces) == "Quick answer."            # only the winner's words are shown
    for _ in range(150):                                  # the loser is still counted when it ends (it costs)
        if kl.stats()["calls"] == 2:
            break
        time.sleep(0.02)
    assert kl.stats()["calls"] == 2 and kl.stats()["hedged"] == 1


def test_a_fast_reply_never_starts_a_second_request():
    p = Timed([(0.05, "Hello.")])
    kl = make(p)
    assert kl.chat("Mira", "hi") == "Hello." and p.started == 1


def test_a_reply_that_stalls_ends_with_the_sentences_already_said():
    p = Timed([(0.05, "Toy? This hammer forged gates. "), (0.05, "And I"), (5.0, " never...")])
    kl = make(p)
    start = time.monotonic()
    pieces = []
    assert kl.chat("Mira", "Nice toy hammer.", stream=pieces.append) == "Toy? This hammer forged gates."
    assert time.monotonic() - start < 1.5
    assert kl.stats()["cut_replies"] == 1


def test_a_stall_before_any_complete_sentence_answers_offline():
    p = Timed([(0.05, "Well I"), (5.0, " think...")], [(5.0, "x")])
    kl = make(p)
    kl.character("Mira", offline="Busy.")
    assert kl.chat("Mira", "hi") == "Busy."


def test_the_deadline_holds_even_when_words_keep_coming():
    heard = []

    class Clocked(Timed):   # when the model really said each piece
        def complete(self, *args, on_text=None, **kw):
            return super().complete(*args, on_text=lambda p: (heard.append(time.monotonic() - start), on_text and on_text(p)), **kw)
    slow = [(0.05, "One. ")] + [(0.2, "more. ")] * 40
    kl = make(Clocked(slow))
    start = time.monotonic()
    reply = kl.chat("Mira", "hi", timeout=1.0)
    took = time.monotonic() - start
    assert took < 1.6, took                       # the deadline holds, whatever the machine
    # what was said in time is kept, cut at a sentence. A machine too slow to hear even the first word before the
    # deadline (a macOS CI runner did, once) has nothing to keep: the reply is then the offline one ("" here)
    if heard and heard[0] < 0.9:
        assert reply.startswith("One.") and reply.endswith("."), (reply, heard[:3])
    else:
        assert reply == "", (reply, heard[:3])


def test_the_inner_part_is_kept_when_the_stall_comes_after_it():
    p = Timed([(0.05, 'Out. \n~~~\n{"mood": "angry", "feel": -0.2}'), (5.0, " ")])
    kl = make(p)
    assert kl.chat("Mira", "hi", speaker="Ana") == "Out."
    assert kl.soul("Mira")["mood"]["word"] == "angry" and kl.opinion("Mira", "Ana") == -0.2


def test_once_the_reply_is_said_the_inner_part_gets_a_short_grace():
    p = Timed([(0.05, "Out. \n~~~\n{\"mood\": \"an"), (0.2, "g"), (0.2, "r"), (0.2, "y"), (0.2, "\"")] + [(0.2, " ")] * 30)
    kl = make(p)
    kl.brain.inner_grace = 0.5
    start = time.monotonic()
    assert kl.chat("Mira", "hi") == "Out."
    assert time.monotonic() - start < 1.5
