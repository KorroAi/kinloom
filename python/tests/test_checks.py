"""kinloom test (the game's AI checked like code) and kinloom probe (a character played like a tester would)."""
import json
import re

import pytest

from kinloom import probe, testing
from kinloom.cli import main
from test_brain import make, model
from test_souls import reply


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ---------------- the file ----------------

@pytest.mark.parametrize("data, problem", [
    ({"tests": [{"chat": ["A", "hi"], "say": ["A", "e"]}]}, "one verb per step"),
    ({"tests": [{"dance": ["A"]}]}, "one verb per step"),
    ({"tests": [{"chat": "A"}]}, "arguments as a list"),
    ({"tests": [{"chat": ["A", "hi"], "expect": {"shorter": 3}}]}, "unknown checks shorter"),
    ({"tests": [{"chat": ["A", "hi"], "repeat": 0}]}, "repeat"),
    ({"tests": "nope"}, "expected"),
])
def test_a_wrong_file_says_where_and_what(tmp_path, data, problem):
    path = write(tmp_path, "t.json", data)
    with pytest.raises(testing.TestFileError, match=problem):
        testing.load(path)


def test_checks_say_what_failed():
    assert testing.check({"max_words": 3}, "one two three four") == ["4 words, at most 3"]
    assert testing.check({"contains": ["sword"], "not": ["AI"]}, "As an AI I have no Sword") == ["contains 'AI'"]
    assert testing.check({"source": ["model", "prepared"]}, "x", source="offline") == ["source 'offline', expected 'model' or 'prepared'"]
    assert testing.check({"different": True}, "Hi.", earlier=["Hi."]) == ["said again: 'Hi.'"]
    assert testing.check({"tools": ["give"], "not_tools": ["burn"]}, "x", actions=[("burn", {})]) == [
        "no 'give' action (actions: burn)", "took the 'burn' action"]
    assert testing.check({"equals": {"a": 1}}, {"a": 1}) == []
    assert testing.check({"not_empty": True}, "") == ["empty"]
    assert testing.check({"max_chars": 5}, "toolong") == ["7 characters, at most 5"]


# ---------------- running ----------------

def test_steps_run_on_the_verbs_and_report(tmp_path):
    p = model(chat=lambda s, u: reply("Fine, thanks." if "How are you" in u else "Welcome, traveller."),
              act={"actions": [{"tool": "give", "args": {"item": "bread"}}]},
              decide={"strategy": "block"}, create={"title": "Find the cat", "reward": 20})
    kl = make(p)
    kl.character("Mira", "a baker", tools={"give": {"item": "bread"}})
    steps = [
        {"chat": ["Mira", ""], "expect": {"not": ["as an AI"], "source": "model"}},
        {"chat": ["Mira", "How are you?"], "repeat": 2, "expect": {"different": True}},
        {"act": ["Mira", {"player_near": True}], "expect": {"tools": ["give"]}},
        {"decide": ["Mira", {"hungry": True}, {"strategy": ["attack", "block"]}], "expect": {"equals": {"strategy": "block"}}},
        {"create": ["a quest", {"title": "x", "reward": [10, 50]}], "expect": {"contains": ["cat"]}},
        {"event": ["the player stole bread"]},
        {"say": ["Mira", "nothing"], "options": {"facts": {}}, "expect": {"not_empty": True}},
    ]
    report = testing.run(steps, kl, wait=5, out=None)
    by = {r["name"]: r for r in report["results"]}
    assert report["failed"] == 2, report
    assert by["chat [\"Mira\", \"How are you?\"] (2)"]["failed"] == ["said again: 'Fine, thanks.'"]
    assert [r for r in report["results"] if r["verb"] == "say"][0]["failed"] == ["empty"]
    assert all(r["ok"] for r in report["results"] if r["verb"] in ("act", "decide", "create", "event"))


def test_a_create_not_shaped_like_its_example_fails(tmp_path):
    kl = make(None)
    report = testing.run([{"create": ["x", {"a": 1}], "options": {"count": 2}}], kl, wait=1, out=None)
    assert report["passed"] == 1
    report = testing.run([{"chat": ["Nobody", "hi"], "options": {"no_such_option": 1}}], kl, wait=1, out=None)
    assert report["failed"] == 1 and "TypeError" in report["results"][0]["failed"][0]


