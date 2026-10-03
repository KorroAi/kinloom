"""Native SDK conformance: every client runs the conformance scenario with its own in-process brain (direct mode),
calling a fake model server, instead of `kinloom serve`. Checks per SDK:

  1. the transcript is expected.txt (plus the client's own extra lines), as in relay mode;
  2. prompt parity: the requests the SDK sent the model are the ones the Python reference sent (same system and user
     text, JSON mode, token limit, streaming), compared per task;
  3. vectors: the SDK's pure functions give the Python results on vectors.json (a "vectors: N/N" line);
  4. the deep scenario (deep.py: every path of a reply, repairs, pools, impact, Anthropic, the budget): the transcript
     is expected-deep.txt and the requests are the reference's.

    python conformance/native.py                 # the references, then every SDK found
    python conformance/native.py typescript      # the references, then these SDKs
    python conformance/native.py --show          # also print the reference requests

The references are Python itself: `kinloom serve` (main scenario) and the library (deep scenario), their model the fake.
"""
import json
import os
import re
import subprocess
import sys
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakemodel  # noqa: E402
import run as relay  # noqa: E402

SCRIPT = os.path.join(HERE, "script.json")
DEEP = os.path.join(HERE, "deep.json")
# The deep scenario, per SDK: the command that runs it (KINLOOM_NATIVE in its environment).
DEEP_RUNS = {
    "javascript": lambda: ["node", os.path.join(HERE, "deep.mjs")],
    "csharp": lambda: ["dotnet", "run", "--project", os.path.join(HERE, "csharp"), "--", "deep"],
    "java": lambda: relay.java_cmd("deep"),
    "rust": lambda: ["cargo", "run", "-q", "--manifest-path", os.path.join(HERE, "rust", "Cargo.toml"), "--", "deep"],
    "cpp": lambda: relay.cpp_cmd("deep"),
    # Godot prints its banner on stdout: only the scenario's "T: " lines are kept.
    "godot": lambda: [sys.executable, "-c", "import subprocess, sys; r = subprocess.run(sys.argv[1:], capture_output=True, text=True, "
                      "encoding='utf-8'); print('\\n'.join(l[3:] for l in r.stdout.splitlines() if l.startswith('T: '))); "
                      "sys.stderr.write(r.stderr + r.stdout[-3000:])", *relay.godot_cmd(0)[0], "res://deep.tscn"],
    "lua-luajit21": lambda: [_lua_python(), os.path.join(HERE, "lua", "host.py"), "0", "luajit21", "deep.lua"],
    "lua-lua54": lambda: [_lua_python(), os.path.join(HERE, "lua", "host.py"), "0", "lua54", "deep.lua"],
}
def _lua_python():
    return os.environ.get("LUA_PYTHON") or sys.executable


_ZERO = re.compile(r"(?<![\d.])(-?\d+)\.0(?![\d])")


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url):
    req = urllib.request.Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def normalize(entry):
    """What must be identical between SDKs: everything but number spellings (2.0 and 2 are the same to a model)."""
    e = dict(entry)
    for k in ("system", "user"):
        if isinstance(e.get(k), str):
            e[k] = _ZERO.sub(r"\1", e[k])
    return json.dumps(e, sort_keys=True, ensure_ascii=False)


def by_task(log):
    out = {}
    for entry in log:
        out.setdefault(entry.get("task", "*"), set()).add(normalize(entry))
    return out


def _distance(a, b):
    import difflib
    return 1.0 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def compare(reference, got):
    """[problems]: requests one side sent and the other did not, per task."""
    problems = []
    ref, mine = by_task(reference), by_task(got)
    for task in sorted(set(ref) | set(mine)):
        a, b = ref.get(task, set()), mine.get(task, set())
        for x in sorted(a - b):
            near = min(b, key=lambda y: _distance(x, y)) if b else None
            problems.append("task %s: the reference sent a request this SDK did not:\n  ref: %s\n  sdk: %s"
                            % (task, x[:3000], (near or "(nothing)")[:3000]))
        for y in sorted(b - a):
            if not a:
                problems.append("task %s: this SDK sent a request the reference never sent:\n  sdk: %s" % (task, y[:3000]))
    return problems


def native_runs():
    """(name, command maker, transcript parser) for every SDK whose toolchain is here."""
    import shutil
    lines = lambda o: o.splitlines()
    runs = []
    if shutil.which("node"):
        runs.append(("javascript", lambda: ["node", os.path.join(HERE, "scenario.mjs"), "0"], lines))
        runs.append(("typescript", lambda: ["node", os.path.join(HERE, "scenario.ts"), "0"], lines))
    if shutil.which("dotnet"):
        runs.append(("csharp", lambda: ["dotnet", "run", "--project", os.path.join(HERE, "csharp"), "--", "0"],
                     lambda o: [l for l in o.splitlines() if ": " in l]))
    if shutil.which("javac"):
        runs.append(("java", lambda: relay.java_cmd(0), lines))
    if shutil.which("cargo"):
        runs.append(("rust", lambda: ["cargo", "run", "-q", "--manifest-path", os.path.join(HERE, "rust", "Cargo.toml"), "--", "0"],
                     lines))
    if os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++"):
        runs.append(("cpp", lambda: relay.cpp_cmd(0), lines))
    lua_python = _lua_python()
    if subprocess.run([lua_python, "-c", "import lupa"], capture_output=True).returncode == 0:
        for rt in ("luajit21", "lua54"):
            runs.append(("lua-" + rt, lambda rt=rt: [lua_python, os.path.join(HERE, "lua", "host.py"), "0", rt], lines))
    if relay.GODOT:
        runs.append(("godot", lambda: relay.godot_cmd(0)[0], lambda o: [l[3:] for l in o.splitlines() if l.startswith("T: ")]))
    return runs


