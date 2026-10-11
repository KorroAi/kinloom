"""`kinloom hooks`: where Kinloom plugs into a .NET game with no source (REA is faked: a script printing its answer)."""
import json
import os
import struct
import subprocess
import sys

import pytest

from kinloom import cli, mcp, mod
from kinloom.recipe import recipe


def pe(managed):
    """The smallest file is_managed reads: an MZ header, a PE32 header, the CLI data directory set or not."""
    head = bytearray(512)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x80)
    head[0x80:0x84] = b"PE\0\0"
    opt = 0x80 + 24
    struct.pack_into("<H", head, opt, 0x10B)
    if managed:
        struct.pack_into("<II", head, opt + 96 + 14 * 8, 0x2008, 0x48)
    return bytes(head)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def method(owner, name, params, returns, token, flags=0x86):
    return {"token": "0x0600%04x" % token, "declaring_type": owner, "name": name, "flags": flags,
            "signature": {"parameter_types": params, "return_type": returns}}


# What REA's inspect-managed-members says of proof/mod's Lantern Row (the fields Kinloom reads).
LANTERN = {
    "types": [{"token": "0x02000001", "name": "<Module>", "full_name": "<Module>"},
              {"token": "0x02000002", "name": "Player", "full_name": "LanternRow.Player"},
              {"token": "0x02000003", "name": "Shopkeeper", "full_name": "LanternRow.Shopkeeper"},
              {"token": "0x02000004", "name": "Guard", "full_name": "LanternRow.Guard"},
              {"token": "0x02000005", "name": "<>c__DisplayClass0_0", "full_name": "LanternRow.<>c__DisplayClass0_0"}],
    "methods": [method("LanternRow.Player", ".ctor", [], "void", 1),
                method("LanternRow.Shopkeeper", "Greet", ["class:8"], "string", 2),
                method("LanternRow.Shopkeeper", "Answer", ["class:8", "string"], "string", 3),
                method("LanternRow.Guard", "Shout", ["string"], "void", 4),
                method("LanternRow.Guard", "Patrol", ["i4"], "void", 5),
                method("LanternRow.Guard", "<Patrol>b__0", ["string"], "string", 6),
                method("LanternRow.Program", "Main", ["szarray:string"], "void", 7, 0x96)],
    "call_edges": [{"caller": "LanternRow.Guard.Shout", "target_name": "WriteLine"},
                   {"caller": "LanternRow.Guard.Patrol", "target_name": "Shout"}],
}


@pytest.fixture
def fake_rea(tmp_path, monkeypatch):
    """KINLOOM_REA = a script that answers like REA (or fails with exit 3 when told to)."""
    def use(answer=None, exit_code=0):
        out = tmp_path / "answer.json"
        out.write_text(json.dumps({"provider": {"version": "1"}, "normalized_result": answer or LANTERN}), encoding="utf-8")
        script = tmp_path / "rea.py"
        script.write_text("import sys\nif sys.argv[1] != 'inspect-managed-members' or sys.argv[3] != '--json': sys.exit(9)\n"
                          "sys.stdout.write(open(%r, encoding='utf-8').read())\n"
                          "if %d: sys.stderr.write('REA broke'); sys.exit(%d)\n" % (str(out), exit_code, exit_code),
                          encoding="utf-8")
        monkeypatch.setenv("KINLOOM_REA", '"%s" "%s"' % (sys.executable, script))
    return use


def test_is_managed_tells_net_from_native_and_from_anything_else(tmp_path):
    assert mod.is_managed(write(str(tmp_path / "a.dll"), pe(True))) is True
    assert mod.is_managed(write(str(tmp_path / "b.exe"), pe(False))) is False
    assert mod.is_managed(write(str(tmp_path / "c.dll"), b"not a program")) is None
    assert mod.is_managed(str(tmp_path / "missing.dll")) is None


