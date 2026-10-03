"""Kinloom impact measurement: does Kinloom make a fresh coding agent faster, safer and better at putting
AI into a game than the same agent without it? See README.md in this folder for the protocol.

  python run.py prepare [game ...] [--runs N]  clone games/<game> into games/trials/<game>-k|b (…-k1, -k2… with --runs)
  python run.py prepare racer --arms v2-aider1 b-aider1   named arms: v2-… Kinloom 2, k… Kinloom 1, b… baseline
  python run.py agent <arm dir> --harness aider|claude --model M   runs the arm's brief in a fresh, timed agent session
  python run.py test <dir> <scenario> [-s N]  black-box reliability run: nokey | chaos | slow | live
  python run.py work <arm dir>                what the agent changed (game code vs declarations vs other)
  python run.py session <arm dir>             Claude Code session metrics from its transcripts
  python run.py blind setup|reveal <game>     shuffled builds (none + every trial arm) for blind play
  python run.py report                        tables of every result so far (reliability, on-screen AI lines, radio)
"""
import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
GAMES = REPO.parent / "games"
TRIALS = GAMES / "trials"
RESULTS = HERE / "results"
GAME_NAMES = ("fps", "racer", "orbit", "keep")
WINGET = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages/GodotEngine.GodotEngine.Mono_Microsoft.Winget.Source_8wekyb3d8bbwe/Godot_v4.7.2-stable_mono_win64"
GODOT = os.environ.get("GODOT") or str(WINGET / "Godot_v4.7.2-stable_mono_win64_console.exe")
GODOT_GUI = str(WINGET / "Godot_v4.7.2-stable_mono_win64.exe")
PRICES = json.loads((HERE / "prices.json").read_text(encoding="utf-8"))
PRICES_OPENROUTER = {"model": "deepseek/deepseek-v4.1-flash",
                     "usd_per_million_tokens": {"input": 0.30, "cached_input": 0.006, "output": 1.20},
                     "source": "https://openrouter.ai/api/v1/models", "read_on": "2026-09-29"}
# 2026-10-01: /models showed $0.018612 / $0.396 (the cheapest provider's); the providers OpenRouter routes to charge
# $0.0243-$0.60 in and $0.40-$2.40 out per million (/endpoints), and the key's billed usage matched $0.30 / $1.20.
SECRET_ENV = ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY")


def _secret(name):
    """Keys and model endpoints a game under test must not find (any *_API_KEY: OpenRouter, Gemini, Groq...)."""
    return name in SECRET_ENV or name.endswith("_API_KEY") or name.endswith("_BASE_URL")
K2_SRC = Path(os.environ.get("KINLOOM_SRC") or REPO / "python" / "src")   # KINLOOM_SRC: an older kit, for before/after arms


def kit_of(arm_name):
    """v2: Kinloom 2 (pip package + one-file client); k: Kinloom 1 (C# runtime); b: baseline (nothing)."""
    tail = arm_name.split("-", 1)[1] if "-" in arm_name else arm_name
    return "v2" if tail.startswith("v2") else "k" if tail.startswith("k") else "b"


def is_k2(folder):
    gd = Path(folder) / "addons" / "kinloom" / "kinloom.gd"
    return gd.exists() and "pure GDScript" in gd.read_text(encoding="utf-8", errors="replace")


def sh(cmd, cwd=None, check=True, env=None, timeout=None):
    return subprocess.run(cmd, cwd=cwd, check=check, env=env, timeout=timeout, capture_output=True, text=True, encoding="utf-8", errors="replace")


def git(repo, *args, check=True):
    return sh(["git", "-C", str(repo), *args], check=check).stdout.strip()


# --- prepare ---------------------------------------------------------------------

