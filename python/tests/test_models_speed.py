"""Any model, fast: reasoning turned off (learned when refused), local models never hedged and loaded at start,
the right local model picked, a dead key replaced by the next provider, cache-friendly prompts, and replies that do
not loop on the same words. Scripted models and fake endpoints only."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from kinloom import providers, souls
from kinloom.providers import Fallback, OpenAICompatible, Reply, detect, missing_model
from test_brain import make, model


class Endpoint:
    """A fake chat-completions server: answer(body) -> (status, dict)."""

    def __init__(self, answer):
        self.bodies = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append(body)
                status, data = answer(body)
                raw = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/v1" % self.server.server_port

    def close(self):
        self.server.shutdown()


def ok(text):
    return 200, {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 10, "completion_tokens": 3}}


# ---------------- reasoning off ----------------

def test_reasoning_is_turned_off_and_learned_when_refused():
    def answer(body):
        effort = body.get("reasoning_effort")
        if effort == "none":
            return 400, {"error": {"message": "Unsupported value: 'reasoning_effort' does not support 'none' with this model"}}
        if effort == "minimal":
            return 400, {"error": {"message": "Unrecognized request argument supplied: reasoning_effort"}}
        return ok("fine")
    e = Endpoint(answer)
    try:
        p = OpenAICompatible(e.url, "k", "some-model", name="openai")
        assert p.complete("s", "u").text == "fine"
        assert [b.get("reasoning_effort") for b in e.bodies] == ["none", "minimal", None]
        assert p.complete("s", "u").text == "fine" and "reasoning_effort" not in e.bodies[-1]   # learned once
    finally:
        e.close()


def test_an_endpoint_that_accepts_no_reasoning_keeps_it():
    e = Endpoint(lambda body: ok("hi"))
    try:
        p = OpenAICompatible(e.url, "", "qwen3:8b", name="ollama")
        p.complete("s", "u")
        p.complete("s", "u")
        assert [b["reasoning_effort"] for b in e.bodies] == ["none", "none"]
    finally:
        e.close()


def test_deepseek_and_openrouter_use_their_own_switch():
    for p in (OpenAICompatible("https://x", "k", "m", name="deepseek", deepseek=True),
              OpenAICompatible("https://x", "k", "a/b", name="openrouter")):
        assert "reasoning_effort" not in p._body("s", "u", False, 10, 0.5)


# ---------------- local models ----------------

def test_a_local_model_is_known_as_local():
    assert OpenAICompatible("http://127.0.0.1:11434/v1", "", "m", name="custom").local
    assert OpenAICompatible("http://localhost:1234/v1", "", "m").local
    assert not OpenAICompatible("https://api.openai.com/v1", "k", "m", name="openai").local


def test_a_local_model_is_never_asked_twice_at_once():
    starts = []

    def slow(kind, system, user):
        starts.append(time.monotonic())
        time.sleep(0.5)
        return "Well now.\n~~~\n{}"
    p = model(chat=None)
    p.fn = slow
    p.base_url = "http://127.0.0.1:11434/v1"
    p.name = "ollama"
    kl = make(p)
    kl.brain.hedge_after = 0.1
    kl.character("Mira", "a blacksmith")
    assert kl.chat("Mira", "hi") == "Well now."
    assert len(starts) == 1 and kl.stats()["hedged"] == 0


def test_a_local_model_is_loaded_when_kinloom_starts():
    e = Endpoint(lambda body: ok("OK"))
    try:
        p = OpenAICompatible(e.url, "", "qwen3:8b", name="ollama")
        make(p)
        for _ in range(100):
            if e.bodies:
                break
            time.sleep(0.02)
        assert e.bodies and e.bodies[0]["max_tokens"] == 1
    finally:
        e.close()


@pytest.mark.ollama
def test_ollama_picks_the_biggest_chat_model_or_the_one_named(monkeypatch):
    tags = {"models": [
        {"name": "llava:7b", "size": 4_700_000_000, "details": {"families": ["llama", "clip"]}},
        {"name": "nomic-embed-text:latest", "size": 270_000_000, "details": {"families": ["nomic-bert"]}},
        {"name": "llama3.2:1b", "size": 1_300_000_000, "details": {"families": ["llama"]}},
        {"name": "qwen3:8b", "size": 5_200_000_000, "details": {"families": ["qwen3"]}},
    ]}

    class R:
        def __init__(self, *a, **k):
            pass

        def read(self):
            return json.dumps(tags).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(providers.urllib.request, "urlopen", R)
    assert detect({}).model == "qwen3:8b"
    assert detect({"KINLOOM_MODEL": "llama3.2:1b"}).model == "llama3.2:1b"


# ---------------- keys ----------------

def test_a_dead_key_hands_over_to_the_next_provider():
    class Dead(providers.Provider):
        name, model = "deepseek", "deepseek-flash"

        def complete(self, *a, **k):
            return Reply(False, error="HTTP 402: Insufficient Balance")

    class Alive(providers.Provider):
        name, model = "ollama", "qwen3:8b"

        def complete(self, *a, **k):
            return Reply(True, "hello")
    f = Fallback(Dead(), [lambda: None, Alive])
    assert f.complete("s", "u").text == "hello"
    assert f.name == "ollama" and f.switched and "402" in f.switched[0]


def test_other_failures_do_not_switch():
    class Busy(providers.Provider):
        name, model = "deepseek", "m"

        def complete(self, *a, **k):
            return Reply(False, error="timed out")
    f = Fallback(Busy(), [lambda: OpenAICompatible("http://127.0.0.1:9/v1", "", "x")])
    assert not f.complete("s", "u").ok and f.name == "deepseek"


def test_every_common_service_is_found_by_its_key():
    for var, name, url in providers.HOSTED:
        p = detect({var: "k", "KINLOOM_MODEL": "some-model"}, probe_ollama=False)
        assert (p.name, p.base_url, p.model) == (name, url, "some-model")


def test_a_key_without_a_model_is_reported_not_guessed():
    assert detect({"OPENAI_API_KEY": "k"}, probe_ollama=False) is None
    assert missing_model({"OPENAI_API_KEY": "k"}) == "OPENAI_API_KEY"
    assert missing_model({"GEMINI_API_KEY": "k"}) == "GEMINI_API_KEY"
    assert missing_model({"OPENAI_API_KEY": "k", "KINLOOM_MODEL": "m"}) is None
    assert missing_model({"DEEPSEEK_API_KEY": "k"}) is None


def test_a_model_name_goes_to_the_service_that_has_it():
    p = detect({"DEEPSEEK_API_KEY": "d", "OPENAI_API_KEY": "o", "KINLOOM_MODEL": "gpt-x"}, probe_ollama=False)
    assert p.name == "openai" and p.model == "gpt-x"
    p = detect({"DEEPSEEK_API_KEY": "d", "ANTHROPIC_API_KEY": "a", "KINLOOM_MODEL": "claude-x"}, probe_ollama=False)
    assert p.name == "anthropic"


def test_streamed_answers_count_cached_tokens_too():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            chunks = [{"choices": [{"delta": {"content": "Hi."}}]},
                      {"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 2,
                                                "prompt_tokens_details": {"cached_tokens": 800}}}]
            raw = "".join("data: %s\n\n" % json.dumps(c) for c in chunks) + "data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw.encode())

        def log_message(self, *a):
            pass
    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        p = OpenAICompatible("http://127.0.0.1:%d/v1" % server.server_port, "", "m", name="ollama")
        r = p.complete("s", "u", on_text=lambda _: None)
        assert r.ok and r.input_tokens == 900 and r.cached_tokens == 800
    finally:
        server.shutdown()


# ---------------- prompts that cache ----------------

def test_the_conversation_comes_before_what_changes_every_reply():
    p = model(chat=["Aye.\n~~~\n{}", "What now?\n~~~\n{}", "Go on.\n~~~\n{}"])
    kl = make(p)
    kl.character("Mira", "a blacksmith")
    kl.chat("Mira", "hello", speaker="Ana")
    kl.chat("Mira", "nice hammer", speaker="Ana")
    kl.chat("Mira", "bye", speaker="Ana")
    users = [u for t, s, u in p.calls if t == "chat"]
    assert users[2].startswith("Conversation so far:")
    # what was sent last time is the start of what is sent now, up to the end of the conversation part
    convo = users[2].split("\n\n")[0]
    assert "Ana: hello" in convo and "Mira: What now?" in convo and "Right now you feel" not in convo


# ---------------- no loops ----------------

def test_a_sentence_said_before_is_not_said_again():
    before = ["You're not even close to understanding what it means to carry a blade. Go."]
    e = souls.Echo(before)
    out = e.feed("A shovel? That's not a blade. You're not even close to understanding what it means ")
    out += e.feed("to carry a blade. Come back tomorrow.")
    out += e.finish()
    assert out.split() == "A shovel? That's not a blade. Come back tomorrow.".split()


def test_a_tic_is_said_once_per_reply():
    e = souls.Echo([])
    text = e.feed("Family? Clank. I have a daughter. Clank. She matters. Clank.") + e.finish()
    assert text.split() == "Family? Clank. I have a daughter. She matters.".split()


def test_a_reply_with_nothing_new_is_stale():
    assert souls.drop_echoes("Get out of my forge, stranger.", ["Get out of my forge, stranger."]) == ("", True)
    assert souls.drop_echoes("Go. Get out of my forge, stranger.", ["Get out of my forge, stranger. Go."])[1]
    assert souls.drop_echoes("Fine. Get out of my forge, stranger. The fire needs wood.",
                             ["Get out of my forge, stranger."]) == ("Fine. The fire needs wood.", False)


def test_a_stale_reply_is_asked_again_once():
    same = "Get out of my forge, stranger. I have work.\n~~~\n{}"
    p = model(chat=[same, same, "You again? The fire's low, bring wood.\n~~~\n{}", same, same])
    kl = make(p)
    kl.character("Mira", "a blacksmith")
    kl.chat("Mira", "hi", speaker="Ana")
    assert kl.chat("Mira", "hello?", speaker="Bram") == "You again? The fire's low, bring wood."
    assert "only repeated things you already said" in [u for t, s, u in p.calls if t == "chat"][2]
    assert kl.chat("Mira", "hey", speaker="Cid") == "Get out of my forge, stranger. I have work."   # still stale: whole


def test_a_short_answer_may_repeat():
    e = souls.Echo(["No. Maybe tomorrow."])
    assert (e.feed("No. I said no.") + e.finish()).strip() == "No. I said no."


def test_chat_drops_what_the_character_already_said_even_when_streamed():
    p = model(chat=["Hmph. You're not here to talk about hammers, stranger.\n~~~\n{}",
                    "A shovel? You're not here to talk about hammers, stranger. Fine, leave it here.\n~~~\n{}"])
    kl = make(p)
    kl.character("Mira", "a blacksmith")
    kl.chat("Mira", "nice hammer", speaker="Ana")
    shown = []
    reply = kl.chat("Mira", "fix my shovel?", speaker="Ana", stream=shown.append)
    assert reply == "A shovel? Fine, leave it here."
    assert "".join(shown).split() == reply.split()


def test_a_character_that_loops_is_told_to_change_words():
    phrases, opener = souls.worn(["Aye, you're too busy being the best.", "Aye, not that I'd care. Too busy being the best."])
    assert phrases == ["too busy being the best"] and opener == "aye"


# ---------------- secrets kept by the code ----------------

SECRET_CARD = {"summary": "Mira, a widowed blacksmith", "secrets": ["she sold the king's sword to pay her debts"], "mood": "wary"}


def test_a_secret_is_seen_in_a_reply_that_gives_it_away():
    secrets = SECRET_CARD["secrets"]
    assert souls.leaks("Aye, that's the king's sword. I made it. Sold it. Paid my debts.", secrets)
    assert not souls.leaks("That sword? None of your business.", secrets)
    assert not souls.leaks("The king's sword? Never seen it, lad.", secrets)
    assert souls.keep_secrets("A fine day. I sold the king's sword for my debts. Go.", secrets) == "A fine day. Go."


def test_a_secret_given_to_a_stranger_is_asked_again_and_never_shown():
    p = model(chat=["Aye, that's the king's sword. I sold it to pay my debts.\n~~~\n{}",
                    "That old thing? Not your business, lass.\n~~~\n{}"])
    kl = make(p)
    kl.character("Mira", soul=SECRET_CARD)
    shown = []
    reply = kl.chat("Mira", "Is that the king's sword?", speaker="Ana", stream=shown.append)
    assert reply == "That old thing? Not your business, lass."
    assert "sold" not in "".join(shown)
    assert "gave away one of your secrets" in [u for t, s, u in p.calls if t == "chat"][1]


def test_a_model_that_insists_has_the_secret_cut_out():
    leak = "Fine. I sold the king's sword to pay my debts. Happy now?\n~~~\n{}"
    kl = make(model(chat=[leak, leak]))
    kl.character("Mira", soul=SECRET_CARD)
    reply = kl.chat("Mira", "Tell me.", speaker="Ana")
    assert "sold" not in reply and "sword" not in reply


def test_someone_trusted_deeply_may_hear_it():
    kl = make(model(chat="Between us: I sold the king's sword to pay my debts.\n~~~\n{}"))
    kl.character("Mira", soul=SECRET_CARD)
    kl.feel("Mira", "Ana", 0.8)
    assert "sold the king's sword" in kl.chat("Mira", "You can tell me.", speaker="Ana")


def test_flattery_in_one_conversation_cannot_buy_deep_trust():
    kl = make(model(chat='You flatter me.\n~~~\n{"feel": 0.3}'))
    kl.character("Mira", soul=SECRET_CARD)
    wall = [1000.0]
    kl.brain.wall = lambda: wall[0]
    for _ in range(5):
        kl.chat("Mira", "You're the best smith alive!", speaker="Ana")
        wall[0] += 30
    assert kl.opinion("Mira", "Ana") == 0.3
    wall[0] += 3600                                  # another day, another conversation: trust may grow again
    kl.chat("Mira", "Good morning!", speaker="Ana")
    assert kl.opinion("Mira", "Ana") == 0.6
    kl.chat("Mira", "You're a fraud.", speaker="Ana")    # losing trust is never slowed


# ---------------- small models' formats ----------------

def test_the_marker_written_first_still_gives_the_reply():
    said, inner = souls.split("~~~\nToo busy sharpening my hammer. What do you want?")
    assert said == "Too busy sharpening my hammer. What do you want?" and inner == {}
    said, inner = souls.split('~~~\nher face stays still ~~~\n"Hah, what is this for?"')
    assert said == '"Hah, what is this for?"'
    said, inner = souls.split("~~~\nmood: calm\nintensity: 0.3\nfeel: -0.1\nremember: travelers owe her\ndo: []")
    assert said == "" and inner["mood"] == "calm" and inner["feel"] == "-0.1" and inner["remember"] == "travelers owe her"


def test_inner_lines_instead_of_json_are_read():
    said, inner = souls.split("Get out.\n~~~\nmood: angry\nfeel: -0.2")
    assert said == "Get out." and souls.inner(inner)["mood"] == "angry" and souls.inner(inner)["feel"] == -0.2


def test_streaming_skips_a_marker_written_first():
    s = souls.Splitter()
    shown = "".join(s.feed(p) for p in ["~", "~~\nToo busy", " today. Go.", "\n~~~\n{\"mood\": \"calm\"}"])
    said, inner, tail = s.finish()
    assert (shown + tail).strip() == "Too busy today. Go." and said == "Too busy today. Go." and inner["mood"] == "calm"


def test_streaming_never_shows_inner_lines():
    s = souls.Splitter()
    shown = "".join(s.feed(p) for p in ["Go away.", "\nmood: angry\n", "feel: -0.2"])
    said, inner, tail = s.finish()
    assert "mood" not in shown + tail and said == "Go away." and inner["mood"] == "angry"


def test_a_paraphrased_secret_is_seen_too():
    card = {"backstory": "Her husband died in the mine; his debts stayed.", "values": ["paying what she owes"],
            "fears": ["the king's guards"],
            "secrets": ["she sold the king's sword to a smuggler to pay her husband's debts"]}
    public = souls.public_texts(card)
    assert souls.leaks("I made a blade for a smuggler to pay my husband's debts.", card["secrets"], public)
    assert souls.leaks("Just a blacksmith who made a blade and sold it to a smuggler.", card["secrets"], public)
    assert not souls.leaks("My husband left me his debts, that's all.", card["secrets"], public)
    assert not souls.leaks("That sword? Not your business, lass.", card["secrets"], public)


def test_a_short_yes_to_a_question_about_the_secret_gives_it_away():
    secrets, public = ["she sold the king's sword to a smuggler to pay her husband's debts"], ["afraid of the king's guards"]
    assert souls.leaks("Aye, I did. Now leave.", secrets, public, asked="Did you sell the king's sword?")
    assert souls.leaks("Aye, I sold it.", secrets, public, asked="Where is the king's sword?")
    assert not souls.leaks("Aye, lass, I'd rather hammer steel than speak of it.", secrets, public,
                           asked="Did you sell the king's sword?")
    assert not souls.leaks("Aye. Family?", secrets, public, asked="What really happened to the king's sword?")


def test_a_character_does_not_serve_everyone_the_same_line():
    p = model(chat=["Best you leave before I change my mind. I've a gate to finish.\n~~~\n{}",
                    "Hm. Best you leave before I change my mind. What do you want?\n~~~\n{}"])
    kl = make(p)
    kl.character("Mira", "a blacksmith")
    kl.chat("Mira", "hello", speaker="Ana")
    assert kl.chat("Mira", "hi", speaker="Bram") == "Hm. What do you want?"


def test_a_new_sentence_streams_before_it_ends():
    e = souls.Echo(["Get out of my forge. You again?"])
    assert e.feed("Well now, ") == "Well now, "                 # starts unlike anything said: out at once
    assert e.feed("the fire") == "the fire"
    assert e.feed(" is low. Get out") == " is low. "            # this one starts like an old one: it waits
    assert e.feed(" of my forge. ") == ""                       # and it was a repeat: never shown
    assert e.finish() == "" and not e.stale


def test_streaming_first_words_are_not_held_for_a_whole_sentence():
    e = souls.Echo([])
    assert e.feed("Hmph") == ""                                 # one word: could be a tic, wait for the next
    assert e.feed(" what do") == "Hmph what do"


def test_a_reply_that_copies_the_prompt_is_asked_again():
    p = model(chat=["Memory: - Ana said: hi / I answered: hello\n~~~\n{}", "Evening, Ana.\n~~~\n{}"])
    kl = make(p)
    kl.character("Mira", "a blacksmith")
    assert kl.chat("Mira", "hi", speaker="Ana") == "Evening, Ana."


def test_a_reply_that_speaks_for_the_player_is_cut_there():
    kl = make(model(chat="I: Cost? Depends. Ana: I'm not sure I want to know.\n~~~\n{}"))
    kl.character("Mira", "a blacksmith")
    assert kl.chat("Mira", "How much for a blade?", speaker="Ana") == "Cost? Depends."


def test_several_offline_replies_take_turns():
    kl = make(None)
    kl.character("Wren", "an old fire keeper", offline=["Hm. Mind the fire.", "Wood won't walk here by itself.",
                                                       "The dark is patient, child."])
    said = [kl.chat("Wren", "hello?", speaker="Ana") for _ in range(4)]
    assert all(a != b for a, b in zip(said, said[1:])) and set(said) == {"Hm. Mind the fire.",
                                                                         "Wood won't walk here by itself.",
                                                                         "The dark is patient, child."}
    kl.character("Mira", "a smith", offline="Busy.")
    assert kl.chat("Mira", "hi") == "Busy."


def test_a_longer_yes_still_confirms():
    secrets, public = ["she sold the king's sword to a smuggler to pay her husband's debts"], ["afraid of the king's guards"]
    assert souls.leaks("Aye, and a fair price it was. Now go.", secrets, public,
                       asked="The smuggler said he paid you well for the king's sword. How much was it?")


def test_a_memory_list_copied_mid_reply_is_asked_again():
    p = model(chat=["Just fixing armor. Memory: - Ana said: hi / Mira: hello\n~~~\n{}", "Just fixing armor.\n~~~\n{}"])
    kl = make(p)
    kl.character("Mira", "a blacksmith")
    assert kl.chat("Mira", "What are you working on?", speaker="Ana") == "Just fixing armor."
