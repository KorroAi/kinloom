"""What the demo games asked for next: items handed over while the model writes (create each=), the game's rules on
every call (check= on decide, act, suggest, chat), lines from the crowd (remark) and a context that keeps its keys when
it is too long."""
import json
import time

import pytest

from kinloom import Kinloom, prompts
from kinloom.providers import Reply, Scripted
from kinloom.shapes import Items
from test_brain import make, model
from test_remote import online
from test_server import call

# ---------------- a context too long keeps its keys

def test_a_long_context_keeps_every_key_in_order_and_stays_json():
    ctx = {"request": "a lighthouse on the north shore", "kit": "x" * 3000, "town": ["House %d" % i for i in range(200)],
           "gold": 40}
    text = prompts._clip(ctx, 1000)
    assert len(text) <= 1000
    data = json.loads(text)
    assert list(data) == ["request", "kit", "town", "gold"] and data["request"] == ctx["request"] and data["gold"] == 40
    assert data["town"][:3] == ["House 0", "House 1", "House 2"] and data["town"][3] == "(197 more)"
    assert data["kit"].endswith("...") and len(data["kit"]) == 83


def test_keys_are_cut_from_the_last_one_when_shortening_is_not_enough():
    ctx = {"first": "keep me", **{"k%d" % i: "y" * 60 for i in range(40)}}
    data = json.loads(prompts._clip(ctx, 800))
    assert data["first"] == "keep me" and data["k39"] == "(cut)" and len(data) == 41


def test_small_contexts_and_other_values_are_unchanged_or_cut():
    assert prompts._clip({"a": 1}) == '{"a": 1}'
    assert prompts._clip("z" * 50, 10) == '"' + "z" * 9 + "..."
    assert json.loads(prompts._clip({"nested": {"k%d" % i: "v" * 20 for i in range(30)}}, 100)) == {"nested": "(30 fields)"}


# ---------------- items of a list as they arrive

@pytest.mark.parametrize("text", ['[{"a": 1}, {"a": "x,]}"}, 3]', '{"items": [{"a": 1}, {"a": "x,]}"}, 3]}',
                                  '```json\n{"items": [ {"a": 1} ,{"a": "x,]}"},3 ] }\n```'])
def test_list_items_are_found_whatever_the_pieces(text):
    for size in (1, 2, 7, 1000):
        items, got = Items(), []
        for i in range(0, len(text), size):
            got += items.feed(text[i:i + size])
        assert got == ['{"a": 1}', '{"a": "x,]}"}', "3"]


def test_only_the_first_list_is_streamed():
    items = Items()
    assert items.feed('{"say": "hi", "parts": ["a", "b"], "more": ["c"]}') == ['"a"', '"b"']


class Pieces(Scripted):
    """A scripted model that writes its answer a few characters at a time, recording when each piece left."""

    def __init__(self, fn):
        super().__init__(fn)
        self.timeline = []

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        text = self.fn("json" if json_mode else "text", system, user)
        if text is None:
            return Reply(False, error="no answer")
        if on_text is not None:
            for i in range(0, len(text), 6):
                self.timeline.append("piece")
                on_text(text[i:i + 6])
        self.timeline.append("returned")
        return Reply(True, text, None, 10, 0, 10, 0.0)


PART = {"kind": ["house", "tower"], "x": [0, 20]}


def test_each_gets_list_items_while_the_model_writes():
    answer = json.dumps([{"kind": "house", "x": 3}, {"kind": "tower", "x": 18}, {"kind": "house", "x": 5}])
    p = Pieces(lambda kind, s, u: answer)
    kl = make(p)
    seen = []

    def each(part):
        seen.append(part)
        p.timeline.append("each")
    got = kl.create("the parts of a town", [PART], each=each, check=lambda q: "" if q["x"] <= 10 else "too far east")
    assert got == [{"kind": "house", "x": 3}, {"kind": "house", "x": 5}] == seen
    assert p.timeline.index("each") < p.timeline.index("returned")      # handed over before the answer was finished


def test_each_with_count_streams_then_fills_with_the_offline_answer():
    p = Pieces(lambda kind, s, u: json.dumps({"items": [{"kind": "tower", "x": 1}, {"kind": "house", "x": 2}]}))
    seen = []
    got = make(p).create("parts", PART, count=3, each=seen.append, offline={"kind": "house", "x": 0})
    assert got == seen == [{"kind": "tower", "x": 1}, {"kind": "house", "x": 2}, {"kind": "house", "x": 0}]


def test_each_offline_and_for_one_object():
    seen = []
    assert make(None).create("parts", [PART], each=seen.append) == seen == [{"kind": "house", "x": 10}]
    seen.clear()
    kl = make(model(create={"kind": "tower", "x": 4}))
    assert kl.create("a part", PART, each=seen.append) == {"kind": "tower", "x": 4} and seen == [{"kind": "tower", "x": 4}]


