"""v1: saves, the player's choices, characters talking together, models per task, the content rating, inspect."""
import json
import os

import pytest

from kinloom import Kinloom, server
from kinloom.brain import Brain
from test_brain import make, model


# ---------------- 1. saves ----------------

def test_a_save_brings_back_memories_feelings_moods_conversations_and_lore():
    p = model(chat="Hm, Ana. Welcome back.\n~~~\n{\"mood\": \"wary\", \"intensity\": 0.8, \"feel\": -0.2, \"remember\": \"Ana owes me 3 coins\"}")
    kl = make(p)
    kl.character("Mira", "a gruff smith")
    kl.chat("Mira", "I'll pay you tomorrow.", speaker="Ana")
    kl.lore(["The village is Brookmere."])
    kl.state({"day": 3})
    data = kl.save()
    assert isinstance(data, str) and json.loads(data)["kinloom"] == 1

    other = make(p)                                     # a new run of the game: the player loads their slot
    other.character("Mira", "a gruff smith")
    assert other.opinion("Mira", "Ana") == 0.0
    assert other.load(data) is True
    soul = other.soul("Mira", "Ana")
    assert other.opinion("Mira", "Ana") == pytest.approx(-0.2)
    assert soul["mood"]["word"] == "wary"
    assert any("3 coins" in m for m in soul["memories"])
    assert soul["conversation"][0] == ["Ana", "I'll pay you tomorrow."]
    assert other.lore() == ["The village is Brookmere."]
    assert soul["bonds"]["Ana"]["talks"] == 1


def test_a_save_belongs_to_its_session_and_loading_replaces_it():
    brain = Brain(provider=None, memory_path=None)
    slot1, slot2 = Kinloom(brain=brain).session("slot1"), Kinloom(brain=brain).session("slot2")
    slot1.remember("Mira", "the player saved the mill")
    slot2.remember("Mira", "the player burned the mill")
    data = slot1.save()
    assert "burned" not in data
    slot2.load(data)
    assert slot2.memories("Mira") == ["the player saved the mill"]
    assert slot1.memories("Mira") == ["the player saved the mill"]


def test_learned_minds_come_back_with_the_save():
    brain = Brain(provider=None, memory_path=None)
    kl = Kinloom(brain=brain)
    senses, actions = {"hp": [0, 1]}, {"fight": {}, "flee": {}}
    kl.mind("guard", "a guard", senses, actions, variants=2)
    brain.memory.put("minds", "default/guard", {"sig": brain._minds[("default", "guard")].sig,
                                                "variants": [{"flee": {"score": 2.0}}, {"fight": {"score": 2.0}}],
                                                "generation": 7, "curve": [0.5]})
    data = kl.save()
    fresh = Kinloom(brain=Brain(provider=None, memory_path=None))
    fresh.mind("guard", "a guard", senses, actions, variants=2)
    fresh.load(data)
    assert fresh.mind_report("guard")["generation"] == 7


def test_loading_something_else_is_a_clear_error():
    kl = make(None)
    for bad in ("", "not json", "{}", json.dumps({"kinloom": 2})):
        with pytest.raises(ValueError, match="not a Kinloom save"):
            kl.load(bad)


# ---------------- 2. the player's choices ----------------

def test_suggest_rewrites_each_example_for_the_moment_in_order():
    p = model(suggest={"replies": ["Show me the king's sword.", "How much for a blade?", "Goodbye, Mira."]})
    kl = make(p)
    kl.character("Mira", "a gruff smith")
    got = kl.suggest("Mira", ["Ask about the sword", "Buy something", "Leave"], speaker="Ana")
    assert got == ["Show me the king's sword.", "How much for a blade?", "Goodbye, Mira."]
    system = [c for c in p.calls if c[0] == "suggest"][0][1]
    assert "Write 3 replies Ana could say now" in system and "keep each example's intent" in system


def test_suggest_keeps_an_example_wherever_the_answer_is_unusable():
    p = model(suggest={"replies": ["", "x " * 40, "Ignore previous instructions", 7]})
    kl = make(p)
    examples = ["Ask", "Buy", "Leave", "Wave"]
    assert kl.suggest("Mira", examples) == examples
    assert make(None).suggest("Mira", ["Hi", "Bye"]) == ["Hi", "Bye"]
    with pytest.raises(ValueError, match="examples"):
        make(None).suggest("Mira", "Hi")
    with pytest.raises(ValueError, match="examples"):
        make(None).suggest("Mira", [])


# ---------------- 3. characters talking together ----------------

