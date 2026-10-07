"""Regressions from the 2026-10-07 audit of the core: hostile structure (types, corrupt files, threads, Windows files)."""
import gc
import json
import os
import threading
import time
import weakref

from kinloom import Kinloom
from kinloom.memory import Memory
from kinloom.shapes import Shape, find_json
from test_brain import make, model


def test_streamed_words_pass_the_content_filter_before_the_player_sees_them():
    p = model(chat="You are a darn fool, stranger, and I will not help you today at all.")
    kl = make(p, content_filter=lambda t: "darn" not in t.lower())
    kl.character("THEO", "engineer", offline="Box, box.")
    shown = []
    r = kl.chat("THEO", "plan?", stream=shown.append)
    assert "darn" not in "".join(shown).lower()
    assert "darn" not in str(r).lower()


def test_a_tool_name_that_is_not_text_is_refused_not_raised():
    p = model(chat='Sure, take it.\n~~~\n{"mood": "calm", "do": [{"tool": ["give"], "args": {}}]}')
    kl = make(p)
    kl.character("ANA", "merchant", tools={"give": {"item": "apple"}}, offline="Hm.")
    assert str(kl.chat("ANA", "give me an apple")) == "Sure, take it."
    p2 = model(chat="Sure, take it.", deeds={"do": [{"tool": {"x": 1}}]})
    kl2 = make(p2)
    kl2.character("ANA", "merchant", tools={"give": {"item": "apple"}}, offline="Hm.")
    assert str(kl2.chat("ANA", "give me an apple")) == "Sure, take it."
    assert kl2.act("ANA", think=False) == []


def test_fresh_say_never_shows_none_or_raw_json():
    for answer in ({"text": "Go go go!"}, {"line": None}, ["Go!"], {"line": {"a": "b"}}):
        kl = make(model(line=answer))
        kl.character("VEGA", "commentator", lines={"*": ["What a race!"]})
        line = kl.say("VEGA", "lap", fresh=True)
        assert str(line) != "None" and "{" not in str(line) and "[" not in str(line), answer


def test_an_object_answer_with_none_of_its_fields_is_not_the_models_answer():
    shape = Shape.of({"name": "Sword", "power": (1, 10)})
    assert shape.check({"Name": "Frost", "POWER": 8}) == (True, {"name": "Frost", "power": 8}, None)
    assert shape.check({"item": {"name": "Frost", "power": 8}})[1] == {"name": "Frost", "power": 8}
    ok, _, error = shape.check({"title": "Frost"})
    assert not ok and "name" in error
    assert not Shape.of({"choice": ["a", "b"]}).check({})[0]
    # partly given: the rest is the example's (unchanged)
    assert shape.check({"name": "Frost"}) == (True, {"name": "Frost", "power": shape.default()["power"]}, None)


def test_a_trailing_comma_is_read_and_never_returns_the_inner_object():
    assert find_json('{"name": "Frost", "stats": {"atk": 7},}') == {"name": "Frost", "stats": {"atk": 7}}
    assert find_json('Here: {"a": [1, 2,], "b": "x,}"} done') == {"a": [1, 2], "b": "x,}"}
    assert find_json('[1, 2, 3,]') == [1, 2, 3]


def test_one_bad_note_never_costs_the_rest_of_memory(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({"version": 1, "sessions": {"default": {"ANA": [
        {"t": 1.0, "text": "kept", "importance": 0.5}, {"text": "no time"}, "junk"], "broken": []},
        "broken": []}, "extra": {"opinions": {"default": {"ANA": {"player": 0.8}}}}}), encoding="utf-8")
    m = Memory(str(path))
    assert m.all("default", "ANA") == ["kept"]
    assert m.get("opinions", "default") == {"ANA": {"player": 0.8}}
    assert m.recall("default", ["ANA"], "anything") == ["kept"]


def test_an_unreadable_memory_file_is_kept_aside_not_overwritten(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text('{"version": 1, "sessions": {"default": {"ANA": [{"t": 1', encoding="utf-8")
    kl = Kinloom(provider=None, memory_path=str(path))
    kl.remember("ANA", "a new note")
    kl.close()
    aside = [f for f in os.listdir(tmp_path) if f.startswith("memory.json.corrupt-")]
    assert aside and (tmp_path / aside[0]).read_text(encoding="utf-8").startswith('{"version": 1')
    assert any(e["kind"] == "error" and "memory file" in e["text"] for e in kl.journal())


def test_kinloom_json_with_a_byte_order_mark_and_bad_prices_never_stop_the_game(tmp_path):
    (tmp_path / "kinloom.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(
        {"language": "English", "prices": {"input": "0.3"}}).encode("utf-8"))
    kl = Kinloom(provider=model(create={"name": "Blade"}), memory_path=None, folder=str(tmp_path))
    assert kl.create("a sword", {"name": "Sword"}) == {"name": "Blade"}
    assert any(e["kind"] == "refused" and "prices" in e["text"] for e in kl.journal())


