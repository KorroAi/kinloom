"""kinloom add (a character in one command) and kinloom recipe (any request -> the call and the pattern)."""
import json

import pytest

from kinloom import Kinloom
from kinloom.add import add, parse_tools, SNIPPETS
from kinloom.cli import main
from kinloom.config import ConfigError


def test_add_writes_the_character_and_prints_code_for_the_engine(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n")
    (tmp_path / "kinloom.json").write_text('{"language": "French"}')
    text = add(str(tmp_path), "Mira", "a gruff smith", tools="give(item), refuse_service", trust=["give=0.3"],
               offline="Busy.", strict=True)
    data = json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))
    assert data["language"] == "French"                                          # the rest is kept
    assert data["characters"]["Mira"] == {"soul": "a gruff smith", "offline": "Busy.",
                                          "tools": {"give": {"item": "text"}, "refuse_service": {}},
                                          "trust": {"give": 0.3}, "invent": False}
    assert 'await Kinloom.chat("Mira", text' in text and "AIDialogue" in text
    kl = Kinloom(provider=None, memory_path=None, folder=str(tmp_path))
    assert kl.chat("Mira", "hi") == "Busy."


def test_add_never_breaks_a_bad_config(tmp_path):
    (tmp_path / "kinloom.json").write_text("{not json")
    with pytest.raises(ConfigError):
        add(str(tmp_path), "Mira", "a smith")
    assert (tmp_path / "kinloom.json").read_text() == "{not json"


def test_add_checks_trust_names_and_adds_lore(tmp_path):
    with pytest.raises(ValueError):
        add(str(tmp_path), "Mira", "a smith", tools="give(item)", trust=["steal=0.5"])
    add(str(tmp_path), "", lore=["The village is Ashford.", "The king died."])
    add(str(tmp_path), "", lore=["The village is Ashford."])
    assert json.loads((tmp_path / "kinloom.json").read_text())["lore"] == ["The village is Ashford.", "The king died."]


def test_every_engine_has_a_snippet_that_formats():
    for lang, s in SNIPPETS.items():
        text = s.format(name="Mira")
        assert "Mira" in text and "{name}" not in text, lang


def test_tools_parse_from_plain_words():
    assert parse_tools("give(item), follow, sell(item, price)") == {
        "give": {"item": "text"}, "follow": {}, "sell": {"item": "text", "price": [0, 100]}}


def test_cli_add(tmp_path, capsys):
    (tmp_path / "main.py").write_text("")
    assert main(["add", "Orrin", "an old lighthouse keeper", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert 'PygameTalkBox(kl, "Orrin"' in out and 'box.handle(e)' in out
    assert main(["add", "Mira", "x", "--tools", "give(item)", "--trust", "steal=1", "--dir", str(tmp_path)]) == 2


@pytest.mark.parametrize("request_text,expected", [
    ("add a blacksmith the player can talk to and bargain with", "chat + soul"),
    ("a commentator that reacts to goals", "say"),
    ("make the boss choose its attacks depending on the fight", "decide"),
    ("hundreds of enemies that get smarter over time", "mind + think + reward"),
    ("generate a random quest every morning", "create"),
    ("guards should hear rumors about the player's theft", "event + meet + opinion + reputation"),
    ("the player types orders to his squad in natural language", "act + tools"),
    ("keep characters consistent with our world canon", "lore + invent=false"),
    ("characters should speak their lines aloud", "speak + listen"),
    ("let the player talk to the guard with the microphone", "speak + listen"),
])
def test_any_request_goes_to_the_right_call(request_text, expected):
    from kinloom.recipe import recipe
    text = recipe(request_text, "godot")
    assert ("Use %s " % expected) in text.split("\n\n")[1] + text, (request_text, text[:300])


def test_a_recipe_is_short_and_in_the_game_language():
    from kinloom.recipe import recipe
    text = recipe("an innkeeper players can chat with", "web")
    assert 'kl.chat("NAME", text' in text and len(text) < 6000


def test_unsupported_requests_are_said_honestly_and_unknown_ones_get_the_map():
    from kinloom.recipe import recipe
    assert "does not generate images" in recipe("generate sprites for my monsters", "python")
    assert "does not generate" not in recipe("characters speak their lines aloud", "python")
    text = recipe("xyzzy plugh", "python")
    assert "pick by what the game needs back" in text and "anything else" in text


@pytest.mark.parametrize("engine,call", [("python", 'kl.decide("WEATHER"'), ("godot", 'Kinloom.decide("WEATHER"'),
                                         ("web", 'kl.decide("WEATHER"'), ("unity", 'kl.Decide("WEATHER"')])
def test_a_request_in_other_words_gets_the_exact_calls_of_the_game_language(engine, call):
    from kinloom.recipe import recipe
    text = recipe("Génère une recette de potion aléatoire avec ses ingrédients et son effet.", engine)
    assert call in text and "create(" in text.lower()


@pytest.mark.parametrize("request_text,pattern", [
    ("make the shades attack smarter as waves go by", "Crowd minds"),
    ("a merchant who haggles", "a shopkeeper"),
    ("generate a random quest every morning", "a quest giver"),
    ("boss chooses attacks", "boss phases"),
    ("dynamic difficulty", "a director"),
    ("summary after each match", "a post-match recap"),
])
def test_the_closest_pattern_belongs_to_the_request(request_text, pattern):
    from kinloom.recipe import recipe
    assert "## %s" % pattern not in "" and pattern in recipe(request_text, "python").split("Closest patterns")[1].split("\n## ")[1]


def test_add_keeps_a_voice_and_speak_says_a_line(tmp_path, capsys, monkeypatch):
    import json
    from kinloom.cli import main
    assert main(["add", "Mira", "a gruff smith", "--voice", "low, warm", "--dir", str(tmp_path)]) == 0
    assert json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))["characters"]["Mira"]["voice"] == "low, warm"
    monkeypatch.setenv("KINLOOM_VOICE", "scripted")
    capsys.readouterr()
    assert main(["speak", "The", "forge", "is", "hot.", "--name", "Mira", "--no-play", "--dir", str(tmp_path),
                 "--out", str(tmp_path / "line.wav")]) == 0
    out = capsys.readouterr().out
    assert "voice: scripted" in out and ".wav" in out and (tmp_path / "line.wav").read_bytes()[:4] == b"RIFF"
    monkeypatch.setenv("KINLOOM_VOICE", "off")
    assert main(["speak", "hello", "--no-play", "--dir", str(tmp_path)]) == 1
    assert "ELEVENLABS_API_KEY" in capsys.readouterr().out
