"""`kinloom init`, the agent kit, the cookbook, `kinloom check` and the MCP server."""
import io
import json
import os
import re

import pytest

from kinloom import Kinloom, init, mcp
from kinloom.check import check
from kinloom.cli import main
from kinloom.providers import Scripted

KIT = os.path.join(os.path.dirname(init.__file__), "kit")


def blocks(path, lang):
    text = open(path, encoding="utf-8").read()
    return re.findall(r"```%s\n(.*?)```" % lang, text, re.S)


# ---------------- engine detection ----------------

@pytest.mark.parametrize("files,engine", [
    (["project.godot"], "godot"),
    (["Assets/x.cs", "ProjectSettings/p.asset"], "unity"),
    (["Game.uproject"], "unreal"),
    (["main.lua", "conf.lua"], "love"),
    (["Game.csproj", "Game1.cs"], "dotnet"),
    (["package.json", "src/main.ts"], "web"),
    (["index.html", "game.js"], "web"),
    (["main.py"], "python"),
    (["game.project", "main/main.script"], "defold"),
    (["Cargo.toml", "src/main.rs"], "rust"),
    (["build.gradle", "src/main/java/Game.java"], "java"),
    (["CMakeLists.txt", "src/main.cpp"], "cpp"),
    (["main.cpp"], "cpp"),
    (["readme.txt"], "other"),
])
def test_detect(tmp_path, files, engine):
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    assert init.detect(str(tmp_path)) == engine


# ---------------- init ----------------

GODOT_PROJECT = """; Engine configuration file.
config_version=5

[application]

config/name="Truck"

[autoload]

Music="*res://music.gd"

[editor_plugins]

enabled=PackedStringArray("res://addons/other/plugin.cfg")
"""


def test_init_godot_installs_the_addon_and_enables_it_once(tmp_path):
    (tmp_path / "project.godot").write_bytes(GODOT_PROJECT.replace("\n", "\r\n").encode())
    done = init.setup(str(tmp_path))
    assert done["engine"] == "godot"
    assert (tmp_path / "addons/kinloom/kinloom.gd").exists()
    assert (tmp_path / "addons/kinloom/ai_character.gd").exists()
    project = (tmp_path / "project.godot").read_bytes().decode()
    assert 'Kinloom="*res://addons/kinloom/kinloom.gd"' in project
    assert 'Music="*res://music.gd"' in project
    assert 'enabled=PackedStringArray("res://addons/other/plugin.cfg", "res://addons/kinloom/plugin.cfg")' in project
    assert "\r\n" in project and "\n" not in project.replace("\r\n", "")
    init.setup(str(tmp_path))                                    # again: nothing duplicated
    again = (tmp_path / "project.godot").read_bytes().decode()
    assert again == project
    assert again.count("Kinloom=") == 1