def test_a_unity_mono_folder_is_read_through_assembly_csharp(tmp_path):
    write(str(tmp_path / "Game.exe"), pe(False))
    code = write(str(tmp_path / "Game_Data" / "Managed" / "Assembly-CSharp.dll"), pe(True))
    write(str(tmp_path / "Game_Data" / "Managed" / "UnityEngine.dll"), pe(True))
    assert mod.find_code(str(tmp_path)) == code


def test_a_net_folder_gives_the_game_s_own_assembly_not_the_framework(tmp_path):
    write(str(tmp_path / "System.Runtime.dll"), pe(True) + b"x" * 5000)
    write(str(tmp_path / "MonoGame.Framework.dll"), pe(True) + b"x" * 5000)
    write(str(tmp_path / "steam_api64.dll"), pe(False) + b"x" * 9000)
    game = write(str(tmp_path / "LanternRow.dll"), pe(True))
    assert mod.find_code(str(tmp_path)) == game


def test_il2cpp_native_and_missing_say_what_to_do_instead(tmp_path):
    write(str(tmp_path / "il2cpp" / "GameAssembly.dll"), pe(False))
    write(str(tmp_path / "il2cpp" / "Game_Data" / "il2cpp_data" / "x.dat"), b"")
    with pytest.raises(mod.HookError, match="IL2CPP"):
        mod.find_code(str(tmp_path / "il2cpp"))
    native = write(str(tmp_path / "native" / "game.exe"), pe(False))
    with pytest.raises(mod.HookError, match="native code"):
        mod.find_code(native)
    with pytest.raises(mod.HookError, match="No .NET game code"):
        mod.find_code(str(tmp_path / "native"))
    with pytest.raises(mod.HookError, match="no such file"):
        mod.find_code(str(tmp_path / "nowhere"))


def test_candidates_rank_where_the_game_makes_text_and_pick_the_call():
    found = mod.candidates(LANTERN)
    assert [(c["type"], c["method"], c["call"]) for c in found] == [
        ("LanternRow.Guard", "Shout", "say"), ("LanternRow.Shopkeeper", "Answer", "chat"),
        ("LanternRow.Shopkeeper", "Greet", "say")]
    assert found[1]["params"] == ["LanternRow.Player", "string"]          # class:8 = TypeDef row 2
    assert "shows it: WriteLine" in found[0]["why"] and "returns text" in found[2]["why"]
    names = [c["method"] for c in found]
    assert ".ctor" not in names and not any("<" in n for n in names) and "Patrol" not in names


def test_patches_keep_the_game_s_value_as_the_offline_answer():
    shout, answer, greet = mod.candidates(LANTERN)
    p = mod.patch(greet, "MARLO")
    assert 'AccessTools.Method("LanternRow.Shopkeeper:Greet")' in p and "Postfix(ref string __result)" in p
    assert 'var said = Mod.Kl.Say("MARLO", "greet", new Obj {' in p and "if (said.Length > 0) __result = said;" in p
    assert '["greet"] = new Obj { ["when"]' in p and "{line}" not in p   # the game's text is never a fact
    p = mod.patch(answer, "MARLO")
    assert 'Chat("MARLO", (string)__args[1]' in p and "if (reply.Length > 0) __result = reply;" in p
    p = mod.patch(shout)
    assert "Prefix(object[] __args)" in p and "if (said.Length > 0) __args[0] = said;" in p
    assert p.count("{") == p.count("}")


def test_a_choice_and_content_get_decide_and_create():
    found = mod.candidates({"types": [], "methods": [
        method("Arena.EnemyBrain", "ChooseAttack", ["r4"], "i4", 1),
        method("Arena.Dungeon", "GenerateRoom", ["i4"], "class:12", 2),
        method("Arena.Dungeon", "Generated", [], "void", 3)]})
    calls = {c["method"]: c["call"] for c in found}
    assert calls == {"ChooseAttack": "decide", "GenerateRoom": "create"}
    assert "Postfix(ref int __result)" in mod.patch(found[0]) or "Postfix(ref int __result)" in mod.patch(found[1])


