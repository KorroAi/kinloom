"""Kinloom's C# SDK inside the Unity editor (batch mode, no window), with no key and no real model:

  1. relay:  the C# conformance scenario (python/conformance/csharp/Program.cs) run by the editor against a real
             `kinloom serve` with the scripted model; its transcript must equal conformance/expected.txt
  2. native: the same scenario with the SDK calling the conformance fake model itself: transcript, the shared vectors,
             every request equal to Python's, and the deep scenario (what conformance/native.py checks)
  3. play:   the KinloomDialogue component in play mode through a relay: she speaks first, her action, gesture and mood,
             the reply choices, a choice picked, her answer, the box closed
  4. player: a Windows player built with IL2CPP (managed stripping "low"; "player-high": "high") runs 1 and 2 itself

    python proof/engines/unity/run.py "C:/Program Files/Unity/Hub/Editor/6000.3.25f1/Editor/Unity.exe" [PROJECT] [relay native play player player-high]

PROJECT (default: a folder next to this file, ignored by git) is created with the editor and set up by `kinloom init`.
Unity writes its own lines to Console ("Start Indexing..."): they are left out of the transcript.
"""
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "..", "..", "..", "python")
CONF = os.path.join(PY, "conformance")
sys.path.insert(0, CONF)
import native  # noqa: E402
import run as relay  # noqa: E402

EDITOR_NOISE = ("[Indexing]", "Start Indexing")


def base_env():
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.endswith("_BASE_URL") and not k.startswith("KINLOOM_")}
    env["PYTHONPATH"] = os.path.join(PY, "src")
    return env


def setup(unity, project):
    if not os.path.isdir(os.path.join(project, "Assets")):
        subprocess.run([unity, "-batchmode", "-nographics", "-createProject", project, "-quit", "-logFile",
                        os.path.join(os.path.dirname(project), "unity-create.log")], check=True, timeout=1200)
    subprocess.run([sys.executable, "-m", "kinloom", "init", project, "--yes", "--agents", "minimal"], env=base_env(),
                   check=True, capture_output=True)
    editor = os.path.join(project, "Assets", "Editor")
    runtime = os.path.join(project, "Assets", "KinloomConformance")     # in the game's assembly: players include it
    os.makedirs(editor, exist_ok=True)
    os.makedirs(runtime, exist_ok=True)
    if os.path.exists(os.path.join(editor, "Program.cs")):
        os.remove(os.path.join(editor, "Program.cs"))
    src = open(os.path.join(CONF, "csharp", "Program.cs"), encoding="utf-8").read()   # Main reachable from the probes
    src = src.replace("static class Program", "public static class Program", 1)
    src = src.replace("static async Task Main(string[] args)", "public static async Task Main(string[] args)", 1)
    open(os.path.join(runtime, "Program.cs"), "w", encoding="utf-8").write("#nullable enable\n" + src)
    shutil.copy(os.path.join(HERE, "KinloomPlayerProbe.cs"), runtime)
    for name in ("KinloomProbe.cs", "KinloomPlayProbe.cs", "KinloomBuild.cs"):
        shutil.copy(os.path.join(HERE, name), editor)


def probe_run(cmd, log, env, out):
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run(cmd + ["-logFile", log], env=dict(env, KL_PROBE_OUT=out), timeout=900)
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    errors = sorted(set(re.findall(r"Assets/[^\n]*(?:error|warning) CS\d+[^\n]*", text)))
    lines = open(out, encoding="utf-8").read().replace("\r\n", "\n").splitlines() if os.path.exists(out) else []
    return r.returncode, lines, errors


def editor_run(unity, project, method, env, out):
    return probe_run([unity, "-batchmode", "-nographics", "-projectPath", project, "-executeMethod", method],
                     os.path.join(project, "probe-unity.log"), env, out)


def editor_runner(unity, project):
    return lambda env, out: editor_run(unity, project, "KinloomProbe.Run", env, out)