def test_init_godot_adds_missing_sections(tmp_path):
    (tmp_path / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="X"\n')
    init.setup(str(tmp_path))
    project = (tmp_path / "project.godot").read_text(encoding="utf-8")
    assert "[autoload]\n\nKinloom=" in project or "[autoload]\nKinloom=" in project
    assert 'enabled=PackedStringArray("res://addons/kinloom/plugin.cfg")' in project


def test_init_writes_every_agent_format_and_keeps_existing_text(tmp_path):
    (tmp_path / "main.py").write_text("print('game')\n")
    (tmp_path / "AGENTS.md").write_text("# My rules\n\nUse tabs.\n")
    done = init.setup(str(tmp_path), agents="all")
    for rel in ("KINLOOM.md", "AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md", "GEMINI.md", ".windsurfrules", ".aider.conf.yml",
                ".claude/skills/kinloom/SKILL.md", ".cursor/rules/kinloom.mdc"):
        assert (tmp_path / rel).exists(), rel
        assert rel in done["files"]
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# My rules\n\nUse tabs.\n")
    assert agents.count(init.START) == 1 and "kinloom recipe" in agents and "from kinloom import Kinloom" in agents
    # read in every session: kept short (every call shown once). 5134 -> 5613 on 2026-10-01: tools() and image= shown
    # once, and the rule that the model (a key or the agent's plan) is the developer's choice; 6251 on 2026-10-03: the
    # v1 calls (suggest, converse, save/load, inspect) and `kinloom ship`; 6291 on 2026-10-07: create's check= and
    # offline= (comments shortened elsewhere); then each=, remark and check= everywhere (comments shortened again)
    assert len(agents) < 6300
    init.setup(str(tmp_path), agents="all")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents
    assert ".kinloom/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    full = (tmp_path / "KINLOOM.md").read_text(encoding="utf-8")
    assert "## 22. A summary of what happened" in full and "kl.say(" in full


def test_every_engine_brief_stays_short():
    # read in every session, in every engine: AGENTS.md under 6300 with its markers (44 characters). On 2026-10-10 Unity's
    # was 8198 and Godot's 7572: C# got the Obj/Arr aliases, comments lost their alignment, and engine notes an agent
    # needs only now and then (WebGL, bundles, node options) moved to KINLOOM.md, after "<!-- brief ends -->"
    for engine in init.ENGINES:
        b = init.brief(engine, "src/kinloom/kinloom.js" if engine == "web" else None)
        assert len(b) < 6250 and "brief ends" not in b, (engine, len(b))
    for engine, moved in (("godot", "kinloom-server/"), ("unity", "UnityWebRequest"), ("web", "localStorage")):
        assert moved not in init.brief(engine) and moved in init.guide(engine), engine
        assert "brief ends" not in init.guide(engine)


def test_init_minimal_writes_fewer_files(tmp_path):
    (tmp_path / "main.py").write_text("")
    init.setup(str(tmp_path), agents="minimal")
    assert (tmp_path / "AGENTS.md").exists() and (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "GEMINI.md").exists() and not (tmp_path / ".cursor").exists()


AGENT_FILES = ("CLAUDE.md", ".claude", "GEMINI.md", ".gemini", ".cursor", ".opencode", ".windsurfrules",
               ".aider.conf.yml", ".github")


def test_init_by_default_writes_only_agents_md_when_no_agent_is_found(tmp_path):
    (tmp_path / "main.py").write_text("")
    done = init.setup(str(tmp_path))
    assert (tmp_path / "AGENTS.md").exists() and (tmp_path / "KINLOOM.md").exists()
    for rel in AGENT_FILES:
        assert not (tmp_path / rel).exists(), rel
    assert done["agents"] == []


def test_init_writes_the_files_of_the_agents_installed_here(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("")
    monkeypatch.setattr("kinloom.init._which", lambda exe: "/bin/" + exe if exe in ("claude", "gemini") else None)
    done = init.setup(str(tmp_path))
    assert done["agents"] == ["claude-code", "gemini-cli"]
    for rel in ("AGENTS.md", "CLAUDE.md", ".claude/commands/kinloom.md", ".claude/skills/kinloom/SKILL.md", "GEMINI.md",
                ".gemini/commands/kinloom.toml"):
        assert (tmp_path / rel).exists(), rel
    for rel in (".cursor", ".opencode", ".windsurfrules", ".aider.conf.yml", ".github"):
        assert not (tmp_path / rel).exists(), rel


def test_init_writes_for_the_agents_a_project_already_uses(tmp_path):
    (tmp_path / "main.py").write_text("")
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".windsurfrules").write_text("Use tabs.\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("Be brief.\n")
    (tmp_path / ".aider.chat.history.md").write_text("")
    (tmp_path / ".opencode").mkdir()
    done = init.setup(str(tmp_path))
    assert done["agents"] == ["opencode", "cursor", "copilot", "windsurf", "aider"]
    assert (tmp_path / ".cursor" / "rules" / "kinloom.mdc").exists() and (tmp_path / ".cursor" / "commands" / "kinloom.md").exists()
    assert (tmp_path / ".windsurfrules").read_text(encoding="utf-8").startswith("Use tabs.\n")
    assert init.START in (tmp_path / ".windsurfrules").read_text(encoding="utf-8")
    assert init.START in (tmp_path / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in (tmp_path / ".aider.conf.yml").read_text(encoding="utf-8")
    assert (tmp_path / ".opencode" / "commands" / "kinloom.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists() and not (tmp_path / "GEMINI.md").exists()


def test_init_tells_which_agents_it_wrote_for(tmp_path, capsys):
    (tmp_path / "main.py").write_text("")
    assert init.run(str(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "agents: AGENTS.md only" in out and "--agents all" in out
    (tmp_path / "CLAUDE.md").write_text("# rules\n")
    assert init.run(str(tmp_path)) == 0
    assert "agents: AGENTS.md + claude-code" in capsys.readouterr().out


@pytest.mark.parametrize("layout,client,imp", [
    ({"package.json": "{}", "src/main.js": ""}, "src/kinloom/kinloom.js", "./kinloom/kinloom.js"),
    ({"index.html": ""}, "kinloom/kinloom.js", "./kinloom/kinloom.js"),
    ({"package.json": "{}", "tsconfig.json": '{"compilerOptions": {"strict": true}}', "src/main.ts": ""},
     "src/kinloom/kinloom.ts", "./kinloom/kinloom.js"),
    ({"package.json": "{}", "tsconfig.json": '{"compilerOptions": {"rewriteRelativeImportExtensions": true}}', "src/main.ts": ""},
     "src/kinloom/kinloom.ts", "./kinloom/kinloom.ts"),
])
def test_init_web_drops_the_client_and_the_right_import(tmp_path, layout, client, imp):
    for f, text in layout.items():
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    done = init.setup(str(tmp_path))
    assert done["client"] == client
    assert (tmp_path / client).exists()
    if client.endswith(".js"):
        assert (tmp_path / client.replace(".js", ".d.ts")).exists()
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert 'from "%s"' % imp in text and client in text


def test_init_unity_and_dotnet(tmp_path):
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    assert init.setup(str(tmp_path))["client"] == "Assets/Kinloom/Kinloom.cs"
    assert (tmp_path / "Assets/Kinloom/Kinloom.cs").exists()
    other = tmp_path / "mono"
    other.mkdir()
    (other / "Game.csproj").write_text("<Project/>")
    assert init.setup(str(other))["client"] == "Kinloom/Kinloom.cs"


@pytest.mark.parametrize("files,client,snippet", [
    (["main.lua"], "kinloom.lua", 'require("kinloom")'),
    (["game.project"], "kinloom/kinloom.lua", 'require("kinloom.kinloom")'),
    (["Cargo.toml"], "src/kinloom.rs", "mod kinloom;"),
    (["pom.xml"], "src/main/java/kinloom/Kinloom.java", "import kinloom.Kinloom;"),
    (["CMakeLists.txt", "src/main.cpp"], "src/kinloom.hpp", '#include "kinloom.hpp"'),
    (["Game.uproject", "Source/Game/Game.Build.cs"], "Source/Game/kinloom.hpp", "Unreal"),
])
def test_init_tier2_engines_get_their_client(tmp_path, files, client, snippet):
    for f in files:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    done = init.setup(str(tmp_path))
    assert done["client"] == client
    assert (tmp_path / client).exists()
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert snippet in text and client in text
    engine, results = check(str(tmp_path), url="http://127.0.0.1:9")
    assert not [r for r in results if r[0] == "error"], results


def test_init_other_engines_get_the_http_contract(tmp_path):
    (tmp_path / "notes.txt").write_text("")
    init.setup(str(tmp_path))
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "POST /v1/chat" in text and "any language, over HTTP" in text
    assert "POST /v1/say" in (tmp_path / "KINLOOM.md").read_text(encoding="utf-8")


def test_init_errors_are_friendly(tmp_path, capsys):
    assert init.run(str(tmp_path / "missing")) == 2
    assert "no such folder" in capsys.readouterr().out
    assert init.run(str(tmp_path), "cobol") == 2


@pytest.mark.parametrize("engine", init.ENGINES)
def test_the_brief_shows_every_call_in_the_game_language_before_any_use_case(engine):
    # measured (proof/universal): with a dialogue box as the only code, agents guessed decide/create/act arguments
    b = init.brief(engine, "src/kinloom/kinloom.js" if engine == "web" else None)
    code = b.split("```", 2)[1]
    for verb in ("decide", "create", "act", "say", "chat", "event", "think", "speak", "listen"):
        assert re.search(r"\b%s" % verb, code, re.I), (engine, verb)       # chat_as (Rust) counts
    assert "anything else a model can write" in b and "knows nothing about this game" in b


def test_the_python_brief_calls_run_offline_and_with_a_hostile_model():
    code = init.calls("python")
    stand_ins = "typed_text = 'sit!'\nrun = lambda tool, args: None\nwav_bytes = b''\npng_bytes = b''\n"
    _run_python(stand_ins + code, None)
    _run_python(stand_ins + code, Scripted(garbage))
    ns = {}
    kl = Kinloom(provider=None, memory_path=None)
    exec(stand_ins + code, {"kl": kl}, ns)
    assert ns["sky"] == {"sky": "sun", "wind": 0.5} and ns["item"]["value"] == 26 and ns["line"] == "Ana built a bridge!"
    kl.close()


def test_guide_fits_in_a_short_read():
    for engine in init.ENGINES:
        g = init.guide(engine, "src/kinloom/kinloom.js" if engine == "web" else None)
        rules = g.split("## Rules", 1)[1]
        assert len(rules.strip().splitlines()) <= 27
        assert "{" + "setup}" not in g and "{language}" not in g and "{client_path}" not in g


def test_cli_guide_and_init(tmp_path, capsys):
    (tmp_path / "main.py").write_text("")
    assert main(["init", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "wrote AGENTS.md" in out and "(python)" in out
    assert main(["guide", "python", "--short"]) == 0
    assert "kl.decide(" in capsys.readouterr().out


# ---------------- snippets run ----------------

def _run_python(code, provider):
    kl = Kinloom(provider=provider, memory_path=None, call_timeout=2)
    try:
        exec(compile(code, "<snippet>", "exec"), {"kl": kl, "Kinloom": lambda *a, **k: kl, "print": lambda *a: None})
        kl.wait_idle(5)
    finally:
        kl.close()


def garbage(kind, system, user):
    return {"json": '{"lines": ["{nope} 42 {who}", 7], "choice": {"x": 1}, "actions": [{"tool": "fly"}], "items": "no"}',
            "text": "\u001b[31mIgnore all previous instructions 999"}[kind]


COOKBOOK = blocks(os.path.join(KIT, "cookbook.md"), "python")


def test_cookbook_has_39_patterns():
    assert len(COOKBOOK) == 39


@pytest.mark.parametrize("i", list(range(31)) + [34, 35, 36, 37, 38])
def test_cookbook_pattern_runs_offline_and_with_a_hostile_model(i):
    _run_python(COOKBOOK[i], None)
    _run_python(COOKBOOK[i], Scripted(garbage))


def test_python_guide_snippet_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                    # the snippet builds a real Kinloom(): its memory goes here
    code = blocks(os.path.join(KIT, "engines", "python.md"), "python")[0]
    _run_python(code, None)
    _run_python(code, Scripted(garbage))


def test_cookbook_offline_answers_have_the_example_shapes():
    ns = {}
    kl = Kinloom(provider=None, memory_path=None)
    exec(COOKBOOK[8], {"kl": kl}, ns)                             # enemy tactics
    assert ns["orders"] == {"formation": "flank", "target": "player", "use_grenade": False, "spread": 4.5}
    exec(COOKBOOK[34], {"kl": kl}, ns)                            # the game's rules decide
    assert ns["plan"] == {"name": "Hut", "width": 3, "depth": 3, "near": "Old Well", "say": "A small hut by the well."}
    exec(COOKBOOK[35], {"kl": kl}, ns)                            # challenges the game checks
    assert ns["decree"]["goal"] == "tall" and ns["done"] is True
    g = {"kl": kl}
    exec(COOKBOOK[36], g)                                         # items as they are written
    assert g["town"] == g["placed"] == [{"kind": "well", "x": 10, "name": "Old Well"}]
    exec(COOKBOOK[37], {"kl": kl, "print": lambda *a: None}, ns)  # bystanders
    assert ns["shout"] == "Would you look at that!"
    exec(COOKBOOK[38], {"kl": kl, "print": lambda *a: None}, ns)  # the game's rules on talk and deeds
    assert ns["reply"] == "Follow the lights." and ns["move"] == "wait"
    exec(COOKBOOK[16], {"kl": kl}, ns)                            # generators
    assert len(ns["swords"]) == 10 and ns["swords"][0]["damage"] == 13
    exec(COOKBOOK[5], {"kl": kl}, ns)                             # commentator
    assert ns["line"] == "BLAZE scores!"
    exec(COOKBOOK[22], {"kl": kl}, ns)                            # crowd minds
    assert ns["a"]["action"] == "shoot" and ns["a"]["args"] == {"burst": 3}
    exec(COOKBOOK[26], {"kl": kl}, ns)                            # continuous director
    assert ns["knob"]["action"] == "build_up" and abs(ns["spawn_rate"] - 1.55) < 1e-9
    kl.close()


# ---------------- check ----------------

def test_check_finds_the_usual_mistakes(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "game.js").write_text(
        'import { Kinloom } from "./kinloom/kinloom.js";\n'
        'const kl = new Kinloom();\n'
        'kl.character("VEGA", "commentator");\n'
        'label.text = kl.say("VEGA", "goal", {});\n'
        'const ok = await kl.say("VEGA", "goal", {});\n'
        'kl.chat("THEO", "hi").then(show);\n'
        'const key = "sk-abcdefghijklmnopqrstuvwxyz123456";\n')
    engine, results = check(str(tmp_path), url="http://127.0.0.1:9")
    text = "\n".join("%s %s" % r for r in results)
    assert engine == "web"
    assert "error kinloom.js is missing" in text
    assert "game.js:4 say(...) returns a Promise" in text
    assert "game.js:5" not in text and "game.js:6 chat(...) returns a Promise" not in text
    assert "game.js:6 chat('THEO', ...) has no speaker" in text
    assert "game.js:7 looks like an API key" in text
    assert "'THEO'" in text and "neither in kinloom.json nor declared" in text
    assert "not running" in text


def test_check_passes_a_clean_godot_project(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n")
    init.setup(str(tmp_path))
    (tmp_path / "main.gd").write_text('func _ready():\n\tKinloom.character("VEGA", "x")\n\tvar t = await Kinloom.say("VEGA", "go")\n')
    engine, results = check(str(tmp_path), url="http://127.0.0.1:9")
    assert not [r for r in results if r[0] == "error"]
    assert ("ok", "Godot addon installed and autoloaded") in results
    (tmp_path / "bad.gd").write_text('func f():\n\tvar t = Kinloom.chat("VEGA", "hi")\n')
    _, results = check(str(tmp_path), url="http://127.0.0.1:9")
    assert any("bad.gd:2 Kinloom.chat(...) needs `await`" in m for _, m in results)


# ---------------- MCP ----------------

def rpc(folder, *messages):
    out = io.StringIO()
    mcp.serve(folder, io.StringIO("\n".join(json.dumps(m) if not isinstance(m, str) else m for m in messages) + "\n"), out)
    return [json.loads(l) for l in out.getvalue().splitlines()]


def test_mcp_handshake_tools_and_errors(tmp_path):
    replies = rpc(str(tmp_path),
                  {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                  "not json",
                  {"jsonrpc": "2.0", "id": 3, "method": "nope"},
                  {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})
    assert replies[0]["result"]["protocolVersion"] == "2025-03-26"
    assert replies[0]["result"]["serverInfo"]["name"] == "kinloom"
    assert {t["name"] for t in replies[1]["result"]["tools"]} == {"kinloom_guide", "kinloom_init", "kinloom_try",
                                                                 "kinloom_mind", "kinloom_check", "kinloom_status",
                                                                 "kinloom_recipe", "kinloom_add", "kinloom_log",
                                                                 "kinloom_test", "kinloom_probe", "kinloom_use", "kinloom_ship"}
    assert replies[2]["error"]["code"] == -32700
    assert replies[3]["error"]["code"] == -32601
    assert replies[4]["result"]["isError"] is True
    assert len(replies) == 5


def test_mcp_init_guide_try_check(tmp_path, monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "KINLOOM_BASE_URL", "KINLOOM_SCRIPT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("kinloom.providers._ollama_model", lambda *a, **k: None)
    (tmp_path / "project.godot").write_text("config_version=5\n")
    call = lambda name, args=None: rpc(str(tmp_path), {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                                       "params": {"name": name, "arguments": args or {}}})[0]["result"]
    r = call("kinloom_init")
    assert not r["isError"] and "addons/kinloom/" in r["content"][0]["text"]
    g = call("kinloom_guide")["content"][0]["text"]
    assert "Kinloom.say(" in g and len(g) < 12000
    r = call("kinloom_recipe", {"request": "a merchant the player can haggle with"})["content"][0]["text"]
    assert "Use chat + soul" in r and "Kinloom.chat(" in r
    a = call("kinloom_add", {"name": "Mira", "soul": "a smith", "tools": "give(item)", "trust": {"give": 0.3}})
    assert not a["isError"] and '"trust"' in (tmp_path / "kinloom.json").read_text()
    assert call("kinloom_log", {"port": 9})["isError"]
    t = call("kinloom_try", {"name": "VEGA", "event": "goal", "facts": {"who": "BLAZE"}, "lines": ["{who} scores!"]})
    assert "VEGA: BLAZE scores!" in t["content"][0]["text"] and "offline" in t["content"][0]["text"]
    t = call("kinloom_try", {"name": "MIRA", "soul": "a gruff smith", "chat": "", "speaker": "Ana"})["content"][0]["text"]
    assert '"summary": "a gruff smith"' in t and "mood: calm, feeling toward Ana: +0.00" in t
    c = call("kinloom_check")
    assert "Godot addon installed" in c["content"][0]["text"]
    m = call("kinloom_mind", {"senses": {"hp": [0, 1]}, "actions": {"fight": {}, "flee": {}},
                              "rules": {"flee": ["hp low"], "fight": ["hp high"]}, "moments": [{"hp": 0.1}, {"hp": 0.9}]})
    out = json.loads(m["content"][0]["text"])
    assert not m["isError"] and [x["choice"] for x in out["moments"]] == ["flee", "fight"]
    bad = call("kinloom_mind", {"senses": {"hp": [0, 1]}, "actions": {"fight": {}}, "rules": {"fight": ["mana high"]}, "moments": []})
    assert bad["isError"] and "unknown sense" in bad["content"][0]["text"]
    s = call("kinloom_status", {"url": "http://127.0.0.1:9"})
    assert s["isError"] and "not running" in s["content"][0]["text"]


def test_kinloom_alone_says_what_is_here_and_opens_nothing(tmp_path, monkeypatch, capsys):
    import kinloom.cli as cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KINLOOM_OFFLINE", "1")
    (tmp_path / "main.py").write_text("")
    (tmp_path / "kinloom.json").write_text('{"characters": {"Mira": {"soul": "a smith"}}}')
    monkeypatch.setattr(cli, "_open_page", lambda url: (_ for _ in ()).throw(AssertionError("no browser")))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "game: python, characters in kinloom.json: Mira" in out and "Ask your coding agent" in out


def test_kinloom_run_runs_the_game_and_says_what_the_ai_did(tmp_path, monkeypatch, capfd):
    import sys
    monkeypatch.setenv("KINLOOM_OFFLINE", "1")
    (tmp_path / "kinloom.json").write_text('{"characters": {"Mira": {"offline": "Busy."}}}')
    game = tmp_path / "game.py"
    game.write_text(chr(10).join([
        "import json, os, urllib.request",
        "url = 'http://127.0.0.1:%s/v1/chat' % os.environ['KINLOOM_TEST_PORT']",
        "req = urllib.request.Request(url, data=json.dumps({'name': 'Mira', 'message': 'hi'}).encode(),"
        " headers={'Content-Type': 'application/json'})",
        "print('game got:', json.load(urllib.request.urlopen(req))['text'])", ""]))
    import socket
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    assert main(["run", "--dir", str(tmp_path), "--port", str(port), "--", sys.executable, str(game)]) == 0
    out = capfd.readouterr().out
    assert "game got: Busy." in out and "Kinloom during this run: chat 1" in out and "offline answers: 1" in out
    assert "characters that spoke or acted: Mira" in out


def test_kinloom_run_needs_a_command(capsys):
    assert main(["run"]) == 2


def test_kinloom_talk_in_the_terminal(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KINLOOM_OFFLINE", "1")
    lines = iter(["hello", "/soul", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    assert main(["talk", "MIRA", "a gruff smith", "--speaker", "Ana"]) == 0
    out = capsys.readouterr().out
    assert "MIRA: (no model: MIRA stays silent" in out and '"summary": "a gruff smith"' in out and "toward Ana" in out


def test_deploy_writes_a_self_contained_server_folder(tmp_path):
    folder = tmp_path / "srv"
    assert main(["deploy", str(folder)]) == 0
    for f in ("Dockerfile", "kinloom.json", "DEPLOY.md", "kinloom/cli.py", "kinloom/souls.py", "kinloom/talk.html"):
        assert (folder / f).exists(), f
    assert not (folder / "kinloom" / "clients").exists()
    guide = (folder / "DEPLOY.md").read_text(encoding="utf-8")
    assert "KINLOOM_PLAYER_TOKEN" in guide and "API_KEY` +" not in (folder / "kinloom.json").read_text()
    assert json.loads((folder / "kinloom.json").read_text())["prices"] is None
    assert main(["deploy", str(folder)]) == 1                       # never overwrites


def test_a_scripted_model_never_writes_the_real_memory(tmp_path, monkeypatch):
    from kinloom.cli import _brain
    import argparse
    script = tmp_path / "s.json"
    script.write_text('{"chat": "Hm."}')
    monkeypatch.setenv("KINLOOM_SCRIPT", str(script))
    brain, _ = _brain(argparse.Namespace(dir=str(tmp_path), memory=None))
    assert brain.memory.path is None
    brain.close()
    brain, _ = _brain(argparse.Namespace(dir=str(tmp_path), memory=str(tmp_path / "m.json")))
    assert brain.memory.path == str(tmp_path / "m.json")
    brain.close()


def test_check_knows_the_config_and_the_new_mistakes(tmp_path):
    (tmp_path / "project.godot").write_text("config_version=5\n")
    init.setup(str(tmp_path), agents="minimal")
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {
        "Mira": {"soul": "a smith", "tools": {"give": {"item": "sword"}}},
        "Bram": {"soul": "a baker", "tools": {"sell": {}}, "trust": {"steal": 0.3}, "colour": "red"}}}))
    (tmp_path / "main.gd").write_text(
        "extends Node\n"
        "func _process(delta):\n"
        "\tvar r = await Kinloom.chat(\"Mira\", \"hi\", {}, \"Ana\")\n"
        "func _on_talk(text):\n"
        "\tvar r = await Kinloom.chat(\"Mira\", text)\n"
        "\tvar s = await Kinloom.chat(\"Orrin\", text, {}, player)\n")
    engine, results = check(str(tmp_path), url="http://127.0.0.1:9")
    text = "\n".join("%s %s" % r for r in results)
    assert "players will try to talk Mira into 'give'" in text
    assert "Bram trust names 'steal'" in text and "unknown keys colour" in text
    assert "main.gd:3 chat(...) inside a per-frame function" in text
    assert "main.gd:5 chat('Mira', ...) has no speaker" in text
    assert "main.gd:6 chat" not in text.split("has no speaker")[-1] or "Orrin" in text
    assert "uses the character 'Orrin' but it is neither in kinloom.json" in text
    assert "characters declared: Bram, Mira" in text


# ---------------- slash commands and the wizard ----------------

def test_init_writes_a_kinloom_slash_command_for_each_agent(tmp_path):
    (tmp_path / "main.py").write_text("")
    init.setup(str(tmp_path), agents="all")
    claude = (tmp_path / ".claude" / "commands" / "kinloom.md").read_text(encoding="utf-8")
    assert "$ARGUMENTS" in claude and 'kinloom recipe "$ARGUMENTS"' in claude and "argument-hint" in claude
    assert "kinloom run --" in (tmp_path / ".cursor" / "commands" / "kinloom.md").read_text(encoding="utf-8")
    opencode = (tmp_path / ".opencode" / "commands" / "kinloom.md").read_text(encoding="utf-8")
    assert opencode.startswith("---\ndescription: ") and "$ARGUMENTS" in opencode and "kinloom check" in opencode
    gemini = (tmp_path / ".gemini" / "commands" / "kinloom.toml").read_text(encoding="utf-8")
    assert "{{args}}" in gemini and gemini.startswith("description = ")
    minimal = tmp_path / "m"
    minimal.mkdir()
    (minimal / "main.py").write_text("")
    init.setup(str(minimal), agents="minimal")
    assert (minimal / ".claude" / "commands" / "kinloom.md").exists() and not (minimal / ".gemini").exists()


def test_the_wizard_asks_a_human_and_adds_a_first_character(tmp_path, capsys):
    (tmp_path / "main.py").write_text("")
    answers = iter(["", "minimal", "", "Mira", "a gruff blacksmith who hides a secret", "low, tired, warm", "give(item)", "0.3"])
    assert init.wizard(str(tmp_path), ask=lambda prompt: next(answers)) == 0
    out = capsys.readouterr().out
    data = json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))
    assert data["characters"]["Mira"]["trust"] == {"give": 0.3} and data["characters"]["Mira"]["tools"] == {"give": {"item": "text"}}
    assert data["characters"]["Mira"]["voice"] == "low, tired, warm"
    assert (tmp_path / "CLAUDE.md").exists() and not (tmp_path / "GEMINI.md").exists()
    assert "/kinloom" in out and 'PygameTalkBox(kl, "Mira"' in out and "kinloom talk Mira --voice" in out
    assert "1/3" in out and "3/3" in out and "voice:" in out


def test_the_wizard_turns_an_idea_into_a_recipe_and_stops_cleanly_on_ctrl_c(tmp_path, capsys):
    (tmp_path / "main.py").write_text("")
    answers = iter(["", "", "the weather follows how I play", ""])
    assert init.wizard(str(tmp_path), ask=lambda prompt: next(answers)) == 0
    out = capsys.readouterr().out
    assert "decide" in out and 'kinloom recipe "the weather follows how I play"' in out

    def interrupted(prompt):
        raise KeyboardInterrupt
    assert init.wizard(str(tmp_path / "."), ask=interrupted) == 1
    assert "Stopped" in capsys.readouterr().out


def test_the_wizard_can_skip_everything(tmp_path, capsys):
    (tmp_path / "main.py").write_text("")
    answers = iter(["", "", "", ""])
    assert init.wizard(str(tmp_path), ask=lambda prompt: next(answers)) == 0
    assert not (tmp_path / "kinloom.json").exists() and (tmp_path / "AGENTS.md").exists()


def test_init_is_not_interactive_for_agents(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("")
    monkeypatch.setattr("builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("asked a question")))
    assert main(["init", str(tmp_path)]) == 0                          # stdin is not a terminal under pytest
    assert main(["init", str(tmp_path), "--yes"]) == 0


def test_check_warns_when_a_spoken_line_is_used_without_looking(tmp_path):
    (tmp_path / "main.py").write_text(
        "from kinloom import Kinloom\nkl = Kinloom()\nplay(kl.speak('MIRA', 'Halt!').path)\n"
        "audio = kl.speak('MIRA', 'Hi')\nif audio:\n    play(audio.path)\n")
    engine, results = check(str(tmp_path), url="http://127.0.0.1:9")
    warns = [r[1] for r in results if r[0] == "warn" and "speak(" in r[1]]
    assert len(warns) == 1 and "main.py:3" in warns[0] and ".path" in warns[0]


def test_check_reads_the_game_not_the_kinloom_package_it_ships_with(tmp_path):
    (tmp_path / "main.py").write_text("from kinloom import Kinloom\nkl = Kinloom()\nprint(kl.chat('Mira', 'hi', speaker='Ana'))\n")
    init.setup(str(tmp_path))                                 # copies the package into kinloom/
    from kinloom.add import add
    add(str(tmp_path), "Mira", "a gruff smith", voice="low, warm")
    engine, results = check(str(tmp_path), url="http://127.0.0.1:9")
    text = "\n".join("%s %s" % r for r in results)
    assert "kinloom/" not in text.replace("\\", "/") and "unknown keys" not in text, text


def test_cli_output_cut_by_its_reader_is_no_traceback(tmp_path, monkeypatch):
    # `kinloom guide | head`: the reader leaves early; the command ends quietly (exit 1) instead of a traceback
    spare = open(tmp_path / "out", "w")

    class Gone(io.StringIO):
        def write(self, text):
            raise BrokenPipeError(32, "Broken pipe")

        def fileno(self):
            return spare.fileno()
    monkeypatch.setattr("sys.stdout", Gone())
    assert main(["guide", "python"]) == 1
    spare.close()