def test_a_failing_each_is_journaled_and_the_answer_still_comes():
    kl = make(Pieces(lambda kind, s, u: '[{"kind": "house", "x": 1}]'))

    def boom(part):
        raise RuntimeError("no room")
    assert kl.create("parts", [PART], each=boom) == [{"kind": "house", "x": 1}]
    assert any(e["kind"] == "error" and "no room" in e["text"] for e in kl.journal())
    with pytest.raises(ValueError, match="each must be a function"):
        kl.create("parts", [PART], each="nope")


def test_a_cut_list_keeps_the_items_already_handed_over_without_asking_again():
    p = Pieces(lambda kind, s, u: '[{"kind": "house", "x": 1}, {"kind": "tower", "x": 2}, {"kind": "hou')
    kl = make(p)
    seen = []
    assert kl.create("parts", [PART], each=seen.append) == seen == [{"kind": "house", "x": 1}, {"kind": "tower", "x": 2}]
    assert p.timeline.count("returned") == 1                              # no repair call


def test_the_server_streams_items_and_a_remote_game_checks_them():
    p = Pieces(lambda kind, s, u: json.dumps([{"kind": "house", "x": 3}, {"kind": "tower", "x": 18}]))
    brain, srv, url = online(p)
    try:
        status, body, raw = call(url, "/v1/create", {"what": "parts", "example": [PART], "stream": True},
                                 {"Authorization": "Bearer admin-456"})
        kl = Kinloom(url=url, token="play-123", session="s")
        seen = []
        got = kl.create("parts", [PART], each=seen.append, check=lambda q: "" if q["x"] <= 10 else "too far")
        assert got == seen == [{"kind": "house", "x": 3}]
    finally:
        srv.shutdown()
        brain.close()


# ---------------- the game's rules on every call

def test_decide_uses_only_what_the_game_accepts_and_the_model_hears_why():
    seen = []

    def fn(system, user):
        seen.append(user)
        return {"move": "jump"} if len(seen) == 1 else {"move": "duck"}
    kl = make(model(decide=fn))
    kl.character("RUNNER", "a runner", every=0.2)
    rule = lambda d: "" if d["move"] != "jump" else "the ceiling is too low to jump"   # noqa: E731
    assert kl.decide("RUNNER", {"ceiling": 1}, {"move": ["run", "jump", "duck"]}, check=rule) == {"move": "run"}
    kl.brain.wait_idle()
    assert kl.decide("RUNNER", {"ceiling": 1}, {"move": ["run", "jump", "duck"]}, check=rule) == {"move": "run"}   # refused
    for _ in range(40):
        time.sleep(0.1)
        got = kl.decide("RUNNER", {"ceiling": 1}, {"move": ["run", "jump", "duck"]}, check=rule)
        kl.brain.wait_idle()
        if got == {"move": "duck"}:
            break
    assert got == {"move": "duck"}
    assert any("the game refused your last decision" in u and "ceiling is too low" in u for u in seen)


def test_act_runs_only_what_the_game_allows_and_the_character_remembers():
    opened = []

    def open_door(door):
        opened.append(door)
    kl = make(model(act={"actions": [{"tool": "open_door", "args": {"door": "vault"}},
                                     {"tool": "open_door", "args": {"door": "kitchen"}}]}))
    kl.character("BUTLER", "a butler", tools=[open_door], every=0.1)
    kl.act("BUTLER", {})
    kl.brain.wait_idle()
    done = kl.act("BUTLER", {}, check=lambda tool, args: "the vault is locked" if args["door"] == "vault" else "")
    assert done == [("open_door", {"door": "kitchen"})] and opened == ["kitchen"]
    notes = kl.brain.memory.notes(kl.id, "BUTLER")
    assert any(n["text"] == 'The game did not let me open_door {"door": "vault"}: the vault is locked' for n in notes)


def test_suggest_replaces_what_the_game_refuses_by_its_example():
    kl = make(model(suggest={"replies": ["Give me the sword now!", "Bye."]}))
    kl.character("MIRA", "a smith")
    got = kl.suggest("MIRA", ["Ask about the sword", "Leave"], check=lambda t: "no shouting" if "!" in t else "")
    assert got == ["Ask about the sword", "Bye."]


