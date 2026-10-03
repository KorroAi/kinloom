"""Ship anywhere: the model is an API key or the developer's coding agent (its subscription); pictures the model looks
at; the game's tools declared once; prepare() for loading screens. Coding agents are a stand-in script here."""
import base64
import json
import os
import sys
import threading
import time

import pytest

from kinloom import Kinloom, config, media
from kinloom.brain import Brain
from kinloom.harness import Harness
from kinloom.providers import Anthropic, OpenAICompatible, Reply, detect
from test_brain import make, model
from test_server import call, server  # noqa: F401  (fixture)
from test_souls import reply

FAKE = [sys.executable, os.path.join(os.path.dirname(__file__), "fake_agent.py")]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """The stand-in agent: set its answer, read what it received."""
    log = tmp_path / "agent.jsonl"
    monkeypatch.setenv("FAKE_AGENT_LOG", str(log))

    class A:
        def answer(self, text):
            monkeypatch.setenv("FAKE_AGENT_ANSWER", text)

        def env(self, key, value):
            monkeypatch.setenv(key, value)

        def calls(self):
            return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return A()


# ---------------- pictures ----------------

def test_a_picture_is_read_from_bytes_a_file_base64_or_a_data_uri(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(PNG)
    b64 = base64.b64encode(PNG).decode()
    for value in (PNG, bytearray(PNG), str(path), b64, "data:image/png;base64," + b64):
        p = media.picture(value)
        assert p.mime == "image/png" and p.data == PNG
    assert media.picture(JPEG).mime == "image/jpeg"
    assert media.picture(b"GIF89a" + b"\x00" * 10).mime == "image/gif"
    assert media.picture(b"RIFF\x00\x00\x00\x00WEBPVP8 ").mime == "image/webp"
    assert media.picture(None) is None and media.picture("") is None


def test_what_is_not_a_picture_is_refused_with_a_reason(tmp_path):
    for bad in (b"hello", "not base64 !!", str(tmp_path / "missing.png"), 42, base64.b64encode(b"%PDF-1.4").decode()):
        with pytest.raises(ValueError):
            media.picture(bad)
    with pytest.raises(ValueError, match="larger"):
        media.picture(PNG + b"\x00" * media.MAX_IMAGE)


def test_chat_shows_the_picture_to_the_model():
    p = model(chat=lambda s, u: reply("A fine blade." if "[image: image/png" in u else "I see nothing."))
    kl = make(p)
    kl.character("Mira", "a smith")
    said = kl.chat("Mira", "What do you think of this sword?", image=PNG)
    assert said == "A fine blade." and said.source == "model"
    user = [c for c in p.calls if c[0] == "chat"][-1][2]
    assert "A picture comes with this moment" in user


def test_a_picture_skips_the_prepared_greeting_the_model_wrote_without_it():
    p = model(greet=reply("Welcome!"), chat=lambda s, u: reply("That map is old." if "[image:" in u else "Hm."))
    kl = make(p)
    kl.character("Mira", "a smith", soul="a gruff smith")
    kl.wait_idle(5)
    assert kl.chat("Mira", "", image=PNG) == "That map is old."


def test_create_looks_at_the_picture_and_still_answers_the_example_shape():
    seen = []

    def create(s, u):
        seen.append(u)
        return {"mood": "stormy", "danger": 0.8}
    kl = make(model(create=create))
    out = kl.create("what this screenshot shows", {"mood": "calm", "danger": 0.1}, image=PNG)
    assert out == {"mood": "stormy", "danger": 0.8}
    assert "[image: image/png" in seen[0] and "A picture comes with this request" in seen[0]
    kl.create("three items seen here", [{"name": "torch"}], count=3, image=PNG)
    assert "[image: image/png" in seen[-1]


def test_a_bad_picture_is_told_and_the_call_goes_on():
    p = model(chat=reply("Hello."))
    kl = make(p)
    kl.character("Mira", "a smith")
    assert kl.chat("Mira", "hi", image=b"not an image") == "Hello."
    assert any(e["kind"] == "refused" and "image" in e["text"] for e in kl.journal())
    assert "[image:" not in [c for c in p.calls if c[0] == "chat"][-1][2]


def test_offline_a_picture_changes_nothing():
    kl = make(None)
    kl.character("Mira", "a smith", offline="Busy.")
    assert kl.chat("Mira", "look", image=PNG) == "Busy."
    assert kl.create("x", {"a": 1}, image=PNG) == {"a": 1}


def test_instant_create_does_not_use_the_picture_and_says_so():
    kl = make(model(create={"items": [{"a": 2}] * 5}))
    kl.create("loot", {"a": 1}, instant=True, image=PNG)
    assert any("instant" in e["text"] for e in kl.journal() if e["kind"] == "refused")


def test_a_game_provider_written_before_pictures_still_works_and_it_is_told_once():
    class Old:
        name, model, base_url = "old", "old", ""

        def complete(self, system, user, json_mode=False, max_tokens=400, temperature=0.8, timeout=15.0, on_text=None):
            if on_text:
                on_text("Fine.")
            return Reply(True, "Fine.")
    kl = make(Old())
    kl.character("Mira", "a smith")
    assert kl.chat("Mira", "look", image=PNG) == "Fine."
    assert kl.chat("Mira", "and this", image=PNG) == "Fine."
    told = [e for e in kl.journal() if "cannot see pictures" in e["text"]]
    assert len(told) == 1


def test_openai_compatible_sends_the_picture_as_an_image_part(http):
    from conftest import openai_reply
    http.answer(200, openai_reply("A sword."))
    p = OpenAICompatible(http.url, "k", "m")
    r = p.complete("Kinloom task: chat", "look", images=[media.picture(PNG)])
    assert r.ok and not r.blind
    content = http.requests[0]["body"]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_a_model_that_cannot_see_is_asked_again_without_the_picture_and_learns_it(http):
    from conftest import openai_reply
    http.answer(400, {"error": {"message": "unknown variant `image_url`, expected `text`"}})
    http.answer(200, openai_reply("Words only."))
    p = OpenAICompatible(http.url, "k", "m")
    r = p.complete("Kinloom task: chat", "look", images=[media.picture(PNG)])
    assert r.ok and r.text == "Words only." and r.blind
    assert isinstance(http.requests[1]["body"]["messages"][1]["content"], str)
    r = p.complete("Kinloom task: chat", "again", images=[media.picture(PNG)])
    assert r.blind and len(http.requests) == 3 and isinstance(http.requests[2]["body"]["messages"][1]["content"], str)


def test_anthropic_sends_the_picture_as_an_image_block(http):
    http.answer(200, {"content": [{"type": "text", "text": "A sword."}], "usage": {"input_tokens": 5, "output_tokens": 2}})
    p = Anthropic("k", "m", http.url)
    assert p.complete("Kinloom task: chat", "look", images=[media.picture(JPEG)]).ok
    content = http.requests[0]["body"]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    assert content[1] == {"type": "text", "text": "look"}


def test_pictures_over_http(server):  # noqa: F811
    brain, url = server(model(chat=lambda s, u: reply("Seen." if "[image:" in u else "Blind."),
                              create=lambda s, u: {"what": "map" if "[image:" in u else "?"}))
    call(url, "/v1/character", {"name": "Mira", "personality": "a smith"})
    b64 = base64.b64encode(PNG).decode()
    assert call(url, "/v1/chat", {"name": "Mira", "message": "look", "image": b64})[1]["text"] == "Seen."
    assert call(url, "/v1/create", {"what": "x", "example": {"what": "?"}, "image": "data:image/png;base64," + b64})[1] == {"value": {"what": "map"}}
    assert call(url, "/v1/chat", {"name": "Mira", "message": "look", "image": 5})[0] == 400
    big = "A" * (2 * 1024 * 1024)            # bigger than a plain request, smaller than a picture request may be
    status, body, _ = call(url, "/v1/chat", {"name": "Mira", "message": "look", "image": big})
    assert status == 200                     # not a picture: told in the journal, the reply still comes


def test_the_online_mode_sends_the_picture(server):  # noqa: F811
    brain, url = server(model(chat=lambda s, u: reply("Seen." if "[image:" in u else "Blind.")))
    kl = Kinloom(url=url)
    kl.character("Mira", "a smith")
    assert kl.chat("Mira", "look", image=PNG) == "Seen."
    kl.close()


# ---------------- the game's tools ----------------

def test_tools_declared_once_are_used_by_name():
    opened = []

    def open_door(door: str = "north"):
        """Opens a door of the keep."""
        opened.append(door)
    p = model(act={"actions": [{"tool": "open_door", "args": {"door": "east"}}, {"tool": "give", "args": {"item": "key"}}]})
    kl = make(p)
    assert kl.tools({"give": {"item": "sword"}}) == ["give"]
    kl.tools([open_door, {"give": {"item": "sword"}}])
    kl.character("Guard", "a guard", tools=["open_door"])
    assert kl.act("Guard") == []
    kl.wait_idle(5)
    assert kl.act("Guard") == [("open_door", {"door": "east"})]          # give is not one of the guard's tools
    assert opened == ["east"]
    assert kl.soul("Guard")["tools"] == ["open_door"]
    assert sorted(kl.tools()) == ["give", "open_door"]


def test_all_takes_every_game_tool_even_those_declared_later():
    kl = make(model(act={"actions": [{"tool": "heal", "args": {"amount": 5}}]}))
    kl.character("Priest", "a priest", tools="all")
    assert kl.soul("Priest")["tools"] == []
    kl.tools({"heal": {"amount": 1}, "bless": {}})
    assert kl.soul("Priest")["tools"] == ["bless", "heal"]
    kl.act("Priest")
    kl.wait_idle(5)
    assert kl.act("Priest") == [("heal", {"amount": 5})]


def test_own_tools_and_game_tools_mix_and_trust_applies_to_game_tools():
    kl = make(None)
    kl.tools({"give": {"item": "sword"}})
    kl.character("Mira", "a smith", tools=["give", {"repair": {"what": "blade"}}], trust={"give": 0.5})
    c = kl.brain._characters[("default", "Mira")]
    assert sorted(c.tools) == ["give", "repair"] and c.trust == {"give": 0.5}


def test_a_tool_name_the_game_never_declared_is_told():
    kl = make(None)
    kl.tools({"give": {"item": "sword"}})
    kl.character("Mira", "a smith", tools=["giv"])
    assert any("giv not declared" in e["text"] for e in kl.journal())


def test_game_tools_from_kinloom_json(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({
        "tools": {"open_door": {"door": "north"}},
        "characters": {"Guard": {"personality": "a guard", "tools": ["open_door"]}}}), encoding="utf-8")
    kl = make(model(act={"actions": [{"tool": "open_door", "args": {"door": "west"}}]}), folder=str(tmp_path))
    assert kl.tools() == ["open_door"]
    assert kl.soul("Guard")["tools"] == ["open_door"]
    kl.act("Guard")
    kl.wait_idle(5)
    assert kl.act("Guard") == [("open_door", {"door": "west"})]


def test_bad_tools_are_refused():
    kl = make(None)
    with pytest.raises(ValueError):
        kl.tools(42)


def test_game_tools_over_http_and_through_the_online_mode(server):  # noqa: F811
    brain, url = server(model(act={"actions": [{"tool": "open_door", "args": {"door": "east"}}]}))
    assert call(url, "/v1/tools", {"tools": {"open_door": {"door": "north"}}})[1] == {"tools": ["open_door"]}
    assert call(url, "/v1/tools", {})[1] == {"tools": ["open_door"]}
    assert call(url, "/v1/tools", {"tools": ["x"]})[0] == 400
    call(url, "/v1/character", {"name": "Guard", "personality": "a guard", "tools": ["open_door"]})
    assert brain.soul("default", "Guard")["tools"] == ["open_door"]

    opened = []

    def open_door(door: str = "north"):
        opened.append(door)
    kl = Kinloom(url=url, session="p2")
    kl.tools([open_door])
    kl.character("Guard", "a guard", tools=["open_door"])
    kl.brain.wait_idle(5)
    deadline = time.time() + 5
    while time.time() < deadline and brain.soul("p2", "Guard")["tools"] != ["open_door"]:
        time.sleep(0.05)
    assert brain.soul("p2", "Guard")["tools"] == ["open_door"]
    kl.act("Guard")
    brain.wait_idle(5)
    assert kl.act("Guard") == [("open_door", {"door": "east"})] and opened == ["east"]
    kl.close()


# ---------------- prepare ----------------

def test_prepare_waits_for_what_is_written_ahead():
    gate = threading.Event()

    def soul(s, u):
        gate.wait(5)
        return {"summary": "A gruff smith.", "wants": "quiet"}
    kl = make(model(soul=soul, greet=reply("Hm.")))
    kl.character("Mira", "a smith", soul="a gruff smith")
    assert kl.prepare(0.05)["ready"] is False
    gate.set()
    out = kl.prepare(5)
    assert out == {"ready": True, "waiting": 0, "online": True}


def test_prepare_offline_is_ready_at_once_and_over_http(server):  # noqa: F811
    assert make(None).prepare() == {"ready": True, "waiting": 0, "online": False}
    brain, url = server(None)
    assert call(url, "/v1/prepare", {"timeout": 1})[1] == {"ready": True, "waiting": 0, "online": False}
    assert call(url, "/v1/prepare", {"timeout": "x"})[0] == 400


# ---------------- coding agents ----------------

def test_claude_code_answers_through_stream_json_with_the_picture(agent):
    agent.answer("Hello, traveller.")
    h = Harness("claude-code", "haiku", exe=FAKE, pool=0)
    pieces = []
    r = h.complete("Kinloom task: chat\nYou are Mira.", "Ana says: hi", on_text=pieces.append, images=[media.picture(PNG)],
                   timeout=30)
    h.close()
    assert r.ok and r.text == "Hello, traveller." and "".join(pieces) == "Hello, traveller." and len(pieces) > 1
    assert r.input_tokens == 120 and r.cached_tokens == 20 and r.output_tokens == 7 and not r.blind
    call_ = agent.calls()[0]
    assert call_["kind"] == "claude" and call_["images"] == ["image/png"]
    assert call_["prompt"].startswith("<system>\nKinloom task: chat\nYou are Mira.\n</system>\n\n")   # marked as such
    assert call_["prompt"].endswith("Ana says: hi")
    argv = call_["argv"]
    for flag in ("-p", "--safe-mode", "--no-session-persistence", "--include-partial-messages"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--model") + 1] == "haiku"
    assert json.loads(argv[argv.index("--settings") + 1]) == {"alwaysThinkingEnabled": False}     # thinking off: speed
    assert "Ana says" not in " ".join(argv)                  # player text never on a command line


def test_claude_code_processes_are_started_ahead_and_used_once(agent):
    agent.answer("Hi.")
    h = Harness("claude-code", exe=FAKE, pool=2)
    assert h.starts_ahead
    h.warm()
    deadline = time.time() + 20
    while time.time() < deadline and len(h._pool) < 2:
        time.sleep(0.05)
    assert len(h._pool) == 2
    first = h._pool[0][0]
    assert h.complete("Kinloom task: chat", "a", timeout=30).ok
    assert h.complete("Kinloom task: chat", "b", timeout=30).ok
    assert first.wait(10) == 0                       # it answered one call and ended
    assert [c["prompt"].endswith(x) for c, x in zip(agent.calls(), ("a", "b"))] == [True, True]
    pool = [p for p, _ in h._pool]
    h.close()
    for p in pool:
        p.wait(10)
        assert p.poll() is not None                  # closing stops the processes started ahead


def test_codex_gemini_opencode_and_any_command(agent):
    agent.answer("Fine words.")
    for kind, exe in (("codex", FAKE), ("gemini-cli", FAKE), ("opencode", FAKE)):
        h = Harness(kind, "some-model", exe=exe)
        r = h.complete("Kinloom task: line\nWrite a line.", "Player text: hi & bye | %PATH%", json_mode=False, timeout=30,
                       images=[media.picture(PNG)])
        h.close()
        assert r.ok and r.text == "Fine words.", (kind, r.error)
        assert r.blind == (kind == "gemini-cli")
    calls = agent.calls()
    assert [c["kind"] for c in calls] == ["codex", "gemini", "opencode"]
    assert calls[0]["images"] == [True] and "-m" in calls[0]["argv"] and "read-only" in calls[0]["argv"]
    assert "plan" in calls[1]["argv"] and calls[2]["files"] == 2
    for c in calls:
        assert "Player text: hi & bye | %PATH%" in c["prompt"]
        assert "Player text" not in " ".join(c["argv"])
        assert os.path.basename(c["cwd"]).startswith("kinloom-agent-")    # an empty folder, not the game's
    h = Harness("command", command=["mytool", "--fast"], exe=FAKE)
    r = h.complete("Kinloom task: create", '{"a": 1}', json_mode=True, timeout=30)
    assert r.ok and agent.calls()[-1]["kind"] == "plain" and "JSON object only" in agent.calls()[-1]["prompt"]
    assert agent.calls()[-1]["argv"] == ["--fast"]


def test_an_agent_that_fails_or_is_slow_is_a_failed_call(agent):
    agent.env("FAKE_AGENT_FAIL", "1")
    r = Harness("gemini-cli", exe=FAKE).complete("Kinloom task: x", "y", timeout=30)
    assert not r.ok and "exit 3" in r.error and "not logged in" in r.error
    os.environ.pop("FAKE_AGENT_FAIL")
    agent.env("FAKE_AGENT_SLEEP", "5")
    for kind in ("claude-code", "codex"):
        t = time.monotonic()
        r = Harness(kind, exe=FAKE, pool=0).complete("Kinloom task: x", "y", timeout=1.0)
        assert not r.ok and r.error == "timed out" and time.monotonic() - t < 4


def test_an_agent_that_is_not_installed_is_said_plainly():
    h = Harness("codex")
    assert h.missing == "codex not found (install it, or check PATH)"
    r = h.complete("Kinloom task: x", "y")
    assert not r.ok and r.error == h.missing
    with pytest.raises(ValueError):
        Harness("claude")                      # Claude with a key is provider "anthropic"; the agent is "claude-code"
    with pytest.raises(ValueError):
        Harness("codex", "m; rm -rf /")
    with pytest.raises(ValueError):
        Harness("command")


def test_the_agent_is_chosen_in_kinloom_json_or_the_environment_never_by_itself(monkeypatch):
    p = config.provider({"provider": "claude-code", "model": "haiku", "pool": 0}, env={})
    assert isinstance(p, Harness) and p.kind == "claude-code" and p.model == "haiku"
    p = config.provider({}, env={"KINLOOM_HARNESS": "codex", "KINLOOM_HARNESS_MODEL": "gpt-x"})
    assert isinstance(p, Harness) and p.kind == "codex" and p.model == "gpt-x"
    # KINLOOM_MODEL names an API's model (set for keys): never passed to the agent (every call failed when it was)
    p = config.provider({"provider": "claude-code", "model": "haiku"}, env={"KINLOOM_MODEL": "deepseek/deepseek-v4.1-flash"})
    assert p.model == "haiku"
    assert config.provider({"provider": "claude-code"}, env={"KINLOOM_MODEL": "vendor/x"}).model == ""
    assert isinstance(detect({"KINLOOM_HARNESS": "gemini-cli"}), Harness)
    assert config.provider({}, env={"ANTHROPIC_API_KEY": "k"}).name == "anthropic"
    with pytest.raises(config.ConfigError):
        config.provider({"provider": "command"}, env={})
    assert detect({}, probe_ollama=False) is None             # an installed agent is never used without being chosen


def test_a_coding_agent_is_patient(agent):
    agent.answer(reply("Hello there."))
    h = Harness("claude-code", exe=FAKE, pool=0)
    assert h.patient
    b = Brain(provider=h, memory_path=None)
    assert b._patient() and b._reply_deadline() >= 15.0
    b.character("default", "Mira", "a smith")
    said = b.chat("default", "Mira", "hello")
    assert said == "Hello there." and said.source == "model"
    assert b.stats()["hedged"] == 0
    b.close()
    assert h._closed


def test_the_brain_starts_claude_code_processes_ahead(agent):
    agent.answer("Hi.")
    h = Harness("claude-code", exe=FAKE, pool=1)
    b = Brain(provider=h, memory_path=None)
    deadline = time.time() + 20
    while time.time() < deadline and not h._pool:
        time.sleep(0.05)
    assert len(h._pool) == 1
    b.close()


# ---------------- choosing: kinloom use, kinloom init, kinloom ----------------

def test_kinloom_use_writes_the_choice_and_back(tmp_path, capsys):
    from kinloom.cli import main
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {"soul": "a smith"}}}), encoding="utf-8")
    assert main(["use", "claude-code", "--model", "haiku", "--dir", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))
    assert data["provider"] == "claude-code" and data["model"] == "haiku" and "Mira" in data["characters"]
    out = capsys.readouterr().out
    assert "claude-code answers (haiku)" in out and "claude not found" in out    # conftest hides the real one
    assert main(["use", "key", "--dir", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))
    assert "provider" not in data and "model" not in data and "Mira" in data["characters"]
    assert main(["use", "command", "--dir", str(tmp_path)]) == 2
    assert main(["use", "command", "--dir", str(tmp_path), "--", "mytool", "--fast"]) == 0
    assert json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))["command"] == ["mytool", "--fast"]
    assert main(["use", "codex", "--model", "bad model;", "--dir", str(tmp_path)]) == 2