def test_hooks_reads_the_game_with_rea_and_prints_the_patch(tmp_path, fake_rea, capsys):
    fake_rea()
    game = write(str(tmp_path / "LanternRow.dll"), pe(True))
    assert cli.main(["hooks", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert game in out and "1. LanternRow.Guard.Shout(string) -> void   [say]" in out
    assert "2. LanternRow.Shopkeeper.Answer(LanternRow.Player, string) -> string   [chat]" in out
    assert 'AccessTools.Method("LanternRow.Guard:Shout")' in out
    assert cli.main(["hooks", game, "--json", "--top", "1"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["code"] == game and len(r["candidates"]) == 1 and r["patch"].startswith("[HarmonyPatch]")


def test_without_rea_hooks_says_how_to_get_it(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("KINLOOM_REA", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    write(str(tmp_path / "LanternRow.dll"), pe(True))
    assert cli.main(["hooks", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "REA is not installed" in out and "npm install --global rea-agents" in out and "KINLOOM_REA" in out
    assert mod.rea_command() is None


def test_rea_failing_or_answering_nonsense_is_a_clear_error(tmp_path, fake_rea):
    game = write(str(tmp_path / "LanternRow.dll"), pe(True))
    fake_rea(exit_code=3)
    with pytest.raises(mod.HookError, match="REA failed .*exit 3.*REA broke"):
        mod.report(game)
    fake_rea(answer={"types": []})
    with pytest.raises(mod.HookError, match="no methods"):
        mod.report(game)


def test_no_method_name_says_what_to_do(tmp_path, fake_rea, capsys):
    fake_rea(answer={"types": [], "methods": [method("a.b", "c", [], "void", 1)]})
    write(str(tmp_path / "Obf.dll"), pe(True))
    assert cli.main(["hooks", str(tmp_path)]) == 0
    assert "obfuscated" in capsys.readouterr().out


def test_guide_and_mcp_tool(tmp_path, fake_rea):
    assert "Harmony" in mod.guide() and "IL2CPP" in mod.guide() and "proof/mod" in mod.guide()
    assert cli.main(["hooks", "--guide"]) == 0
    assert any(t["name"] == "kinloom_hooks" for t in mcp.TOOLS)
    r = mcp.call(str(tmp_path), "kinloom_hooks", {})
    assert not r.get("isError") and "mod API" in r["content"][0]["text"]
    r = mcp.call(str(tmp_path), "kinloom_hooks", {"game": "missing"})
    assert r.get("isError") and "no such file" in r["content"][0]["text"]
    fake_rea()
    write(str(tmp_path / "game" / "LanternRow.dll"), pe(True))
    r = mcp.call(str(tmp_path), "kinloom_hooks", {"game": "game", "top": 2})
    assert not r.get("isError") and "LanternRow.Shopkeeper.Answer" in r["content"][0]["text"]


def test_recipe_routes_a_mod_request_to_hooks():
    text = recipe("a mod for a Unity game I don't have the source of: patch the shopkeeper with Harmony", "dotnet")
    assert "kinloom hooks" in text and "Harmony patch" in text
    assert "kinloom hooks" not in recipe("make the enemies smarter", "python")


def test_doctor_says_whether_rea_is_there(tmp_path, fake_rea, capsys):
    fake_rea()
    cli.main(["doctor", "--dir", str(tmp_path)])
    assert "mods (kinloom hooks): REA found" in capsys.readouterr().out


def test_the_guide_ships_in_the_package():
    assert os.path.isfile(mod.GUIDE)
    toml = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml"),
                encoding="utf-8").read()
    assert "kit/*.md" in toml or "kit/**" in toml or '"kit' in toml


def test_python_m_kinloom_hooks_runs(tmp_path, fake_rea):
    fake_rea()
    write(str(tmp_path / "LanternRow.dll"), pe(True))
    src = os.path.dirname(os.path.dirname(os.path.abspath(mod.__file__)))
    r = subprocess.run([sys.executable, "-m", "kinloom", "hooks", str(tmp_path), "--top", "1"], capture_output=True,
                       text=True, env=dict(os.environ, PYTHONPATH=src), timeout=60)
    assert r.returncode == 0 and "LanternRow.Guard.Shout" in r.stdout, r.stderr