def scenario(lines):
    return [l for l in lines if not l.startswith("UNITY ") and not l.startswith(EDITOR_NOISE)]


def check_relay(runner, project):
    expected = open(os.path.join(CONF, "expected.txt"), encoding="utf-8").read().strip().splitlines()
    env = dict(base_env(), KINLOOM_SCRIPT=os.path.join(CONF, "script.json"))
    port = relay.free_port()
    server = relay.start_server(dict(env, KINLOOM_VOICE="scripted"), port)
    try:
        code, lines, errors = runner(dict(env, KL_PROBE_ARGS=str(port), KINLOOM_TEST_PORT=str(port), KINLOOM_VOICE="off"),
                                     os.path.join(project, "probe-out.txt"))
    finally:
        server.kill()
    got = scenario(lines)
    problems = errors + [l for l in lines if l.startswith("UNITY ") and "main thread: yes" not in l and "UNITY player:" not in l]
    if got != expected:
        problems.append("transcript differs: %s" % [(w, g) for w, g in zip(expected, got) if w != g][:5])
    return code == 0 and not problems, problems + [l for l in lines if "main thread" in l or "UNITY player:" in l]


def check_native(runner, project):
    fake, base = native.serve(native.SCRIPT)
    deep, dbase = native.serve(native.DEEP)
    expected = open(os.path.join(CONF, "expected.txt"), encoding="utf-8").read().strip().splitlines()
    deep_expected = open(os.path.join(CONF, "expected-deep.txt"), encoding="utf-8").read().strip().splitlines()
    count = len(__import__("json").load(open(os.path.join(CONF, "vectors.json"), encoding="utf-8")))
    env = dict(base_env(), KINLOOM_VECTORS=os.path.join(CONF, "vectors.json"))
    off = dict(env, KINLOOM_VOICE="off")   # the scenarios run without the system voice; the server keeps its own
    model = dict(KINLOOM_BASE_URL=base + "/v1", KINLOOM_MODEL="fake-model", KINLOOM_API_KEY="fake-key",
                 KINLOOM_VOICE_BASE_URL=base + "/v1", KINLOOM_SPEAK_MODEL="fake-tts", KINLOOM_LISTEN_MODEL="fake-stt",
                 KINLOOM_VOICE_API_KEY="fake-key")
    try:
        # the references: Python inside kinloom serve, then Python's library on the deep scenario
        native._post(base + "/reset")
        sport = relay.free_port()
        server = relay.start_server(dict(env, **model), sport)
        try:
            subprocess.run([sys.executable, os.path.join(CONF, "scenario.py"), str(sport)], capture_output=True, timeout=240, env=off)
        finally:
            server.kill()
        reference = native._get(base + "/log")
        subprocess.run([sys.executable, os.path.join(CONF, "deep.py")], capture_output=True, timeout=300,
                       env=dict(off, KINLOOM_NATIVE=dbase + "/v1"))
        deep_reference = native._get(dbase + "/log")
        out = os.path.join(project, "probe-out.txt")
        native._post(base + "/reset")
        code, lines, errors = runner(dict(off, KL_PROBE_ARGS="0", KINLOOM_NATIVE=base + "/v1"), out)
        got = [l for l in scenario(lines) if ": " in l]
        vec = [l for l in got if l.startswith("vectors: ")]
        got = [l for l in got if not l.startswith("vectors: ")]
        problems = errors + [l for l in lines if l.startswith("UNITY ERR")]
        if got != expected:
            problems.append("transcript differs: %s" % [(w, g) for w, g in zip(expected, got) if w != g][:5])
        if vec != ["vectors: %d/%d" % (count, count)]:
            problems.append("vectors: %s" % vec)
        problems += native.compare(reference, native._get(base + "/log"))
        native._post(dbase + "/reset")
        dcode, dlines, _ = runner(dict(off, KL_PROBE_ARGS="deep", KINLOOM_NATIVE=dbase + "/v1"), out)
        if scenario(dlines) != deep_expected:
            problems.append("deep transcript differs")
        problems += ["deep " + p for p in native.compare(deep_reference, native._get(dbase + "/log"))]
        note = "%d requests and %d deep requests equal to Python's, %s" % (len(reference), len(deep_reference), vec[0] if vec else "no vectors")
        return code == 0 and dcode == 0 and not problems, problems + [note]
    finally:
        fake.shutdown()
        deep.shutdown()