def test_the_wizard_offers_the_agents_subscription_when_one_is_installed(tmp_path, monkeypatch, capsys):
    from kinloom import init
    monkeypatch.setattr("kinloom.harness._which", lambda exe: "C:/bin/claude.exe" if exe == "claude" else None)
    answers = iter(["", "", "claude-code", "haiku", "", ""])
    assert init.wizard(str(tmp_path), ask=lambda prompt: next(answers)) == 0
    data = json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))
    assert data == {"provider": "claude-code", "model": "haiku"}
    assert "model: claude-code (haiku)" in capsys.readouterr().out


def test_kinloom_says_both_ways_to_get_a_model(tmp_path, monkeypatch, capsys):
    from kinloom.cli import main
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "an API key" in out and "kinloom use claude-code" in out


# ---------------- a server that is not there is seen at once ----------------

def test_the_online_mode_answers_offline_at_once_when_the_server_is_not_there():
    import socket as _socket
    s = _socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                          # nothing listens there now
    kl = Kinloom(url="http://127.0.0.1:%d" % port)
    kl.character("Mira", "a smith", offline="Busy.")
    t = time.monotonic()
    assert kl.chat("Mira", "hi") == "Busy."
    assert time.monotonic() - t < 1.0                  # Windows sees a refused connection after ~2 s without the check
    t = time.monotonic()
    for _ in range(5):
        assert kl.chat("Mira", "hi") == "Busy."
    assert time.monotonic() - t < 0.5                  # then nothing is tried for a while
    b = kl.brain
    b._down_until = 0.0
    kl.chat("Mira", "hi")
    assert b._failures == 2 and b._down_until - time.monotonic() > 3.0    # still not there: left alone longer
    kl.close()