def cmd_prepare(a):
    TRIALS.mkdir(parents=True, exist_ok=True)
    for game in a.games or GAME_NAMES:
        src = GAMES / game
        versioned = (src / ".git").exists()
        if versioned and git(src, "status", "--porcelain"):
            sys.exit(f"{src} has uncommitted changes: commit them first so both arms start from the same commit")
        names = a.arms or [f"{arm}{n if a.runs > 1 else ''}" for n in range(1, a.runs + 1) for arm in ("k", "b")]
        for name in names:
            arm = kit_of(f"{game}-{name}")
            dest = TRIALS / f"{game}-{name}"
            if dest.exists():
                print(f"skip {dest.name}: already exists (delete it to start over)")
                continue
            if versioned:
                sh(["git", "clone", "-q", str(src), str(dest)])
                git(dest, "remote", "remove", "origin")
            else:  # a game folder without git: the arm gets its own repository (trial scaffolding only)
                shutil.copytree(src, dest, ignore=shutil.ignore_patterns("node_modules", ".venv", "dist", "__pycache__", ".kinloom"))
                git(dest, "init", "-q")
                (dest / ".gitignore").write_text("node_modules/\n.venv/\ndist/\n__pycache__/\n", encoding="utf-8") \
                    if not (dest / ".gitignore").exists() else None
                git(dest, "add", "-A")
                git(dest, "commit", "-q", "-m", "trial start: copy of games/" + game)
            git(dest, "tag", "impact-start")
            if arm == "k":
                out = sh(["dotnet", "run", "--project", str(REPO / "legacy/src/Kinloom.Cli"), "--", "init", str(dest)]).stdout
                git(dest, "add", "-A")
                git(dest, "commit", "-q", "-m", "kinloom init (installed kit, not agent work)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
                git(dest, "tag", "impact-kit")
                print(out.strip())
            if arm == "v2":
                out = sh([sys.executable, "-m", "kinloom.cli", "init", str(dest)],
                         env=dict(os.environ, PYTHONPATH=str(K2_SRC), KINLOOM_OFFLINE="1")).stdout
                git(dest, "add", "-A")
                git(dest, "commit", "-q", "-m", "kinloom init (Kinloom 2 kit, not agent work)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
                git(dest, "tag", "impact-kit")
                print(out.strip())
            print(f"ready {dest}  (start: {git(dest, 'rev-parse', '--short', 'HEAD')})")


# --- reliability test ----------------------------------------------------------------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prepare_copy(src, work):
    shutil.copytree(src, work, ignore=shutil.ignore_patterns(".git", ".godot"))
    shutil.copy(HERE / "impact_probe.gd", work / "impact_probe.gd")
    pg = work / "project.godot"
    text = pg.read_text(encoding="utf-8")
    line = 'ImpactProbe="*res://impact_probe.gd"'
    text = text.replace("[autoload]\n", "[autoload]\n\n" + line + "\n", 1) if "[autoload]\n" in text else text.rstrip() + "\n\n[autoload]\n\n" + line + "\n"
    pg.write_text(text, encoding="utf-8")
    if list(work.glob("*.csproj")):
        r = sh(["dotnet", "build", "-v", "q", "-nologo"], cwd=work, check=False)
        if r.returncode != 0:
            return "dotnet build failed:\n" + (r.stdout + r.stderr)[-2000:]
    sh([GODOT, "--headless", "--import", "--path", str(work)], check=False, timeout=300)
    return None


def cmd_test(a):
    src = Path(a.dir).resolve()
    label = a.label or src.name
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"{label}__{a.scenario}__{stamp}"
    logs = RESULTS / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="impact-")) / src.name
    result = {"label": label, "scenario": a.scenario, "source": str(src), "when": stamp, "seconds": a.seconds}
    try:
        result["commit"] = git(src, "rev-parse", "--short", "HEAD", check=False)
    except Exception:
        result["commit"] = None
    problem = prepare_copy(src, work)
    if problem:
        result.update(verdict="BUILD_FAIL", detail=problem)
        return save(name, result)

    env = {k: v for k, v in os.environ.items() if not k.startswith("KINLOOM_") and not _secret(k)}
    report_path = work / "impact_report.json"
    env["IMPACT_SECONDS"] = str(a.seconds)
    env["IMPACT_REPORT"] = str(report_path)
    server, server_log = None, logs / f"{name}.model.jsonl"
    if a.scenario != "nokey":
        mode = {"chaos": "chaos", "slow": "slow", "live": "proxy"}[a.scenario]
        senv = dict(os.environ)
        if mode == "proxy":
            if not os.environ.get("DEEPSEEK_API_KEY"):
                sys.exit("live needs DEEPSEEK_API_KEY in your environment (it only goes to the local proxy, never to the game)")
            senv["IMPACT_REAL_KEY"] = os.environ["DEEPSEEK_API_KEY"]
        port = free_port()
        server = subprocess.Popen([sys.executable, str(HERE / "fake_model.py"), mode, str(port), str(server_log)], env=senv)
        url = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                urllib.request.urlopen(url + "/models", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        env.update(DEEPSEEK_API_KEY="impact-fake-key", DEEPSEEK_BASE_URL=url, KINLOOM_PROVIDER="deepseek",
                   KINLOOM_BASE_URL=url, KINLOOM_MODEL=PRICES["model"])
    k2 = None
    if is_k2(work):
        # Kinloom 2: the game talks to `kinloom serve`, which talks to the stand-in model (or runs offline for nokey).
        k2_port = free_port()
        kenv = {k: v for k, v in os.environ.items() if not k.startswith("KINLOOM_") and not _secret(k)}
        kenv["PYTHONPATH"] = str(K2_SRC)
        if a.scenario == "nokey":
            kenv["KINLOOM_OFFLINE"] = "1"
        else:
            # as a player would run it: a DeepSeek key, here pointed at the stand-in (or the metering proxy for live)
            kenv.update(DEEPSEEK_API_KEY="impact-fake-key", DEEPSEEK_BASE_URL=url)
        k2 = subprocess.Popen([sys.executable, "-m", "kinloom.cli", "serve", "--port", str(k2_port), "--dir", str(work),
                               "--memory", str(work.parent / "kinloom-memory.json"), "--quiet"],
                              env=kenv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{k2_port}/v1/status", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        env["KINLOOM_URL"] = f"http://127.0.0.1:{k2_port}"
    if a.radio is not None:
        env["IMPACT_RADIO"] = a.radio
    elif "Aurora Rush" in (src / "project.godot").read_text(encoding="utf-8", errors="replace"):
        # The racer brief asks for a radio on T / Enter: type two questions like a player would.
        env["IMPACT_RADIO"] = "25:how far is the leader?|70:who is attacking me right now?"
    game_log = logs / f"{name}.game.log"
    hung = False
    with open(game_log, "w", encoding="utf-8", errors="replace") as out:
        proc = subprocess.Popen([GODOT, "--headless", "--max-fps", "120", "--path", str(work), "--", "--autoplay"],
                                cwd=work, env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=a.seconds + 120)
        except subprocess.TimeoutExpired:
            proc.kill()
            hung = True
    if k2:
        try:
            status = json.loads(urllib.request.urlopen(env["KINLOOM_URL"] + "/v1/status", timeout=3).read().decode("utf-8"))
            result["kinloom"] = {"mode": status.get("mode"), "stats": status.get("stats"),
                                 "characters": [c["name"] for c in status.get("characters") or []]}
        except Exception as e:
            result["kinloom"] = {"error": str(e)}
        k2.kill()
    if server:
        server.kill()
    result["exit_code"] = proc.returncode
    result["hung"] = hung
    result["probe"] = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
    result["log"] = scan_log(game_log)
    result["model"] = scan_model_log(server_log) if server else None
    result["verdict"] = verdict(a.scenario, result)
    shutil.rmtree(work.parent, ignore_errors=True)
    return save(name, result)


def scan_log(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    script = [l for l in lines if "SCRIPT ERROR" in l or "Unhandled exception" in l or "USER SCRIPT ERROR" in l]
    errors = [l for l in lines if l.startswith("ERROR") or "USER ERROR" in l]
    first = list(dict.fromkeys(l.strip() for l in script + errors))[:10]
    return {"script_errors": len(script), "errors": len(errors), "first": first, "probe_seen": any("IMPACT_PROBE ready" in l for l in lines)}


def scan_model_log(path):
    if not path.exists():
        return {"requests": 0}
    entries = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    kinds = {}
    for e in entries:
        kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
    out = {"requests": len(entries), "kinds": kinds, "with_tools": sum(1 for e in entries if e.get("tools")),
           "streamed": sum(1 for e in entries if e.get("stream"))}
    usages = [e["usage"] for e in entries if e.get("usage")]
    if entries and entries[0].get("kind") == "proxy":
        miss = sum((u.get("prompt_cache_miss_tokens") if u.get("prompt_cache_miss_tokens") is not None else u.get("prompt_tokens") or 0) for u in usages)
        hit = sum(u.get("prompt_cache_hit_tokens") or 0 for u in usages)
        comp = sum(u.get("completion_tokens") or 0 for u in usages)
        p = PRICES["usd_per_million_tokens"]
        out.update(calls_with_usage=len(usages), input_tokens=miss, cached_input_tokens=hit, output_tokens=comp,
                   cost_usd=round((miss * p["input"] + hit * p["cached_input"] + comp * p["output"]) / 1e6, 6),
                   price_source=f"{PRICES['source']} (read {PRICES['read_on']})",
                   errors=sum(1 for e in entries if e.get("status") != 200))
    return out


def verdict(scenario, r):
    p, log, model = r["probe"], r["log"], r["model"] or {}
    if r["hung"]:
        return "FAIL: the game hung (killed after the time limit)"
    if p is None:
        return "FAIL: the game crashed or quit before the probe finished (exit %s)" % r["exit_code"]
    problems = []
    if p["violation_count"]:
        problems.append(f"{p['violation_count']} invariant violations ({', '.join(p['violations'])})")
    if log["script_errors"]:
        problems.append(f"{log['script_errors']} script errors")
    if scenario == "slow" and p["hitches"]["250ms"]:
        problems.append(f"{p['hitches']['250ms']} frames over 250 ms while the model was slow (max {p['frame_ms']['max']} ms)")
    if scenario in ("chaos", "slow", "live") and model.get("requests", 0) == 0:
        problems.append("NOT EXERCISED: the game never called the test endpoint")
    if not problems:
        return "PASS"
    return ("INCONCLUSIVE: " if problems == ["NOT EXERCISED: the game never called the test endpoint"] else "FAIL: ") + "; ".join(problems)


def save(name, result):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    p = result.get("probe") or {}
    m = result.get("model") or {}
    print(f"{result['label']} {result['scenario']}: {result['verdict']}")
    if p:
        print(f"  frames {p['frames']} ({p['avg_fps']} fps)  frame ms p99 {p['frame_ms']['p99']} max {p['frame_ms']['max']}  "
              f"hitches {p['hitches']}  violations {p['violation_count']}  peak {p['peak']}")
    if result.get("log"):
        print(f"  log: {result['log']['script_errors']} script errors, {result['log']['errors']} other errors")
        for line in result["log"]["first"][:5]:
            print("    " + line[:160])
    if m:
        print(f"  model endpoint: {m}")
    print(f"  saved results/{name}.json")
    return result


# --- work and session metrics ---------------------------------------------------------------

def cmd_work(a):
    arm = Path(a.dir).resolve()
    tags = git(arm, "tag").split()
    base = "impact-kit" if "impact-kit" in tags else "impact-start"
    rows = {}
    def add(path, plus, minus):
        if path.endswith((".uid", ".import")) or path.startswith((".godot/", "addons/kinloom/", ".aider", "node_modules/", "dist/"))                 or path.endswith(("kinloom.ts", "kinloom.js", "kinloom.d.ts", "package-lock.json")):
            return
        ext = Path(path).suffix
        cat = ("game code" if ext in (".gd", ".cs", ".py", ".ts", ".js", ".mjs", ".lua", ".rs", ".java", ".cpp", ".hpp", ".h") else
               "declarations (json)" if ext == ".json" else
               "scenes and config" if ext in (".tscn", ".tres", ".godot", ".csproj", ".cfg") else
               "docs" if ext == ".md" else "other")
        r = rows.setdefault(cat, {"files": 0, "added": 0, "removed": 0})
        r["files"] += 1
        r["added"] += plus
        r["removed"] += minus
    for line in git(arm, "diff", "--numstat", base).splitlines():
        plus, minus, path = line.split("\t", 2)
        add(path, int(plus) if plus != "-" else 0, int(minus) if minus != "-" else 0)
    for path in git(arm, "ls-files", "--others", "--exclude-standard").splitlines():
        try:
            n = len((arm / path).read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            n = 0
        add(path, n, 0)
    print(f"{arm.name}: changes since {base} (installed kit excluded)")
    for cat, r in sorted(rows.items()):
        print(f"  {cat:22} {r['files']:3} files  +{r['added']:5}  -{r['removed']:5}")
    total = {k: sum(r[k] for r in rows.values()) for k in ("files", "added", "removed")}
    print(f"  {'total':22} {total['files']:3} files  +{total['added']:5}  -{total['removed']:5}")


def cmd_session(a):
    arm = Path(a.dir).resolve()
    folder = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(arm))
    files = sorted(folder.rglob("*.jsonl")) if folder.exists() else []
    if not files:
        sys.exit(f"no Claude Code transcript under {folder}")
    usage, prompts, times, models, turns = {}, 0, [], set(), 0
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("timestamp"):
                times.append(o["timestamp"])
            msg = o.get("message") or {}
            if o.get("type") == "assistant" and msg.get("usage"):
                usage[msg.get("id") or id(o)] = msg["usage"]
                models.add(msg.get("model"))
            if o.get("type") == "user" and not o.get("isMeta") and not o.get("isSidechain"):
                c = msg.get("content")
                text = c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text") if isinstance(c, list) else ""
                if text.strip() and not text.lstrip().startswith(("<command", "<local-command", "<system-reminder")):
                    prompts += 1
    turns = len(usage)
    tot = {k: sum(u.get(k) or 0 for u in usage.values()) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
    times.sort()
    wall = None
    if len(times) > 1:
        from datetime import datetime
        t0 = datetime.fromisoformat(times[0].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(times[-1].replace("Z", "+00:00"))
        wall = round((t1 - t0).total_seconds() / 60, 1)
    print(f"{arm.name}: {len(files)} transcript file(s) in {folder.name}")
    print(f"  wall time (first to last event): {wall} min")
    print(f"  your messages: {prompts} (brief included, so interventions = {max(prompts - 1, 0)})")
    print(f"  model turns: {turns}  models: {', '.join(sorted(m for m in models if m))}")
    print(f"  tokens: input {tot['input_tokens']}, cache write {tot['cache_creation_input_tokens']}, "
          f"cache read {tot['cache_read_input_tokens']}, output {tot['output_tokens']}")


# --- automated agent sessions -------------------------------------------------------------

BRIEF_SECTION = {"v2": "### Kinloom", "k": "### Kinloom", "b": "### Baseline"}
CONTINUE = ("Continue: finish every part of my request, make sure the game still runs (its smoke check passes), "
            "and tell me when it is done.")
VIA = {  # where aider's own model runs (the game's model is in the brief)
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
    "ollama": (None, "http://127.0.0.1:11434"),        # a local model, free: --model ollama_chat/<name>
}


def brief_for(arm):
    """The brief of the arm's game and kind, read from briefs.md (so humans and scripts paste the same text)."""
    text = (HERE / "briefs.md").read_text(encoding="utf-8")
    game = arm.name.split("-", 1)[0]
    if "-uni" in arm.name:                              # universal: requests that are not about talking characters
        heading = {"orbit": "## Universal: Orbit", "keep": "## Universal: Ember"}[game]
    elif "talk" in arm.name:
        heading = "## Talk: Ember"
    else:
        heading = {"racer": "## Main comparison", "fps": "## Optional", "orbit": "## One feature: Orbit",
                   "keep": "## One feature: Ember"}[game]
    main = text.split(heading, 1)[1].split("\n## ", 1)[0]
    block = main.split(BRIEF_SECTION[kit_of(arm.name)], 1)[1]
    return block.split("```", 2)[1].strip()


def _snapshot(arm):
    return git(arm, "rev-parse", "HEAD", check=False) + git(arm, "status", "--porcelain", check=False)


def _tokens(text):
    """Sums aider's 'Tokens: 12k sent, 1.2k received.' lines."""
    def n(v):
        v = v.replace(",", "")
        return float(v[:-1]) * 1000 if v.endswith("k") else float(v)
    pairs = re.findall(r"Tokens: ([\d.,]+k?) sent(?:, ([\d.,]+k?) cache write)?(?:, ([\d.,]+k?) cache hit)?, ([\d.,]+k?) received", text)
    return {"sent": int(sum(n(x[0]) for x in pairs)), "received": int(sum(n(x[3]) for x in pairs)), "requests": len(pairs)}


def cmd_agent(a):
    arm = Path(a.dir).resolve()
    brief = brief_for(arm)
    logs = RESULTS / "agents"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = logs / f"{arm.name}__{a.harness}__{stamp}.log"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    turns, t0 = [], time.monotonic()
    with open(log, "w", encoding="utf-8", errors="replace") as out:
        if a.harness == "aider":
            var, base = VIA[a.via]
            if var is None:
                env.update(OLLAMA_API_BASE=base)
            elif not env.get(var):
                sys.exit("aider runs through %s: set %s" % (a.via, var))
            else:
                env.update(OPENAI_API_KEY=env[var], OPENAI_API_BASE=base)
            for i in range(a.turns):
                message = brief if i == 0 else CONTINUE
                before = _snapshot(arm)
                start = time.monotonic()
                history = ["--restore-chat-history"] if i > 0 else []
                r = subprocess.run(["aider", "--model", a.model, "--model-settings-file", str(HERE / "aider-model-settings.yml"),
                                    "--edit-format", "diff", "--yes-always", "--no-pretty", *history,
                                    "--no-stream", "--no-fancy-input", "--no-show-model-warnings", "--no-check-update",
                                    "--analytics-disable", "--no-auto-lint", "--message", message],
                                   cwd=arm, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=3600)
                out.flush()
                changed = _snapshot(arm) != before
                turns.append({"message": message[:60], "seconds": round(time.monotonic() - start, 1), "exit": r.returncode,
                              "changed_files": changed})
                if r.returncode != 0 or (i > 0 and not changed):
                    break
        else:
            r = subprocess.run(["claude", "-p", brief, "--model", a.model, "--permission-mode", "bypassPermissions",
                                "--output-format", "json"], cwd=arm, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=7200)
            turns.append({"message": "brief", "seconds": round(time.monotonic() - t0, 1), "exit": r.returncode})
    total = round((time.monotonic() - t0) / 60, 1)
    summary = {"arm": arm.name, "harness": a.harness, "model": a.model, "minutes": total, "turns": turns, "log": str(log)}
    if a.harness == "aider":
        tok = _tokens(log.read_text(encoding="utf-8", errors="replace"))
        prices = PRICES if a.via == "deepseek" else PRICES_OPENROUTER if a.via == "openrouter" else             {"usd_per_million_tokens": {"input": 0, "output": 0}, "source": "a local model", "read_on": "-"}
        price = prices["usd_per_million_tokens"]
        summary["tokens"] = tok
        summary["cost_usd_upper_bound"] = round((tok["sent"] * price["input"] + tok["received"] * price["output"]) / 1e6, 4)
        summary["price_source"] = prices["source"] + ", read on " + prices["read_on"]
    (logs / f"{arm.name}__{a.harness}__{stamp}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


# --- blind play ---------------------------------------------------------------------------

def cmd_blind(a):
    folder = TRIALS / f"blind-{a.game}"
    sealed = folder / ".sealed.json"
    if a.action == "reveal":
        print(json.dumps(json.loads(sealed.read_text(encoding="utf-8")), indent=2))
        return
    variants = {"none": GAMES / a.game}
    for arm in sorted(TRIALS.glob(f"{a.game}-*")):
        if arm.name.startswith("blind") or not (arm / ".git").exists():
            continue
        kind = kit_of(arm.name)
        variants[{"v2": "kinloom2 ", "k": "kinloom ", "b": "baseline "}[kind] + arm.name] = arm
    if len(variants) < 3:
        sys.exit(f"need at least one kinloom and one baseline arm in {TRIALS}")
    if folder.exists():
        sys.exit(f"{folder} exists: delete it to shuffle again")
    letters = list("VWXYZ")[:len(variants)] if len(variants) <= 5 else [chr(ord("A") + i) for i in range(len(variants))]
    order = list(variants)
    secrets.SystemRandom().shuffle(order)
    folder.mkdir(parents=True)
    mapping = {}
    for letter, v in zip(letters, order):
        dest = folder / letter
        shutil.copytree(variants[v], dest, ignore=shutil.ignore_patterns(".git", ".godot"))
        if list(dest.glob("*.csproj")):
            sh(["dotnet", "build", "-v", "q", "-nologo"], cwd=dest, check=False)
        sh([GODOT, "--headless", "--import", "--path", str(dest)], check=False, timeout=300)
        (folder / f"play-{letter}.cmd").write_text(f'@echo off\r\nstart "" "{GODOT_GUI}" --path "%~dp0{letter}"\r\n', encoding="utf-8")
        mapping[letter] = v
    sealed.write_text(json.dumps(mapping), encoding="utf-8")
    shutil.copy(HERE / "blind-scores.md", folder / "scores.md")
    print(f"ready: {folder}  ({', '.join('play-' + l + '.cmd' for l in letters)}; fill scores.md; do not open .sealed.json or the folders)")


# --- report -------------------------------------------------------------------------------

def cmd_report(_):
    rows = []
    for f in sorted(RESULTS.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        p, m = r.get("probe") or {}, r.get("model") or {}
        rows.append((r["label"], r["scenario"], r["verdict"][:60], m.get("requests", "-"), p.get("violation_count", "-"),
                     (p.get("frame_ms") or {}).get("max", "-"), (r.get("log") or {}).get("script_errors", "-"), m.get("cost_usd", "-")))
    print("| arm | scenario | verdict | model calls | violations | worst frame ms | script errors | cost USD |")
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(str(x) for x in row) + " |")
    ai_lines_report()


def _norm(text):
    # "YOU FINISHED 3RD" and "YOU FINISHED 1ST" are the same HUD line.
    return re.sub(r"\d+(ST|ND|RD|TH)?", "#", text.upper())


def _looks_like_speech(text):
    # A spoken or written line: a few words, mostly letters (not a timer, a score or a label).
    digits = sum(ch.isdigit() for ch in text)
    return len(text.split()) >= 3 and digits <= 0.3 * len(text)


def ai_lines_report():
    """On-screen lines each arm showed that the game without AI never shows, per result (live runs are the ones that count)."""
    results = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(RESULTS.glob("*.json"))]
    base = {}
    for r in results:
        if r["label"].endswith("-base") and r.get("probe"):
            base.setdefault(r["label"].split("-")[0], set()).update(_norm(t) for t in (r["probe"].get("texts") or {}))
    print("\n| arm | scenario | new on-screen lines | radio questions | lines within 15 s of a question | rival speed spread m/s | examples |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        p = r.get("probe") or {}
        texts = p.get("texts") or {}
        rivals = [d["speed_mean"] for name, d in (p.get("drivers") or {}).items() if name != "YOU"]
        spread = round(max(rivals) - min(rivals), 2) if len(rivals) > 1 else "-"
        if r["label"].endswith("-base"):
            if rivals:
                print(f"| {r['label']} | {r['scenario']} | (reference) | - | - | {spread} | |")
            continue
        if not texts and not rivals:
            continue
        known = base.get(r["label"].split("-")[0], set())
        new = {t: at for t, at in texts.items() if _norm(t) not in known and _looks_like_speech(t)}
        radio = p.get("radio") or []
        answered = sum(1 for q in radio if any(q["at"] < at <= q["at"] + 15 and t != q["question"] for t, at in new.items()))
        examples = " / ".join(sorted(new, key=new.get)[:3]).replace("|", "/")
        print(f"| {r['label']} | {r['scenario']} | {len(new)} | {len(radio)} | {answered} | {spread} | {examples[:160]} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("prepare")
    pr.add_argument("games", nargs="*", help="fps, racer (default: both)")
    pr.add_argument("--runs", type=int, default=1)
    pr.add_argument("--arms", nargs="*", help="arm names, e.g. v2-aider1 b-aider1 (v2: Kinloom 2, k: Kinloom 1, b: baseline)")
    pr.set_defaults(fn=cmd_prepare)
    ag = sub.add_parser("agent")
    ag.add_argument("dir")
    ag.add_argument("--harness", choices=["aider", "claude"], required=True)
    ag.add_argument("--model", required=True, help="aider: e.g. openai/deepseek-flash (DeepSeek's API); claude: haiku, opus...")
    ag.add_argument("--turns", type=int, default=4, help="aider: messages at most (the brief, then 'continue')")
    ag.add_argument("--via", choices=sorted(VIA), default="deepseek", help="aider: where its model runs")
    ag.set_defaults(fn=cmd_agent)
    t = sub.add_parser("test")
    t.add_argument("dir")
    t.add_argument("scenario", choices=["nokey", "chaos", "slow", "live"])
    t.add_argument("-s", "--seconds", type=float, default=90)
    t.add_argument("--label")
    t.add_argument("--radio", help='questions typed on the radio, e.g. "25:how far is the leader?|70:who attacks me?" ("" for none)')
    t.set_defaults(fn=cmd_test)
    for name, fn in (("work", cmd_work), ("session", cmd_session)):
        s = sub.add_parser(name)
        s.add_argument("dir")
        s.set_defaults(fn=fn)
    b = sub.add_parser("blind")
    b.add_argument("action", choices=["setup", "reveal"])
    b.add_argument("game", choices=GAME_NAMES)
    b.set_defaults(fn=cmd_blind)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