def serve(script):
    port = relay.free_port()
    server = fakemodel.serve(port, script)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d" % port


def main(argv):
    show = "--show" in argv
    only = [a for a in argv if not a.startswith("--")]
    fake, base = serve(SCRIPT)
    deep, dbase = serve(DEEP)
    expected = open(os.path.join(HERE, "expected.txt"), encoding="utf-8").read().strip().splitlines()
    deep_expected = open(os.path.join(HERE, "expected-deep.txt"), encoding="utf-8").read().strip().splitlines()
    vectors = json.load(open(os.path.join(HERE, "vectors.json"), encoding="utf-8"))
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.endswith("_BASE_URL")
           and not k.startswith("KINLOOM_")}
    env["PYTHONPATH"] = os.path.join(relay.ROOT, "src")
    env["KINLOOM_VECTORS"] = os.path.join(HERE, "vectors.json")
    model_env = dict(KINLOOM_BASE_URL=base + "/v1", KINLOOM_MODEL="fake-model", KINLOOM_API_KEY="fake-key",
                     KINLOOM_VOICE_BASE_URL=base + "/v1", KINLOOM_SPEAK_MODEL="fake-tts", KINLOOM_LISTEN_MODEL="fake-stt",
                     KINLOOM_VOICE_API_KEY="fake-key")
    ok = True

    # ---- the reference: Python's brain inside kinloom serve, its model the fake one ----
    _post(base + "/reset")
    sport = relay.free_port()
    server = relay.start_server(dict(env, **model_env), sport)
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "scenario.py"), str(sport)], capture_output=True, text=True,
                           timeout=240, env=dict(env, KINLOOM_VOICE="off"))
    finally:
        server.kill()
    got = r.stdout.replace("\r\n", "\n").splitlines()
    reference = _get(base + "/log")
    if got != expected:
        ok = False
        print("reference (python): FAIL\n--- expected\n%s\n--- got\n%s\n%s" % ("\n".join(expected), "\n".join(got), r.stderr[-3000:]))
    else:
        print("reference (python): PASS (%d requests, %d tasks)" % (len(reference), len(by_task(reference))))
    if show:
        for e in reference:
            print(json.dumps(e, ensure_ascii=False)[:600])

    # ---- the deep scenario's reference: Python's library ----
    r = subprocess.run([sys.executable, os.path.join(HERE, "deep.py")], capture_output=True, text=True, timeout=300,
                       env=dict(env, KINLOOM_NATIVE=dbase + "/v1", KINLOOM_VOICE="off"))
    got = r.stdout.replace("\r\n", "\n").splitlines()
    deep_reference = _get(dbase + "/log")
    if got != deep_expected:
        ok = False
        print("deep reference (python): FAIL\n--- expected\n%s\n--- got\n%s\n%s" % ("\n".join(deep_expected), "\n".join(got), r.stderr[-3000:]))
    else:
        print("deep reference (python): PASS (%d requests, %d tasks)" % (len(deep_reference), len(by_task(deep_reference))))

    # ---- every SDK, in direct mode against the same fake models ----
    for name, make, parse in native_runs():
        if only and name not in only:
            continue
        _post(base + "/reset")
        try:
            cmd = make()
        except Exception as e:  # a toolchain that cannot build: reported, the others still run
            ok = False
            print("%s: FAIL (build) %s" % (name, e))
            continue
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           env=dict(env, KINLOOM_NATIVE=base + "/v1", KINLOOM_VOICE="off"))
        out = r.stdout.replace("\r\n", "\n")
        got = parse(out)
        vec = [l for l in got if l.startswith("vectors: ")]
        got = [l for l in got if not l.startswith("vectors: ")]
        want = expected[:6] + relay.EXTRA.get(name, []) + expected[6:]
        problems = []
        if got != want:
            problems.append("transcript differs\n--- expected\n%s\n--- got\n%s" % ("\n".join(want), "\n".join(got)))
        if vec != ["vectors: %d/%d" % (len(vectors), len(vectors))]:
            problems.append("vectors: %s (want %d/%d)" % (vec or "no vectors line", len(vectors), len(vectors)))
        problems += compare(reference, _get(base + "/log"))
        if name in DEEP_RUNS:
            _post(dbase + "/reset")
            d = subprocess.run(DEEP_RUNS[name](), capture_output=True, text=True, timeout=300,
                               env=dict(env, KINLOOM_NATIVE=dbase + "/v1", KINLOOM_VOICE="off"))
            dgot = d.stdout.replace("\r\n", "\n").splitlines()
            if dgot != deep_expected:
                problems.append("deep transcript differs\n--- expected\n%s\n--- got\n%s\n--- deep output (tail)\n%s"
                                % ("\n".join(deep_expected), "\n".join(dgot), (d.stderr + d.stdout)[-2000:]))
            problems += ["deep " + p for p in compare(deep_reference, _get(dbase + "/log"))]
        if problems:
            ok = False
            print("%s: FAIL\n%s\n--- output (tail)\n%s" % (name, "\n".join(problems), (r.stderr + out)[-3000:]))
        else:
            print("%s: PASS%s" % (name, " (with the deep scenario)" if name in DEEP_RUNS else ""))
    fake.shutdown()
    deep.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
