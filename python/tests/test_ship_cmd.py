"""`kinloom ship`: what to fix before a release, and the AI disclosure draft."""
import json
import os

from kinloom import cli, mcp, ship


def game(tmp_path, files, cfg=None):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if cfg is not None:
        (tmp_path / "kinloom.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(tmp_path)


def levels(results, level):
    return [m for lv, m in results if lv == level]


READY = {"rating": "everyone", "max_cost_per_hour": 0.5, "prices": {"input": 1, "output": 2, "source": "the provider's page"},
         "characters": {"Mira": {"personality": "a smith", "offline": "Busy."}}}


def test_a_key_in_any_file_is_an_error_and_dotenv_a_warning(tmp_path):
    key = "sk-ant-" + "a1B2" * 8
    folder = game(tmp_path, {"main.py": "from kinloom import Kinloom\n", "data/settings.json": '{"k": "%s"}' % key,
                             ".env": "ANTHROPIC_API_KEY=%s\n" % key}, READY)
    _, results, _ = ship.review(folder)
    errors = levels(results, "error")
    assert any("data/settings.json:1" in m and "model key" in m for m in errors)
    assert any(".env:1" in m for m in levels(results, "warn"))


def test_a_ready_game_has_nothing_to_fix(tmp_path):
    folder = game(tmp_path, {"main.py": "from kinloom import Kinloom\nkl = Kinloom(url='https://ai.example.org', token=t)\n"
                                        "kl.chat('Mira', text, speaker='Ana')\n"}, READY)
    _, results, facts = ship.review(folder)
    assert levels(results, "error") == []
    assert levels(results, "warn") == []
    assert any("no model key" in m for m in levels(results, "ok"))
    assert any("content rating: everyone" in m for m in levels(results, "ok"))
    assert facts["features"][0].startswith("Characters answer")


def test_what_is_missing_is_told(tmp_path):
    folder = game(tmp_path, {"main.py": "kl.character('Bram', 'a baker')\n"}, {"characters": {"Mira": {"personality": "a smith"}}})
    _, results, _ = ship.review(folder)
    warns = " | ".join(levels(results, "warn"))
    assert "no offline answer for Bram (main.py:1), Mira" in warns
    assert "no spending cap" in warns and "no \"prices\"" in warns and "no content rating" in warns


def test_the_coding_agent_plan_cannot_ship(tmp_path):
    folder = game(tmp_path, {"main.py": "x = 1\n"}, dict(READY, provider="claude-code"))
    _, results, _ = ship.review(folder)
    assert any("coding agent's subscription" in m for m in levels(results, "error"))


def test_a_bad_rating_is_an_error(tmp_path):
    folder = game(tmp_path, {"main.py": "x = 1\n"}, dict(READY, rating="kids"))
    _, results, _ = ship.review(folder)
    assert any("rating" in m for m in levels(results, "error"))


def test_how_players_reach_a_model(tmp_path):
    folder = game(tmp_path, {"game.js": "import { Kinloom } from './kinloom.js'\nconst kl = new Kinloom('http://127.0.0.1:7717')\n",
                             "kinloom.js": "// client\n"}, READY)
    _, results, _ = ship.review(folder)
    assert any("players do not run one" in m for m in levels(results, "warn"))
    os.makedirs(os.path.join(folder, "kinloom-server"))
    with open(os.path.join(folder, "kinloom-server", "README.txt"), "w", encoding="utf-8") as f:
        f.write("Kinloom for this game (windows)\n")
    _, results, _ = ship.review(folder)
    assert any("bundled kinloom server" in m for m in levels(results, "ok"))
    folder2 = game(tmp_path / "relay", {"game.js": "import { Kinloom } from './kinloom.js'\nconst kl = new Kinloom('https://ai.example.org', "
                                                   "{ token: t })\n", "kinloom.js": "// client\n"}, READY)
    _, results, facts = ship.review(folder2)
    assert facts["relay"] == "https://ai.example.org"
    assert any("relay: https://ai.example.org" in m for m in levels(results, "ok"))
    folder3 = game(tmp_path / "native", {"Game.cs": "var kl = new Kinloom(new KinloomOptions { Provider = Env(\"OPENAI_API_KEY\") });\n"
                                                    "await kl.ChatAsync(\"Mira\", text);\n"}, READY)
    _, results, _ = ship.review(folder3)
    assert any("reads OPENAI_API_KEY on the player's machine" in m for m in levels(results, "warn"))


def test_the_disclosure_says_what_the_game_uses_and_invents_nothing(tmp_path):
    folder = game(tmp_path, {"main.py": "kl.chat('Mira', t, speaker='Ana')\nkl.speak('Mira', line)\nkl.listen(rec)\n"
                                        "kl.create('loot', {'item': 'sword'})\n"},
                  dict(READY, provider="openrouter", banned_words=["dragon"]))
    _, _, facts = ship.review(folder)
    text = ship.disclosure(facts)
    assert "Characters answer what players type or say" in text
    assert "Synthetic voices" in text and "voice recordings" in text and "Game content" in text
    assert "kinloom.json (openrouter)" in text
    assert "\"everyone\", given to the model as a rule" in text
    assert "Banned words: 1" in text
    assert "What players type or say is sent" in text
    assert "Not detected by this tool" in text


def test_the_command_writes_the_draft_and_fails_on_errors(tmp_path, capsys):
    folder = game(tmp_path, {"main.py": "kl.chat('Mira', t, speaker='Ana')\n"}, READY)
    assert cli.main(["ship", folder]) == 0
    assert os.path.exists(os.path.join(folder, "kinloom-ai-disclosure.md"))
    assert "Ready to ship." in capsys.readouterr().out
    bad = game(tmp_path / "bad", {"main.py": "KEY = 'sk-" + "x" * 40 + "'\n"}, READY)
    assert cli.main(["ship", bad, "--disclosure", ""]) == 1
    assert not os.path.exists(os.path.join(bad, "kinloom-ai-disclosure.md"))
    assert "Fix the errors" in capsys.readouterr().out


def test_mcp_ship(tmp_path):
    folder = game(tmp_path, {"main.py": "kl.chat('Mira', t, speaker='Ana')\n"}, READY)
    assert any(t["name"] == "kinloom_ship" for t in mcp.TOOLS)
    r = mcp.call(folder, "kinloom_ship", {})
    assert not r.get("isError") and "Ready to ship." in r["content"][0]["text"]


def test_a_python_game_that_finds_its_key_in_the_environment_is_told(tmp_path):
    folder = game(tmp_path, {"main.py": "from kinloom import Kinloom\nkl = Kinloom()\nkl.chat('Mira', t, speaker='Ana')\n"}, READY)
    _, results, _ = ship.review(folder)
    assert any("Kinloom() looks in the environment" in m for m in levels(results, "warn"))
    folder2 = game(tmp_path / "relay", {"main.py": "kl = Kinloom(url='https://ai.example.org', token=t)\n"}, READY)
    _, results, _ = ship.review(folder2)
    assert not any("looks in the environment" in m for m in levels(results, "warn"))
