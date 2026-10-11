"""A mod, end to end, on a game whose source the mod never uses.

    python proof/mod/run.py            build Lantern Row (a tiny .NET game, no AI, no mod API), find where to plug in
                                       with `kinloom hooks` (the real REA), build the Harmony mod, run it offline and
                                       with `kinloom serve` + a scripted model; every step checked
    python proof/mod/run.py live       the same with the model from the environment (KINLOOM_MODEL + its key): billed

Needs: the .NET SDK (8+), REA (`rea` on PATH or KINLOOM_REA), network once for the Harmony NuGet package."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "python", "src")
WORK = os.path.join(HERE, ".work")
GAME = os.path.join(WORK, "game", "LanternRow.dll")
MOD = os.path.join(WORK, "mod", "LanternRowKinloom.dll")
sys.path.insert(0, SRC)
from kinloom import mod  # noqa: E402

FAILED = []


def check(ok, what):
    print("%s  %s" % ("PASS" if ok else "FAIL", what))
    if not ok:
        FAILED.append(what)


def sh(cmd, env=None, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=timeout)
    if r.returncode != 0:
        sys.exit("failed: %s\n%s" % (" ".join(cmd), (r.stdout + r.stderr)[-3000:]))
    return r.stdout


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def serve(env, port):
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, "kinloom.json"), "w", encoding="utf-8") as f:
        f.write('{"calls_per_minute": 600}')
    err = open(os.path.join(folder, "serve.err"), "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "kinloom.cli", "serve", "--port", str(port), "--memory",
                          os.path.join(folder, "m.json"), "--quiet", "--dir", folder], env=env,
                         stdout=subprocess.DEVNULL, stderr=err)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return p, err


def stats(port):
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/v1/status" % port, timeout=5) as r:
            return json.loads(r.read().decode()).get("stats") or {}
    except Exception:
        return {}


def main(live=False):
    rea = mod.rea_command()
    if not rea:
        sys.exit(mod.INSTALL)
    base = {k: v for k, v in os.environ.items() if not k.startswith("KINLOOM_") or k == "KINLOOM_REA"}
    base["PYTHONPATH"] = SRC
    print("1. The game: Lantern Row, built; the mod never sees its source")
    sh(["dotnet", "build", os.path.join(HERE, "game"), "-c", "Release", "-o", os.path.dirname(GAME), "-nologo"])
    original = sh(["dotnet", GAME])
    print(original.rstrip())

    print("\n2. Where to plug in: kinloom hooks (REA reads the .dll, nothing is run)")
    start = time.monotonic()
    out = subprocess.run([sys.executable, "-m", "kinloom", "hooks", os.path.dirname(GAME), "--json"], capture_output=True,
                         text=True, env=base, timeout=600)
    took = time.monotonic() - start
    found = json.loads(out.stdout)
    for c in found.get("candidates", []):
        print("   %s.%s(%s) -> %s  [%s]" % (c["type"], c["method"], ", ".join(c["params"]), c["returns"], c["call"]))
    got = {(c["type"], c["method"]): c["call"] for c in found.get("candidates", [])}
    check(got.get(("LanternRow.Shopkeeper", "Greet")) == "say", "Shopkeeper.Greet found, call say (%.1f s)" % took)
    check(got.get(("LanternRow.Shopkeeper", "Answer")) == "chat", "Shopkeeper.Answer found, call chat")
    check(got.get(("LanternRow.Guard", "Shout")) == "say", "Guard.Shout found, call say")
    check(len(got) == 3, "nothing else proposed (Player, Patrol, Main: no line made there)")

    print("\n3. The mod: Kinloom's C# client + Harmony, the patches hooks proposed")
    sh(["dotnet", "build", os.path.join(HERE, "mod"), "-c", "Release", "-o", os.path.dirname(MOD), "-nologo"])

    print("\n4. No server, no model: the game's own lines are the offline answers")
    offline = sh(["dotnet", MOD, GAME, "http://127.0.0.1:%d" % free_port()])
    lines = offline.rstrip().splitlines()
    check(lines[:-1] == original.rstrip().splitlines(), "every line is the game's own")
    check(lines[-1] == "sources: MARLO offline, GUARD offline", "and the patches ran (%s)" % lines[-1])

    env = dict(base)
    if live:
        env.update({k: v for k, v in os.environ.items() if k.startswith("KINLOOM_") or k.endswith("_API_KEY")})
        env.pop("KINLOOM_SCRIPT", None)
        print("\n5. With kinloom serve and the model from the environment (%s)" % env.get("KINLOOM_MODEL", "detected"))
    else:
        env["KINLOOM_SCRIPT"] = os.path.join(HERE, "script.json")
        print("\n5. With kinloom serve and a scripted model")
    port = free_port()
    server, err = serve(env, port)
    try:
        start = time.monotonic()
        played = sh(["dotnet", MOD, GAME, "http://127.0.0.1:%d" % port], timeout=180)
        took = time.monotonic() - start
        print(played.rstrip())
        lines = played.rstrip().splitlines()
        orig = original.rstrip().splitlines()
        check(len(lines) == len(orig) + 1, "the game ran to its end (%.1f s)" % took)
        if live:      # a real model can be late: then the game's own line is said, never nothing
            spoken = [l for l in lines[:-1] if not l.startswith("Ana:")]
            mine = [l for l, o in zip(lines, orig) if not l.startswith("Ana:") and l != o]
            check(all(l.split(": ", 1)[1].strip() for l in spoken), "no empty line")
            check(all(l.split(": ", 1)[0] in ("Marlo", "Guard") for l in spoken), "every line said by the right person")
            check(len(mine) >= 1, "%d of %d lines written by the model, the others the game's own (%s)"
                  % (len(mine), len(spoken), lines[-1]))
        else:
            check(lines[-1] == "sources: MARLO prepared, GUARD prepared", "lines came from the model (%s)" % lines[-1])
            check(all(l.endswith("*a lantern flickers*") for i, l in enumerate(lines[:-1]) if i != 2 and
                      not l.startswith("Ana:")), "every line is the model's")
            check(lines[2] == "Marlo: Curfew, and his cut of my oil. Don't tell him I said so.", "the reply is the model's")
        if FAILED:
            print(subprocess.run([sys.executable, "-m", "kinloom.cli", "log", "--port", str(port), "-n", "40"],
                                 capture_output=True, text=True, env=base).stdout)
        s = stats(port)
        if s:
            print("   server: %s" % json.dumps({k: s[k] for k in ("calls", "failures", "input_tokens", "output_tokens", "cost")
                                                if k in s}))
    finally:
        server.terminate()
        server.wait(10)
        err.close()
    with open(err.name, encoding="utf-8") as f:
        noise = f.read()
    check("Traceback" not in noise, "the server printed no traceback when the game quit")
    print("\n%s" % ("ALL PASS" if not FAILED else "FAILED: %s" % "; ".join(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main(live="live" in sys.argv[1:]))
