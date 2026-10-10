"""Runs every client's conformance scenario against a real `kinloom serve` with a scripted model (no tokens).
    python conformance/run.py            # Python, JavaScript (node), Godot (if installed), C# (dotnet)
Exit code 0 when every transcript matches expected.txt (plus each client's own extra lines)."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLIENTS = os.path.join(ROOT, "src", "kinloom", "clients")
WINGET = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
                      "GodotEngine.GodotEngine.Mono_Microsoft.Winget.Source_8wekyb3d8bbwe", "Godot_v4.7.2-stable_mono_win64",
                      "Godot_v4.7.2-stable_mono_win64_console.exe")
GODOT = os.environ.get("GODOT") or (WINGET if os.path.exists(WINGET) else shutil.which("godot"))
EXTRA = {"godot": ["aichar talks: BLAZE passes NOVA!", "aichar steers: block 0.9", "aimind moves: retreat, charge 2.5"]}


FAILURES = os.path.join(tempfile.gettempdir(), "kinloom-conformance-failures.log")


def keep_failure(text):
    """A failure's report, also appended to FAILURES: when a run's output is filtered or lost, the reason stays."""
    try:
        with open(FAILURES, "a", encoding="utf-8") as f:
            f.write("==== %s %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(sys.argv), text))
    except OSError:
        pass
    return text + "\n(kept in %s)" % FAILURES


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def godot_cmd(port):
    work = os.path.join(tempfile.mkdtemp(), "godot")
    shutil.copytree(os.path.join(HERE, "godot"), work)
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from kinloom import init  # installs the addon exactly as a developer would (autoload + editor plugin)
    init.setup(work, "godot", agents="minimal")
    subprocess.run([GODOT, "--headless", "--import", "--path", work], capture_output=True, timeout=300)
    return [GODOT, "--headless",  "--path", work], lambda out: [l[3:] for l in out.splitlines() if l.startswith("T: ")]


def java_cmd(port):
    """Compiles the Java client for Java 8 (Android, libGDX, old Minecraft) and runs the scenario with the same JDK."""
    javac = shutil.which("javac")
    out = tempfile.mkdtemp()
    subprocess.run([javac, "--release", "8", "-Xlint:-options", "-d", out, os.path.join(CLIENTS, "java", "Kinloom.java"),
                    os.path.join(HERE, "java", "Scenario.java")], check=True, timeout=180)
    java = os.path.join(os.path.dirname(javac), "java")
    return [java if os.path.exists(java) or os.path.exists(java + ".exe") else "java", "-cp", out, "Scenario", str(port)]


def start_server(env, port):
    # The scenarios make about 25 model calls in a minute (Godot's AI nodes keep deciding): with the default budget
    # (30 a minute, 30 % kept for the player) the last background think was sometimes refused "over budget" (seen in
    # the server's journal, 1 run in 4): a flaky failure that tests nothing of the clients. The budget is checked by
    # tests/test_brain.py.
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, "kinloom.json"), "w", encoding="utf-8") as f:
        f.write('{"calls_per_minute": 600}')
    server = subprocess.Popen([sys.executable, "-m", "kinloom.cli", "serve", "--port", str(port), "--memory",
                               os.path.join(folder, "m.json"), "--quiet", "--dir", folder],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return server


def cpp_cmd(port):
    """Builds the C++ scenario with $CXX (e.g. "python -m ziglang c++"), g++ or clang++."""
    cxx = os.environ.get("CXX", "").split() or [shutil.which("g++") or shutil.which("clang++")]
    exe = os.path.join(tempfile.mkdtemp(), "scenario.exe")
    link = ["-lws2_32"] if os.name == "nt" else ["-pthread"]
    subprocess.run(cxx + ["-std=c++17", "-Wall", "-Wextra", "-Werror=all", "-O1", os.path.join(HERE, "cpp", "scenario.cpp"), "-o", exe]
                   + link, check=True, timeout=600, capture_output=True)
    return [exe, str(port)]


def main(only=()):
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and not k.endswith("_BASE_URL") and not k.startswith("KINLOOM_")}
    env.update(KINLOOM_SCRIPT=os.path.join(HERE, "script.json"), PYTHONPATH=os.path.join(ROOT, "src"))
    expected = open(os.path.join(HERE, "expected.txt"), encoding="utf-8").read().strip().splitlines()
    lines = lambda o: o.splitlines()
    runs = [("python", lambda port: [sys.executable, os.path.join(HERE, "scenario.py"), str(port)], lines)]
    if shutil.which("node"):
        runs.append(("javascript", lambda port: ["node", os.path.join(HERE, "scenario.mjs"), str(port)], lines))
        runs.append(("typescript", lambda port: ["node", os.path.join(HERE, "scenario.ts"), str(port)], lines))
    if shutil.which("dotnet"):
        runs.append(("csharp", lambda port: ["dotnet", "run", "--project", os.path.join(HERE, "csharp"), "--", str(port)],
                     lambda o: [l for l in o.splitlines() if ": " in l]))
    if shutil.which("cargo"):
        runs.append(("rust", lambda port: ["cargo", "run", "-q", "--manifest-path", os.path.join(HERE, "rust", "Cargo.toml"), "--", str(port)], lines))
    lua_python = os.environ.get("LUA_PYTHON") or sys.executable
    lua_ok = subprocess.run([lua_python, "-c", "import lupa"], capture_output=True).returncode == 0
    if lua_ok:
        for runtime in ("luajit21", "lua54"):
            runs.append(("lua-" + runtime, lambda port, rt=runtime: [lua_python, os.path.join(HERE, "lua", "host.py"), str(port), rt], lines))
    if os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++"):
        runs.append(("cpp", cpp_cmd, lines))
    if shutil.which("javac"):
        runs.append(("java", java_cmd, lines))
    if GODOT:
        runs.append(("godot", lambda port: godot_cmd(port)[0], lambda o: [l[3:] for l in o.splitlines() if l.startswith("T: ")]))
    ok = True
    for runtime in ("luajit21", "lua54") if lua_ok and (not only or any(o.startswith("lua") for o in only)) else ():
        # the Lua client's own transports (LuaSocket, the LÖVE thread): host.py replaces them with its own
        r = subprocess.run([lua_python, os.path.join(HERE, "lua", "transports.py"), runtime], capture_output=True, text=True,
                           timeout=120)
        passed = r.returncode == 0 and "PASS" in r.stdout
        ok = ok and passed
        print("lua-transports-%s: %s" % (runtime, "PASS" if passed else "FAIL\n" + (r.stdout + r.stderr)[-2000:]))
    for name, make, parse in runs:
        if only and name not in only:
            continue
        port = free_port()                      # a fresh server per client: no state carried from one client to the next
        server = start_server(dict(env, KINLOOM_VOICE="scripted"), port)       # a scripted voice on the server
        try:
            r = subprocess.run(make(port), capture_output=True, text=True, timeout=240,
                               env=dict(env, KINLOOM_TEST_PORT=str(port), KINLOOM_VOICE="off"))   # offline: no system voice
        finally:
            server.kill()
        got = parse(r.stdout.replace("\r\n", "\n"))
        want = expected[:6] + EXTRA.get(name, []) + expected[6:]
        if got == want:
            print("%s: PASS" % name)
        else:
            ok = False
            print(keep_failure("%s: FAIL\n--- expected\n%s\n--- got\n%s\n--- output (tail)\n%s"
                               % (name, "\n".join(want), "\n".join(got), (r.stderr + r.stdout)[-3000:])))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(tuple(sys.argv[1:])))