# ---------------- one description of the HTTP API ----------------

def test_the_api_description_covers_every_verb_and_is_shipped(server):  # noqa: F811
    from kinloom import openapi
    from kinloom.server import VERBS
    assert sorted(openapi.POSTS) == sorted(VERBS)
    path = os.path.join(os.path.dirname(openapi.__file__), "kit", "openapi.json")
    with open(path, encoding="utf-8") as f:
        assert f.read() == openapi.text(), "kit/openapi.json is stale: python -m kinloom.openapi > src/kinloom/kit/openapi.json"
    brain, url = server(None)
    status, body, _ = call(url, "/v1/openapi.json")
    assert status == 200 and body["openapi"] == "3.1.0" and "/v1/chat" in body["paths"] and "/v1/prepare" in body["paths"]
    chat = body["paths"]["/v1/chat"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert chat["required"] == ["name", "message"] and "image" in chat["properties"]


# ---------------- no Python on the player's machine ----------------

def test_bundle_builds_a_folder_the_game_can_start(tmp_path, monkeypatch):
    from kinloom import bundle
    (tmp_path / "kinloom.json").write_text('{"characters": {"Mira": {"offline": "Busy."}}}', encoding="utf-8")
    seen = {}

    def fake_run(args, **kw):
        seen["args"] = args
        dist = args[args.index("--distpath") + 1]
        os.makedirs(os.path.join(dist, "kinloom", "_internal"))
        open(os.path.join(dist, "kinloom", "kinloom.exe"), "wb").close()

        class R:
            returncode, stdout, stderr = 0, "", ""
        return R()
    monkeypatch.setattr(bundle, "pyinstaller_command", lambda: ["pyinstaller"])
    code, message = bundle.build(str(tmp_path), "kinloom-server", run=fake_run)
    out = tmp_path / "kinloom-server"
    assert code == 0 and "kinloom-server" in message
    assert (out / "kinloom.exe").exists() and (out / ".gdignore").exists() and (out / "README.txt").exists()
    assert json.loads((out / "kinloom.json").read_text(encoding="utf-8"))["characters"]["Mira"]["offline"] == "Busy."
    assert "--onedir" in seen["args"] and "--collect-data" in seen["args"]
    monkeypatch.setattr(bundle, "pyinstaller_command", lambda: None)
    assert bundle.build(str(tmp_path))[0] == 2


def test_bundle_never_replaces_the_game_or_a_folder_that_is_not_a_bundle(tmp_path, monkeypatch):
    from kinloom import bundle
    monkeypatch.setattr(bundle, "pyinstaller_command", lambda: ["pyinstaller"])
    (tmp_path / "main.py").write_text("game")
    for out in (".", "..", str(tmp_path)):
        code, message = bundle.build(str(tmp_path), out, run=lambda *a, **k: 1 / 0)
        assert code == 2 and "holds the game" in message
    (tmp_path / "art").mkdir()
    (tmp_path / "art" / "hero.png").write_text("x")
    code, message = bundle.build(str(tmp_path), "art", run=lambda *a, **k: 1 / 0)
    assert code == 2 and "not a Kinloom bundle" in message and (tmp_path / "art" / "hero.png").exists()
    assert (tmp_path / "main.py").read_text() == "game"


def test_bundle_reports_a_failed_build(tmp_path, monkeypatch):
    from kinloom import bundle

    class R:
        returncode, stdout, stderr = 1, "", "boom"
    monkeypatch.setattr(bundle, "pyinstaller_command", lambda: ["pyinstaller"])
    code, message = bundle.build(str(tmp_path), run=lambda args, **kw: R())
    assert code == 1 and "boom" in message and not (tmp_path / "kinloom-server").exists()


def test_kinloom_check_reads_the_game_tools_and_the_model_choice(tmp_path):
    from kinloom.check import _config_findings
    (tmp_path / "kinloom.json").write_text(json.dumps({
        "provider": "claude-code", "tools": {"give": {"item": "bread"}, "open_door": {}},
        "characters": {"Mira": {"tools": ["give", "fly"], "trust": {"give": 0.3}},
                       "King": {"tools": "all", "trust": {"open_door": 0.5}}},
        "tool": {}}), encoding="utf-8")
    found = [m for _, m in _config_findings(str(tmp_path))[0]]
    assert any("names the tool 'fly'" in m for m in found)
    assert not any("trust names" in m for m in found)                # give and open_door are the game's tools
    assert any("unknown keys tool" in m for m in found)
    (tmp_path / "kinloom.json").write_text(json.dumps({"provider": "claud"}), encoding="utf-8")
    assert any("unknown provider 'claud'" in m for _, m in _config_findings(str(tmp_path))[0])
    (tmp_path / "kinloom.json").write_text(json.dumps({"provider": "command"}), encoding="utf-8")
    assert any("needs \"command\"" in m for _, m in _config_findings(str(tmp_path))[0])


def test_a_late_agent_is_stopped_at_its_deadline_not_left_running(agent):
    agent.env("FAKE_AGENT_SLEEP", "30")
    h = Harness("claude-code", exe=FAKE, pool=1)
    h.warm()
    deadline = time.time() + 20
    while time.time() < deadline and not h._pool:
        time.sleep(0.05)
    proc = h._pool[0][0]
    r = h.complete("Kinloom task: x", "y", timeout=1.0)
    assert not r.ok and r.error == "timed out"
    assert proc.wait(5) is not None                        # stopped at once (it would keep spending the plan)
    h.close()


def test_an_agent_answer_that_breaks_the_reader_is_a_failed_call(agent, monkeypatch):
    h = Harness("gemini-cli", exe=FAKE)
    monkeypatch.setattr(h, "_once", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    r = h.complete("Kinloom task: x", "y", timeout=5)
    assert not r.ok and "RuntimeError: boom" in r.error


def test_a_wrong_field_in_a_streamed_chat_is_a_400_not_a_cut_stream(server):  # noqa: F811
    brain, url = server(model(chat=reply("Hello.")))
    for body in ({"name": "Mira", "message": "hi", "stream": True, "facts": ["a"]},
                 {"name": "Mira", "message": "hi", "stream": True, "image": 5},
                 {"name": "Mira", "message": "hi", "facts": "gold"}):
        status, out, _ = call(url, "/v1/chat", body)
        assert status == 400 and "must be" in out["error"]
    status, out, _ = call(url, "/v1/say", {"name": "Mira", "event": "x", "facts": [1]})
    assert status == 400


def test_a_situation_with_odd_values_still_gets_a_decision():
    kl = make(model(decide={"choice": "b"}, act={"actions": [{"tool": "go", "args": {}}]}))
    kl.character("A", "x", tools={"go": {}})
    odd = {"blob": b"\x00\x01", "when": object(), "n": 1}
    kl.decide("A", odd, ["a", "b"])
    kl.act("A", odd)
    kl.wait_idle(5)
    assert kl.decide("A", odd, ["a", "b"]) == "b" and kl.act("A", odd) == [("go", {})]
    assert not [e for e in kl.journal() if e["kind"] == "error"]


def test_wrong_argument_types_say_which_argument():
    kl = make(None)
    with pytest.raises(TypeError, match="facts: an object"):
        kl.chat("A", "hi", ["gold"])
    with pytest.raises(ValueError, match="max_words: a finite number"):
        kl.character("A", "x", max_words=float("inf"))
    with pytest.raises(TypeError, match="seen_by: a list"):
        kl.event("x", seen_by=5)
    kl.event("x", seen_by="BAKER")                         # one name: a list of one


def test_an_infinite_number_over_http_is_a_400(server):  # noqa: F811
    import urllib.request
    brain, url = server(None)
    req = urllib.request.Request(url + "/v1/character", data=b'{"name": "A", "max_words": Infinity}', method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
        status = 200
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 400