def check_play(unity, project):
    env = dict(base_env(), KINLOOM_SCRIPT=os.path.join(HERE, "dialogue_script.json"))
    port = relay.free_port()
    server = relay.start_server(dict(env, KINLOOM_VOICE="off"), port)
    try:
        code, lines, errors = editor_run(unity, project, "KinloomPlayProbe.Run", dict(env, KL_PROBE_ARGS=str(port)),
                                         os.path.join(project, "play-out.txt"))
    finally:
        server.kill()
    want = ["play mode: True", "reply: Hmph. What do you want?", 'action: give {"item":"sword"}', "gesture: crosses her arms",
            "choices: Ask about the sword | Leave", "open: True, mood: wary", "reply: Then go.",
            "choices: Ask about the sword | Leave", "mood: calm", "closed", "DONE"]
    return code == 0 and lines == want and not errors, errors + lines


def build_player(unity, project, backend, stripping):
    """A Windows player (backend il2cpp or mono, a managed stripping level) whose scene runs the scenario."""
    exe = os.path.join(project, "Build-%s-%s" % (backend, stripping), "probe.exe")
    log = os.path.join(project, "build-unity.log")
    r = subprocess.run([unity, "-batchmode", "-nographics", "-projectPath", project, "-executeMethod", "KinloomBuild.Build",
                        "-logFile", log], env=dict(base_env(), KL_BUILD_OUT=exe, KL_BACKEND=backend, KL_STRIPPING=stripping),
                       timeout=3600)
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    summary = re.findall(r"KINLOOM BUILD [^\n]*", text)
    return (exe if r.returncode == 0 and os.path.exists(exe) else None), (summary or [text[-1500:]])


def check_player(unity, project, backend="il2cpp", stripping="low"):
    t = time.time()
    exe, notes = build_player(unity, project, backend, stripping)
    notes = ["build (%s, stripping %s, %.0f s): %s" % (backend, stripping, time.time() - t, " ".join(notes))]
    if exe is None:
        return False, notes
    runner = lambda env, out: probe_run([exe, "-batchmode", "-nographics"], os.path.join(project, "player.log"), env, out)
    ok = True
    for name, check in (("relay", check_relay), ("native", check_native)):
        passed, more = check(runner, project)
        ok = ok and passed
        notes += ["player %s: %s" % (name, "PASS" if passed else "FAIL")] + ["  " + m for m in more]
    return ok, notes


STEPS = ("relay", "native", "play", "player", "player-high")


def main(argv):
    unity = argv[0]
    project = argv[1] if len(argv) > 1 and argv[1] not in STEPS else os.path.join(HERE, "project")
    steps = [a for a in argv[1:] if a in STEPS] or ["relay", "native", "play", "player"]
    project = os.path.abspath(project)
    setup(unity, project)
    runner = editor_runner(unity, project)
    ok = True
    for step in steps:
        t = time.time()
        if step == "relay":
            passed, notes = check_relay(runner, project)
        elif step == "native":
            passed, notes = check_native(runner, project)
        elif step == "play":
            passed, notes = check_play(unity, project)
        else:
            passed, notes = check_player(unity, project, "il2cpp", "high" if step == "player-high" else "low")
        ok = ok and passed
        print("unity %s: %s (%.0f s)" % (step, "PASS" if passed else "FAIL", time.time() - t))
        for n in notes:
            print("   " + n[:1500])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
