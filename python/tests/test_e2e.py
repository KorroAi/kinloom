"""End to end, as a developer or a coding agent does it: `kinloom init`, `kinloom add`, a game that calls the character,
`kinloom check`, `kinloom run -- <game>`. Real processes, a scripted model (no tokens)."""
import json
import os
import shutil
import socket
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
SCRIPT = {
    "soul": {"summary": "Mira, a gruff blacksmith", "secrets": ["she sold the king's sword"], "mood": "wary"},
    "greet": "You. Buying or staring?\n~~~\n{\"mood\": \"wary\"}",
    "chat": "Fine. Take it and go.\n~~~\n{\"mood\": \"tired\", \"feel\": 0.3, "
            "\"do\": [{\"tool\": \"give\", \"args\": {\"item\": \"sword\"}}]}",
}


def kinloom(folder, *args, env=None, timeout=120):
    e = dict(os.environ, PYTHONPATH=SRC, PYTHONIOENCODING="utf-8", **(env or {}))
    for k in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "KINLOOM_MODEL", "KINLOOM_BASE_URL"):
        e.pop(k, None)
    r = subprocess.run([sys.executable, "-m", "kinloom.cli"] + list(args), cwd=str(folder), env=e, capture_output=True,
                       text=True, encoding="utf-8", timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scripted(folder):
    path = os.path.join(str(folder), "script.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(SCRIPT, f)
    return {"KINLOOM_SCRIPT": path}


def test_a_python_game_from_init_to_a_character_that_acts(tmp_path):
    (tmp_path / "main.py").write_text("")
    code, out = kinloom(tmp_path, "init", ".", "--yes", "--agents", "all")
    assert code == 0 and (tmp_path / "CLAUDE.md").exists() and (tmp_path / ".claude" / "commands" / "kinloom.md").exists()
    code, out = kinloom(tmp_path, "add", "Mira", "a gruff blacksmith who sold the king's sword", "--tools", "give(item)",
                        "--trust", "give=0.3", "--offline", "Busy.")
    assert code == 0 and 'PygameTalkBox(kl, "Mira"' in out
    (tmp_path / "game.py").write_text(
        "from kinloom import Kinloom\n"
        "kl = Kinloom()\n"
        "kl.wait_idle(5)\n"
        "print('greeting:', kl.chat('Mira', '', speaker='Ana'))\n"
        "print('reply:', kl.chat('Mira', 'Can I have the sword?', speaker='Ana'))\n"
        "print('acts:', kl.act('Mira', think=False))\n"
        "kl.close()\n", encoding="utf-8")
    code, out = kinloom(tmp_path, "check", ".")
    assert code == 0 and "characters declared: Mira" in out
    code, out = kinloom(tmp_path, "run", "--port", str(free_port()), "--", sys.executable, "game.py", env=scripted(tmp_path))
    assert code == 0, out
    assert "greeting: You. Buying or staring?" in out and "reply: Fine. Take it and go." in out
    assert "acts: [('give', {'item': 'sword'})]" in out
    assert "Kinloom during this run: chat 2" in out and "characters that spoke or acted: Mira" in out


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node")
def test_a_web_game_through_the_server(tmp_path):
    (tmp_path / "package.json").write_text('{"type": "module"}')
    code, _ = kinloom(tmp_path, "init", ".", "--yes")
    assert code == 0 and (tmp_path / "kinloom" / "kinloom.js").exists() and (tmp_path / "kinloom" / "kinloom-talk.js").exists()
    code, _ = kinloom(tmp_path, "add", "Mira", "a gruff blacksmith", "--tools", "give(item)", "--trust", "give=0.3")
    assert code == 0
    (tmp_path / "game.mjs").write_text(
        'import { Kinloom } from "./kinloom/kinloom.js";\n'
        'const kl = new Kinloom({ url: "http://127.0.0.1:" + process.env.KINLOOM_TEST_PORT });\n'
        'let shown = "";\n'
        'console.log("reply:", await kl.chat("Mira", "Can I have the sword?", {}, "Ana", (p) => (shown += p)));\n'
        'console.log("streamed:", shown.trim());\n'
        'let acts = [];\n'
        'for (let i = 0; i < 40 && !acts.length; i++) { acts = kl.act("Mira", {}, false); await new Promise((r) => setTimeout(r, 50)); }\n'
        'console.log("acts:", JSON.stringify(acts));\n'
        'console.log("mood:", (await kl.soul("Mira", "Ana")).mood.word);\n', encoding="utf-8")
    code, out = kinloom(tmp_path, "run", "--port", str(free_port()), "--", "node", "game.mjs", env=scripted(tmp_path))
    assert code == 0, out
    assert "reply: Fine. Take it and go." in out and "streamed: Fine. Take it and go." in out
    assert 'acts: [{"tool":"give","args":{"item":"sword"}}]' in out and "mood: tired" in out
    assert "Kinloom during this run: chat 1" in out


def test_kinloom_alone_and_recipe_work_in_a_fresh_folder(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n")
    code, out = kinloom(tmp_path, env={"KINLOOM_OFFLINE": "1"})
    assert code == 0 and "game: godot" in out and "Ask your coding agent" in out
    code, out = kinloom(tmp_path, "recipe", "an", "innkeeper", "players", "can", "chat", "with")
    assert code == 0 and "Use chat + soul" in out and 'Kinloom.chat("NAME"' in out