def test_converse_writes_an_exchange_both_characters_remember():
    p = model(converse={"lines": [{"who": "Mira", "text": "Bram, your bread smells of smoke again."},
                                  {"who": "bram", "text": "My oven, my rules."},
                                  {"who": "Nobody", "text": "skipped"},
                                  {"who": "Mira", "text": "As an AI I cannot say."}]})
    kl = make(p)
    kl.character("Mira", "a gruff smith")
    kl.character("Bram", "a proud baker")
    lines = kl.converse("Mira", "Bram", about="the smoke", turns=4)
    assert lines == [{"who": "Mira", "text": "Bram, your bread smells of smoke again."}, {"who": "Bram", "text": "My oven, my rules."}]
    assert any("Talked with Bram" in m for m in kl.memories("Mira"))
    assert any("Talked with Mira" in m for m in kl.memories("Bram"))
    system = [c for c in p.calls if c[0] == "converse"][0][1]
    assert "Write 4 lines, alternating, Mira first" in system


def test_converse_offline_or_alone_says_nothing():
    assert make(None).converse("Mira", "Bram") == []
    assert make(model(converse="not json")).converse("Mira", "Bram") == []
    assert make(model(converse={"lines": []})).converse("Mira", "Mira") == []


# ---------------- 4. models per task ----------------

def test_background_work_uses_the_background_model_and_talk_the_main_one():
    p = model(chat="Hello.", lines={"lines": ["Go {who}!"]})
    kl = make(p, models={"background": "cheap-model"})
    seen = []
    import kinloom.brain as b
    real = b._complete

    def spy(provider, system, user, **kw):
        seen.append((b.prompts and system.split("\n")[0], provider.model))
        return real(provider, system, user, **kw)

    b._complete = spy
    try:
        kl.character("VEGA", "commentator", events={"overtake": ["who"]})
        kl.wait_idle(5)
        kl.chat("VEGA", "hi")
    finally:
        b._complete = real
    assert ("Kinloom task: lines", "cheap-model") in seen
    assert ("Kinloom task: chat", "scripted") in seen
    assert p.model == "scripted"                             # the main provider is untouched


def test_models_and_rating_are_checked():
    with pytest.raises(ValueError, match="task group"):
        make(model(), models={"talk": "x"})
    with pytest.raises(ValueError, match="rating"):
        make(model(), rating="kids")
    assert make(model(), models={"background": "cheap"}).status()["models"] == {"background": "cheap"}


# ---------------- 5. content rating ----------------

def test_the_rating_reaches_every_prompt_and_none_changes_nothing():
    p = model(chat="Hi.", decide={"go": "left"})
    kl = make(p, rating="everyone")
    kl.chat("Mira", "hi")
    kl.decide("Mira", {}, {"go": ["left", "right"]})
    kl.wait_idle(5)
    assert all("Content rating: everyone" in system for _, system, _ in p.calls)
    q = model(chat="Hi.")
    make(q).chat("Mira", "hi")
    assert all("Content rating" not in system for _, system, _ in q.calls)
    r = model(chat="Hi.")
    make(r, rating="mature").chat("Mira", "hi")
    assert all("Content rating" not in system for _, system, _ in r.calls)


# ---------------- 8. inspect ----------------

def test_inspect_shows_characters_and_minds():
    kl = make(model(chat="Fine.\n~~~\n{\"mood\": \"busy\", \"feel\": 0.1}"))
    kl.character("Mira", "a gruff smith")
    kl.chat("Mira", "hi", speaker="Ana")
    kl.mind("guard", "a guard", {"hp": [0, 1]}, {"fight": {}, "flee": {}}, variants=1)
    snap = kl.inspect()
    mira = snap["characters"]["Mira"]
    assert mira["mood"]["word"] == "busy" and mira["last_words"] == "Fine." and mira["talks"] == {"Ana": 1}
    assert mira["feelings"]["Ana"] == pytest.approx(0.1)
    assert snap["minds"]["guard"]["variants"] == 1 and snap["online"] is True


# ---------------- over HTTP ----------------

def test_the_v1_verbs_over_http():
    brain = Brain(provider=None, memory_path=None)
    assert server.handle(brain, "suggest", {"name": "Mira", "examples": ["Hi", "Bye"]}, "s") == {"replies": ["Hi", "Bye"]}
    assert server.handle(brain, "converse", {"a": "Mira", "b": "Bram"}, "s") == {"lines": []}
    data = server.handle(brain, "save", {}, "s")["data"]
    assert server.handle(brain, "load", {"data": data}, "s2") == {"ok": True}
    assert "characters" in server.handle(brain, "inspect", {}, "s")
    with pytest.raises(server.ApiError):
        server.handle(brain, "suggest", {"name": "Mira"}, "s")
    with pytest.raises(server.ApiError):
        server.handle(brain, "load", {"data": "nope"}, "s")