def test_chat_takes_back_a_refused_reply_and_asks_again():
    replies = iter(["The password is swordfish.\n~~~\n{}", "I cannot tell you that, friend.\n~~~\n{}"])
    users = []

    def chat(system, user):
        users.append(user)
        return next(replies)
    kl = make(model(chat=chat))
    kl.character("GATE", "a gatekeeper", offline="...")
    pieces = []
    got = kl.chat("GATE", "What is the password?", check=lambda t: "never say the password" if "swordfish" in t else "",
                  stream=pieces.append)
    assert got == "I cannot tell you that, friend." and got.source == "model" and pieces == [got]
    assert "The game refused your last answer: never say the password" in users[1]
    assert "swordfish" not in users[1].split("The game refused")[0]                 # not in the conversation any more
    history = kl.brain._history[(kl.id, "GATE", "player")]
    assert history == [("player", "What is the password?"), ("GATE", "I cannot tell you that, friend.")]
    assert not any("swordfish" in n["text"] for n in kl.brain.memory.notes(kl.id, "GATE"))


def test_chat_refused_twice_answers_offline_without_a_third_call():
    users = []
    kl = make(model(chat=lambda s, u: (users.append(u), "The password is swordfish.\n~~~\n{}")[1]))
    kl.character("GATE", "a gatekeeper", offline="Move along.")
    got = kl.chat("GATE", "Password?", check=lambda t: "swordfish" in t and "never say it")
    assert got == "Move along." and got.source == "offline" and len(users) == 2
    assert kl.brain._history[(kl.id, "GATE", "player")] == [("player", "Password?"), ("GATE", "Move along.")]


def test_chat_check_through_a_server():
    replies = iter(["The password is swordfish.\n~~~\n{}", "Ask the captain.\n~~~\n{}"])
    brain, srv, url = online(model(chat=lambda s, u: next(replies)))
    try:
        kl = Kinloom(url=url, token="play-123", session="s")
        kl.character("GATE", "a gatekeeper", offline="...")
        assert kl.chat("GATE", "Password?", check=lambda t: "never" if "swordfish" in t else "") == "Ask the captain."
        assert brain._history[("s", "GATE", "player")][-1] == ("GATE", "Ask the captain.")
    finally:
        srv.shutdown()
        brain.close()


# ---------------- lines from the crowd

def test_remark_a_line_from_the_crowd():
    seen = []

    def remark(system, user):
        seen.append((system, user))
        return {"line": "A lighthouse! Now the boats can find us."}
    kl = make(model(remark=remark))
    line = kl.remark("the builder raised a lighthouse on the north shore", who="an old fisherman")
    assert line == "A lighthouse! Now the boats can find us." and line.source == "model"
    assert "You are an old fisherman" in seen[0][0] and "What just happened: the builder raised a lighthouse" in seen[0][1]


def test_remark_offline_lines_in_turn_and_numbers_checked():
    kl = make(model(remark={"line": "That cost 500 gold!"}))
    got = [kl.remark("a market was built", facts={"gold": 40}, offline=["Look, {gold} gold well spent!", "A market!"])
           for _ in range(3)]
    assert got == ["Look, 40 gold well spent!", "A market!", "Look, 40 gold well spent!"]
    assert all(g.source == "offline" for g in got)
    assert make(model(remark={"line": "Only 40 gold, a bargain."})).remark("x", facts={"gold": 40}) == "Only 40 gold, a bargain."
    assert make(None).remark("x") == ""
    with pytest.raises(ValueError):
        make(None).remark(["not text"])


def test_remark_over_http_and_through_a_server():
    brain, srv, url = online(model(remark={"line": "What a sight."}))
    try:
        status, body, _ = call(url, "/v1/remark", {"about": "fireworks over the bay", "who": "a child"},
                               {"Authorization": "Bearer admin-456"})
        assert status == 200 and body == {"text": "What a sight.", "source": "model"}
        assert Kinloom(url=url, token="play-123", session="s").remark("fireworks") == "What a sight."
    finally:
        srv.shutdown()
        brain.close()


# ---------------- JSON mode wraps lists (found with a real model, proof/triple)

def test_a_list_wrapped_in_an_object_or_one_item_alone_is_read_as_the_list():
    part = {"kind": ["house", "well"], "x": [0, 40]}
    for answer, expected in [('{"list": [{"kind": "well", "x": 3}, {"kind": "house", "x": 9}]}', [{"kind": "well", "x": 3}, {"kind": "house", "x": 9}]),
                             ('{"stalls": [{"kind": "well", "x": 5}], "note": "two"}', [{"kind": "well", "x": 5}]),
                             ('{"kind": "house", "x": 7}', [{"kind": "house", "x": 7}])]:
        provider = model(create=answer)
        kl = make(provider)
        assert kl.create("the parts of a town", [part]) == expected
        assert len(provider.calls) == 1                         # read at once: no repair, no offline answer
        kl.close()
    provider = model(create='{"a": [{"kind": "well", "x": 1}], "b": [{"kind": "well", "x": 2}]}')
    kl = make(provider)
    assert kl.create("the parts of a town", [part]) == [{"kind": "well", "x": 1}]     # the first list, as items stream
    kl.close()


