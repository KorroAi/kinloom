import json

from kinloom.providers import Scripted, detect, from_script_file, Recording


def test_a_script_file_answers_per_task(tmp_path):
    f = tmp_path / "script.json"
    f.write_text(json.dumps({"chat": ["one", "two"], "decide": {"a": 1}, "*": "fallback"}), encoding="utf-8")
    p = from_script_file(str(f))
    assert p.complete("Kinloom task: chat\n...", "u").text == "one"
    assert p.complete("Kinloom task: chat\n...", "u").text == "two"
    assert p.complete("Kinloom task: chat\n...", "u").text == "fallback"
    assert json.loads(p.complete("Kinloom task: decide\n...", "u", json_mode=True).text) == {"a": 1}
    assert p.complete("Kinloom task: lines\n...", "u").text == "fallback"


def test_the_environment_selects_a_script_before_any_key(tmp_path):
    f = tmp_path / "script.json"
    f.write_text("{}", encoding="utf-8")
    p = detect({"KINLOOM_SCRIPT": str(f), "DEEPSEEK_API_KEY": "k"}, probe_ollama=False)
    assert isinstance(p, Scripted)


def test_recording_then_replaying(tmp_path):
    rec = tmp_path / "rec.json"
    inner = Scripted(lambda kind, system, user: "live answer")
    p = Recording(inner, str(rec))
    p.complete("Kinloom task: chat\nx", "u")
    p.complete("Kinloom task: say\nx", "u")
    data = json.loads(rec.read_text(encoding="utf-8"))
    assert data == {"chat": ["live answer"], "say": ["live answer"]}
    replay = from_script_file(str(rec))
    assert replay.complete("Kinloom task: chat\nx", "u").text == "live answer"