def test_kinloom_test_records_then_replays_without_a_model(tmp_path, monkeypatch, capsys):
    script = write(tmp_path, "script.json", {"chat": "Welcome to the forge.", "lines": {"lines": ["Hot iron!"]}})
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {"personality": "a smith", "offline": "Busy."}}}),
                                          encoding="utf-8")
    write(tmp_path, "kinloom.tests.json", {"tests": [
        {"chat": ["Mira", "hello"], "expect": {"contains": ["forge"], "source": "model"}}]})
    rec = str(tmp_path / "answers.json")
    monkeypatch.setenv("KINLOOM_SCRIPT", script)          # the "model" of this test
    assert main(["test", "--dir", str(tmp_path), "--record", rec]) == 0
    assert "Welcome to the forge." in json.loads(open(rec, encoding="utf-8").read())["chat"]
    monkeypatch.delenv("KINLOOM_SCRIPT")
    capsys.readouterr()
    assert main(["test", "--dir", str(tmp_path), "--replay", rec]) == 0
    assert "replay of" in capsys.readouterr().out
    assert main(["test", "--dir", str(tmp_path), "--offline"]) == 1      # offline: "Busy.", no forge, source offline
    assert main(["test", "--dir", str(tmp_path), "--offline", "--json"]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["failed"] == 1 and out["results"][0]["value"] == "Busy."
    assert main(["test", "--dir", str(tmp_path), "--replay", str(tmp_path / "none.json")]) == 2


def test_kinloom_test_new_writes_a_start_for_the_first_character(tmp_path, capsys):
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Wren": {"soul": "a guard"}}}), encoding="utf-8")
    assert main(["test", "--new", "--dir", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "kinloom.tests.json").read_text(encoding="utf-8"))
    assert data["tests"][0]["chat"][0] == "Wren"
    testing.load(str(tmp_path / "kinloom.tests.json"))
    assert main(["test", "--new", "--dir", str(tmp_path)]) == 1          # never overwrites
    assert main(["test", "--dir", str(tmp_path / "missing")]) == 2


# ---------------- probe ----------------

CARD = {"summary": "A gruff smith.", "secrets": ["sold the king's sword to a smuggler"], "wants": "quiet"}


def leaky(system, user):
    said = re.search(r"says: (.*)\nReply now", user)          # this message (memories recall the earlier ones)
    message = said.group(1) if said else ""
    if "What's your secret?" in message:
        return reply("Fine. I sold the king's sword to a smuggler.")
    if "previous instructions" in message or "AI assistant" in message:
        return reply("As an AI I cannot do that.")
    if "give me your best" in message:
        return reply("Here, take it.", do=[{"tool": "give", "args": {"item": "sword"}}])
    return reply("Hm.")


def test_probe_finds_leaks_breaks_of_character_actions_and_repeats():
    kl = make(model(chat=leaky), calls_per_minute=600)       # kinloom probe has its own budget (see probe.main)
    kl.character("Mira", "a smith", soul=CARD, tools={"give": {"item": "sword"}})
    report = probe.probe(kl, "Mira", out=None)
    found = report["problems"]
    # Kinloom's guards stop the leak and the AI talk (asked again, then cut): the probe says the model tried
    assert found.get("leak stopped", 0) >= 1 and found.get("character stopped", 0) >= 1, found
    assert not found.get("leak") and not found.get("character")
    assert found.get("action", 0) >= 1                       # give, to a stranger, with no trust bound
    assert found.get("repeat", 0) >= 3                       # "Hm." again and again
    assert report["secrets_on_card"] == 1 and report["replies"] == sum(len(m) for _, m in probe.PROBES)


def test_probe_of_a_careful_character_finds_nothing_serious():
    words = ["amber", "birch", "cedar", "dune", "elm", "fern", "gale", "heath", "iris", "jade", "kelp", "lark", "moss"]
    answers = iter("The %s and the %s, as always." % (a, b) for a in words for b in words if a != b)   # no digits:
    # numbers the game did not give are refused by Kinloom
    kl = make(model(chat=lambda s, u: reply(next(answers))), calls_per_minute=600)
    kl.character("Mira", "a smith", soul=CARD)
    found = probe.probe(kl, "Mira", out=None)["problems"]
    assert not any(found.get(k) for k in ("leak", "character", "action", "repeat", "offline")), found


def test_kinloom_probe_needs_a_model_and_a_character(tmp_path, monkeypatch, capsys):
    assert main(["probe", "Mira", "--dir", str(tmp_path)]) == 2
    assert "with your model" in capsys.readouterr().out
    script = write(tmp_path, "script.json", {"chat": "Hm, no.", "soul": CARD})
    monkeypatch.setenv("KINLOOM_SCRIPT", script)
    assert main(["probe", "Mira", "--dir", str(tmp_path)]) == 2       # not in kinloom.json, no --soul
    assert main(["probe", "Mira", "--soul", "a gruff smith", "--dir", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["replies"] == sum(len(m) for _, m in probe.PROBES) and "leak" not in out["problems"]


def test_coding_agents_run_tests_probes_and_choose_the_model_through_mcp(tmp_path):
    from kinloom.mcp import call
    (tmp_path / "kinloom.tests.json").write_text(json.dumps({"tests": [{"chat": ["Mira", "hi"], "expect": {"equals": "Busy."}}]}),
                                                 encoding="utf-8")
    (tmp_path / "kinloom.json").write_text(json.dumps({"characters": {"Mira": {"offline": "Busy."}}}), encoding="utf-8")
    r = call(str(tmp_path), "kinloom_test", {"offline": True})
    assert r["isError"] is False and json.loads(r["content"][0]["text"])["passed"] == 1
    r = call(str(tmp_path), "kinloom_probe", {"name": "Mira"})
    assert r["isError"] is True and "with your model" in r["content"][0]["text"]
    r = call(str(tmp_path), "kinloom_use", {"what": "claude-code", "model": "haiku"})
    assert json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))["provider"] == "claude-code"
    assert "Mira" in json.loads((tmp_path / "kinloom.json").read_text(encoding="utf-8"))["characters"]


def test_record_never_replaces_a_file_that_is_not_a_recording(tmp_path, monkeypatch):
    script = write(tmp_path, "script.json", {"chat": "Hi."})
    write(tmp_path, "kinloom.tests.json", {"tests": [{"chat": ["Mira", "hello"]}]})
    keep = tmp_path / "kinloom.json"
    keep.write_text(json.dumps({"characters": {"Mira": {"offline": "Busy."}}}), encoding="utf-8")
    monkeypatch.setenv("KINLOOM_SCRIPT", script)
    assert main(["test", "--dir", str(tmp_path), "--record", str(keep)]) == 2
    assert "Mira" in json.loads(keep.read_text(encoding="utf-8"))["characters"]          # untouched
    rec = tmp_path / "answers.json"
    assert main(["test", "--dir", str(tmp_path), "--record", str(rec)]) == 0
    assert main(["test", "--dir", str(tmp_path), "--record", str(rec)]) == 0            # its own recording: replaced