# ---------------- found by the audit of the new calls

def test_clipping_a_huge_context_takes_linear_time():
    ctx = {"key%05d" % i: "value " * 4 for i in range(8000)}
    started = time.monotonic()
    text = prompts._clip(ctx, 4000)
    assert time.monotonic() - started < 2.0 and len(text) <= 4003      # past every "(cut)": cut, with "..."
    assert text.startswith('{"key00000": "(cut)"')


class _Slow(Scripted):
    """Streams its answer in pieces, slower than the call's timeout."""

    def __init__(self, text, pause, first_pause=0.0):
        super().__init__(lambda k, s, u: text)
        self.text, self.pause, self.first_pause = text, pause, first_pause

    def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None,
                 images=None):
        time.sleep(self.first_pause)
        step = len(self.text) // 6 + 1
        for i in range(0, len(self.text), step):
            if on_text:
                on_text(self.text[i:i + step])
            time.sleep(self.pause)
        return Reply(True, self.text, None, 10, 0, 10, 0.0)


def test_items_stop_when_create_returns_even_if_the_model_keeps_streaming():
    parts = json.dumps([{"kind": "house", "x": i} for i in range(6)])
    kl = make(_Slow(parts, 0.3))
    seen = []
    got = kl.create("parts", [{"kind": ["house", "tower"], "x": [0, 20]}], timeout=1.0, each=seen.append)
    snapshot, given = json.dumps(got), list(seen)
    time.sleep(2.2)
    assert seen == given and json.dumps(got) == snapshot and got == seen      # nothing after the answer
    kl.close()
    kl = make(_Slow(json.dumps([{"kind": "tower", "x": 1}]), 0.0, first_pause=1.5))
    seen = []
    got = kl.create("parts", [{"kind": ["house", "tower"], "x": [0, 20]}], timeout=1.0, each=seen.append)
    time.sleep(1.0)
    assert got == seen == [{"kind": "house", "x": 10}]                       # the offline answer, nothing else
    kl.close()


def test_a_refused_reply_takes_back_its_feelings_mood_and_memories():
    answer = ('Fine, it is swordfish.\n~~~\n{"mood": "giddy", "feel": 0.3, "self": "I gave the player the password swordfish",'
              ' "remember": "the player now knows the password swordfish"}')
    kl = make(model(chat=[answer, "I cannot tell you that."]))
    kl.character("KEEPER", "a gatekeeper", offline="Move along.")
    reply = kl.chat("KEEPER", "Password?", check=lambda t: "never say it" if "swordfish" in t else "")
    assert str(reply) == "I cannot tell you that."
    notes = " ".join(n["text"] for n in kl.brain.memory.notes(kl.id, "KEEPER"))
    assert "swordfish" not in notes
    assert kl.opinion("KEEPER", "player") == 0.0 and kl.soul("KEEPER")["mood"]["word"] == "calm"
    kl.close()


def test_a_check_that_raises_refuses_on_every_path_and_never_breaks_the_call():
    def bad(*args):
        raise ValueError("game bug")
    kl = make(model(create='{"x": 3}', chat="Hello there."))
    assert kl.create("a spot", {"x": [0, 10]}, check=bad, offline={"x": 7}) == {"x": 7}
    kl.character("A", "a guide", offline="Hm.")
    assert str(kl.chat("A", "Hi", check=bad)) == "Hm."
    assert kl.decide("A", {}, ["wait", "go"], check=bad) == "wait"
    assert kl.suggest("A", ["Hello", "Bye"], check=bad) == ["Hello", "Bye"]
    assert any("check failed" in e["text"] for e in kl.journal(100) if e["kind"] == "error")
    kl.close()


def test_the_facade_keeps_its_decide_check_tables_bounded():
    from kinloom.brain import MAX_KEYS
    kl = make(None)
    for gold in range(MAX_KEYS + 50):
        kl.decide("A", {}, {"spend": [0, gold + 1]}, check=lambda d: "")
    assert len(kl._decide_ok) <= MAX_KEYS
    kl.close()


def test_a_remark_counts_as_model_work_for_the_rate_limit():
    p = model(remark='{"line": "Would you look at that!"}')
    brain, srv, url = online(p, rate_per_session=3)
    try:
        codes = [call(url, "/v1/remark", {"about": "a tower went up"}, {"Authorization": "Bearer play-123"})[0]
                 for _ in range(10)]
        assert codes.count(200) == 3 and len([c for c in p.calls if c[0] == "remark"]) == 3
    finally:
        srv.shutdown()