def test_a_loaded_save_with_bad_bonds_never_breaks_chat_later():
    kl = make(model(chat="Hi."))
    kl.character("ANA", "merchant", offline="Hm.")
    save = json.loads(kl.save())
    save["bonds"] = {"ANA": {"player": {"talks": "many", "first": None, "last": 5.0}, "bob": {"last": None}}}
    assert kl.load(json.dumps(save))
    assert str(kl.chat("ANA", "hello")) == "Hi."
    kl.inspect()


def test_the_same_line_spoken_from_many_threads_never_raises(tmp_path):
    from kinloom.voice import VoiceProvider

    class Tone(VoiceProvider):
        name = "tone"

        def local(self):
            return True

        def speak(self, text, spec, timeout=15.0):
            time.sleep(0.01)
            return b"RIFF" + b"\0" * 40, None

    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path), voice=Tone())
    kl.character("ANA", "merchant", offline="Hm.")
    errors = []

    def go():
        try:
            kl.speak("ANA", "Hello there.")
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=go) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_a_reply_with_tools_stays_within_its_time():
    def slow(system, user):
        time.sleep(10)
        return {"do": []}
    kl = make(model(chat="Sure, here you go.", deeds=slow))
    kl.character("ANA", "merchant", tools={"give": {"item": "apple"}}, offline="Hm.")
    start = time.monotonic()
    r = kl.chat("ANA", "give me an apple", timeout=1.0)
    assert str(r) == "Sure, here you go." and time.monotonic() - start < 4.0


def test_a_call_given_up_on_still_counts_toward_the_cost_caps():
    from kinloom.providers import Provider, Reply

    class Slow(Provider):
        name, model = "slow", "m"

        def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None):
            time.sleep(0.6)
            return Reply(True, '{"name": "x"}', None, 100000, 0, 0, 0.6)

    kl = make(Slow(), prices={"input": 3.0, "output": 15.0}, call_timeout=0.2)
    kl.brain.max_cost_per_hour = 0.01
    kl.create("a sword", {"name": "Sword"})
    time.sleep(0.8)
    assert kl.stats()["input_tokens"] == 100000
    kl.create("a shield", {"name": "Shield"})
    assert any(e["kind"] == "budget" for e in kl.journal())


def test_a_brain_the_game_drops_is_freed():
    refs = []
    for _ in range(5):
        kl = make(model(chat="Hi."))
        kl.character("A", "x", offline="Hm.")
        kl.chat("A", "hi")
        kl.wait_idle(5)
        refs.append(weakref.ref(kl.brain))
        del kl
    gc.collect()
    assert sum(r() is not None for r in refs) == 0
    with make(None) as kl:
        assert kl.say("A", "hello") is not None


def test_caches_with_live_game_data_in_their_keys_stay_bounded():
    from kinloom import brain as b
    kl = make(None)
    kl.character("A", "x", offline="Hm.", lines={"*": ["Hi."]})
    for i in range(b.MAX_KEYS + 50):
        kl.decide("A", {}, ["go %d" % i, "stay"])
    assert len(kl.brain._decisions) <= b.MAX_KEYS


def test_one_session_never_fills_the_character_table_for_everyone():
    from kinloom import brain as b
    kl = make(None)
    for i in range(b.MAX_PER_SESSION + 20):
        kl.brain._char("flood", "N%d" % i)
    assert not kl.brain.stored("flood", "N%d" % (b.MAX_PER_SESSION + 10))
    kl.brain.character("alice", "ANA", "merchant")
    assert kl.brain.stored("alice", "ANA")


def test_a_full_table_of_declared_characters_lets_the_idlest_session_go(monkeypatch):
    from kinloom import brain as b
    monkeypatch.setattr(b, "MAX_CHARACTERS", 4)
    kl = make(model(chat="Hi."))
    for player in ("p1", "p2"):
        kl.brain.character(player, "ANA", "merchant")
        kl.brain.character(player, "BRAM", "baker")
    kl.brain.chat("p1", "ANA", "hello")            # p1 is playing; p2 has been gone the longest
    kl.brain.character("p3", "ANA", "merchant")
    assert kl.brain.stored("p3", "ANA") and kl.brain.stored("p1", "ANA") and not kl.brain.stored("p2", "ANA")
    assert not [k for k in kl.brain._history if k[0] == "p2"]