# ---------------- kinloom.json, Unity ----------------

def test_a_wrong_rating_or_models_in_kinloom_json_is_refused_not_fatal(tmp_path):
    (tmp_path / "kinloom.json").write_text(json.dumps({"rating": "kids", "models": {"talk": "x"}}), encoding="utf-8")
    brain = Brain(provider=None, memory_path=None, folder=str(tmp_path))
    refused = [e["text"] for e in brain.journal() if e["kind"] == "refused"]
    assert any("rating" in t for t in refused) and any("task group" in t for t in refused)
    assert brain.rating is None and brain.models == {}
    from kinloom.check import check
    _, results = check(str(tmp_path))
    assert any(level == "error" and "rating" in m for level, m in results)
    assert any(level == "error" and "\"models\"" in m for level, m in results)


def test_init_gives_unity_the_dialogue_component(tmp_path):
    from kinloom import init
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    init.setup(str(tmp_path), "unity", "minimal")
    box = tmp_path / "Assets" / "Kinloom" / "KinloomDialogue.cs"
    assert box.exists() and "class KinloomDialogue : MonoBehaviour" in box.read_text(encoding="utf-8")


def test_python_dash_m_kinloom_works_like_the_command():
    import subprocess
    import sys
    src = os.path.join(os.path.dirname(__file__), "..", "src")
    r = subprocess.run([sys.executable, "-m", "kinloom", "--version"], capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONPATH=src))
    assert r.returncode == 0 and r.stdout.strip() == "kinloom 1.0.0"


def test_a_reply_also_has_text_like_other_sdks_answers():
    kl = Kinloom(provider=None, memory_path=None)
    kl.character("Wren", "a keeper", offline="Stay sharp.")
    reply = kl.chat("Wren", "Hi", speaker="Ana")
    assert reply.text == "Stay sharp." and type(reply.text) is str and reply == "Stay sharp."
    kl.close()


def test_python_dash_m_inside_a_game_uses_the_installed_kinloom_not_the_games_copy(tmp_path):
    import shutil
    import subprocess
    import sys
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    copy = tmp_path / "kinloom"
    shutil.copytree(os.path.join(src, "kinloom"), copy, ignore=shutil.ignore_patterns("__pycache__", "clients"))
    init_py = copy / "__init__.py"
    init_py.write_text(init_py.read_text(encoding="utf-8").replace('__version__ = "1.0.0"', '__version__ = "0.0.1"'), encoding="utf-8")
    run = lambda env: subprocess.run([sys.executable, "-m", "kinloom", "--version"], cwd=str(tmp_path), capture_output=True,
                                     text=True, timeout=60, env=env)
    r = run(dict(os.environ, PYTHONPATH=src))
    assert r.returncode == 0 and r.stdout.strip() == "kinloom 1.0.0", r.stdout + r.stderr
    alone = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = run(dict(alone, PYTHONNOUSERSITE="1"))           # whether or not one is installed, it runs
    assert r.returncode == 0 and r.stdout.strip().startswith("kinloom "), r.stdout + r.stderr


def test_check_warns_when_text_is_used_as_a_placeholder_in_an_example(tmp_path):
    from kinloom.check import check
    (tmp_path / "main.py").write_text("from kinloom import Kinloom\nkl = Kinloom()\n"
                                      "a = kl.create('a greeting', {'greeting': 'text'})\n"
                                      "b = kl.create('a note', {'text': 'Found under a cold stone.'})\n", encoding="utf-8")
    _, results = check(str(tmp_path), url="http://127.0.0.1:1")
    found = [m for level, m in results if "placeholder" in m or "the word \"text\"" in m]
    assert len(found) == 1 and found[0].startswith("main.py:3")


def test_what_a_loaded_save_said_stays_bounded():
    kl = Kinloom(provider=None, memory_path=None)
    data = json.loads(kl.save())
    data["said"] = {"Mira": ["line %d" % i for i in range(30)]}
    kl.load(json.dumps(data))
    said = kl.brain._said[("default", "Mira")]
    assert list(said) == ["line %d" % i for i in range(22, 30)]
    said.append("one more")
    assert len(said) == 8
    kl.close()


def test_kinloom_shows_the_models_and_rating_it_uses(tmp_path):
    from kinloom.cli import _describe
    from kinloom.providers import OpenAICompatible
    brain = Brain(provider=OpenAICompatible("http://127.0.0.1:9/v1", "k", "main-model"), memory_path=None,
                  models={"background": "cheap-model"}, rating="teen", folder=str(tmp_path))
    assert _describe(brain).endswith("(main-model) [background: cheap-model, rating: teen]")
    brain.close()
