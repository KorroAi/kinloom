"""Universality: does any request, in any words, turn into correct Kinloom code? Spends cents (one OpenRouter model).

    python proof/universal/run.py <label> [--src HEAD|path] [--samples N] [--only id,id]   writes results-<label>.json
    python proof/universal/run.py report                                                     the table of every run

For each request of requests.json (most not about characters or dialogue, a third in French), the model
(deepseek/deepseek-v4.1-flash on OpenRouter) reads what a coding agent reads in a Python game after `kinloom init`
(AGENTS.md) and writes the code, twice: with AGENTS.md alone, and with the output of `kinloom recipe "<request>"`
added (an agent that ran the command). The code is then checked:
- calls: it uses at least one Kinloom call that can do the request (the request's `ok` list: lenient on purpose);
- clean: no hand-written HTTP, SDK or API key;
- runs: it runs offline (no key) and against a hostile scripted model, in its own process (runner.py).
`--src HEAD` measures the committed kit (git archive of python/src), the default the working copy.
"""
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
MODEL = "deepseek/deepseek-v4.1-flash"
PRICES = {"input": 0.30, "cached_input": 0.006, "output": 1.20,
          "source": "https://openrouter.ai/api/v1/models, deepseek/deepseek-v4.1-flash, read on 2026-09-29"}
SYSTEM = ("You are a coding agent working in a game project written in Python. The project's instructions file, "
          "AGENTS.md, follows; follow it.\n\n")
ASK = ("The developer asks: \"%s\"\n\nWrite only the Python code that does it, in one ```python block. Kinloom is "
       "already set up: `kl = Kinloom()` exists. Stand in for the game with plain Python at the top (example values, "
       "small functions; no engine imports, no game loop) and make the calls once at the end, where the game would.")
FORBIDDEN = re.compile(r"(?im)^\s*(?:import|from)\s+(?:requests|urllib|http|httpx|aiohttp|openai|anthropic|socket)\b|"
                       r"api[_-]?key|/v1/chat/completions")
CALL = re.compile(r"\bkl\.(\w+)\(")
KIT_SCRIPT = r"""
import os, sys, tempfile
from kinloom import init
from kinloom.recipe import recipe
d = tempfile.mkdtemp()
open(os.path.join(d, "main.py"), "w").close()
init.setup(d)
agents = open(os.path.join(d, "AGENTS.md"), encoding="utf-8").read()
sys.stdout.reconfigure(encoding="utf-8")
print(agents)
print("\n=====RECIPE=====")
print(recipe(sys.argv[1], "python"))
"""


def source(spec):
    """The kinloom sources to measure: the working copy, a folder, or a git revision."""
    if spec in (None, "", "work"):
        return os.path.join(REPO, "python", "src")
    if os.path.isdir(spec):
        return spec
    out = tempfile.mkdtemp()
    tar = os.path.join(out, "src.tar")
    subprocess.run(["git", "-C", REPO, "archive", "-o", tar, spec, "python/src"], check=True)
    with tarfile.open(tar) as t:
        t.extractall(out)
    return os.path.join(out, "python", "src")


def clean_env(src):
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k and not k.startswith(("KINLOOM_", "OPENAI_", "DEEPSEEK_"))}
    env.update(KINLOOM_SRC=src, PYTHONPATH=src, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return env


def kit(src, request):
    """(AGENTS.md, the recipe output) as `kinloom init` and `kinloom recipe` write them from these sources."""
    r = subprocess.run([sys.executable, "-c", KIT_SCRIPT, request], env=clean_env(src), capture_output=True, text=True,
                       encoding="utf-8", timeout=60, cwd=tempfile.gettempdir())
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    agents, recipe = r.stdout.split("\n=====RECIPE=====\n", 1)
    return agents.strip(), recipe.strip()


def code_of(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.S)
    return max(blocks, key=len) if blocks else (text or "")


def run_snippet(src, code, mode):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "runner.py"), mode, f.name], env=clean_env(src),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40,
                           cwd=tempfile.mkdtemp())
        return r.returncode == 0, (r.stderr or "").strip().splitlines()[-1:] or [""]
    except subprocess.TimeoutExpired:
        return False, ["timeout (40 s)"]
    finally:
        os.unlink(f.name)


class _Late:
    ok, text, error, input_tokens, cached_tokens, output_tokens = False, "", "no answer after the deadline", 0, 0, 0


def deadline(fn, seconds):
    """fn() or a failed reply after `seconds`: a provider that keeps the connection alive never times out by itself."""
    box = []
    t = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    t.start()
    t.join(seconds)
    return box[0] if box else _Late()


def check(src, code, ok):
    """What the measure counts for one answer."""
    calls = sorted(set(CALL.findall(code)))
    runs_offline, err_offline = run_snippet(src, code, "offline")
    runs_hostile, err_hostile = run_snippet(src, code, "hostile")
    result = {"calls": calls, "right_call": bool(set(calls) & set(ok)), "clean": not FORBIDDEN.search(code),
              "runs_offline": runs_offline, "runs_hostile": runs_hostile,
              "error": (err_offline if not runs_offline else err_hostile if not runs_hostile else [""])[0][:300]}
    result["pass"] = result["right_call"] and result["clean"] and runs_offline and runs_hostile
    return result


def measure(label, src_spec=None, samples=2, only=None):
    sys.path.insert(0, os.path.join(REPO, "python", "src"))
    from kinloom.providers import detect
    key = os.environ.get("OPENROUTER_API_KEY") or sys.exit("OPENROUTER_API_KEY is not set")
    p = detect({"OPENROUTER_API_KEY": key, "KINLOOM_MODEL": MODEL}, probe_ollama=False)
    src = source(src_spec)
    requests = json.load(open(os.path.join(HERE, "requests.json"), encoding="utf-8"))
    if only:
        requests = [r for r in requests if r["id"] in only]
    rows, tokens = [], {"input": 0, "cached": 0, "output": 0, "calls": 0, "failed": 0}
    started = time.time()
    lock = threading.Lock()

    def one(req, agents, recipe, with_recipe, n):
        user = ASK % req["text"]
        if with_recipe:
            user += "\n\nYou ran `kinloom recipe \"%s\"`; it printed:\n\n%s" % (req["text"], recipe)
        r = deadline(lambda: p.complete(SYSTEM + agents, user, max_tokens=2500, temperature=0.7, timeout=180), 240)
        row = {"id": req["id"], "recipe": with_recipe, "sample": n}
        if r.ok:
            row["code"] = code_of(r.text)
            row.update(check(src, row["code"], req["ok"]))
        else:
            row["failed"] = r.error
        with lock:
            tokens["calls"] += 1
            tokens["failed"] += 0 if r.ok else 1
            tokens["input"] += r.input_tokens
            tokens["cached"] += r.cached_tokens
            tokens["output"] += r.output_tokens
            rows.append(row)
            with open(os.path.join(HERE, "results-%s.jsonl" % label), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")     # kept even if the run is stopped
            print("%-10s recipe=%-5s %s  calls=%s %s" % (req["id"], with_recipe, "PASS" if row.get("pass") else "fail",
                                                         ",".join(row.get("calls", [])), (row.get("error") or row.get("failed") or "")[:90]), flush=True)

    jobs = []
    for req in requests:
        agents, recipe = kit(src, req["text"])
        jobs += [(req, agents, recipe, w, n) for w in (False, True) for n in range(samples)]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda j: one(*j), jobs))
    rows.sort(key=lambda r: ([q["id"] for q in requests].index(r["id"]), r["recipe"], r["sample"]))
    cost = ((tokens["input"] - tokens["cached"]) * PRICES["input"] + tokens["cached"] * PRICES["cached_input"]
            + tokens["output"] * PRICES["output"]) / 1e6
    out = {"label": label, "src": src_spec or "work", "model": MODEL, "samples": samples, "date": time.strftime("%Y-%m-%d"),
           "minutes": round((time.time() - started) / 60, 1), "tokens": tokens, "cost_usd": round(cost, 4),
           "prices": PRICES, "summary": summary(rows), "rows": rows}
    path = os.path.join(HERE, "results-%s.json" % label)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(out["summary"], indent=1))
    print("cost $%.4f, %s" % (cost, path))


def summary(rows):
    out = {}
    for with_recipe in (False, True):
        part = [r for r in rows if r["recipe"] == with_recipe and "failed" not in r]
        if not part:
            continue
        rate = lambda k: round(sum(1 for r in part if r[k]) / len(part), 3)  # noqa: E731
        out["with recipe" if with_recipe else "AGENTS.md only"] = {
            "answers": len(part), "pass": rate("pass"), "right_call": rate("right_call"), "clean": rate("clean"),
            "runs_offline": rate("runs_offline"), "runs_hostile": rate("runs_hostile"),
            "failed_requests": sorted({r["id"] for r in part if not r["pass"]})}
    return out


def report():
    for name in sorted(os.listdir(HERE)):
        if name.startswith("results-") and name.endswith(".json"):
            d = json.load(open(os.path.join(HERE, name), encoding="utf-8"))
            for cond, s in d["summary"].items():
                print("%-10s %-15s pass %4.0f%%  right call %4.0f%%  clean %4.0f%%  offline %4.0f%%  hostile %4.0f%%  (%d answers, $%.3f run)"
                      % (d["label"], cond, 100 * s["pass"], 100 * s["right_call"], 100 * s["clean"], 100 * s["runs_offline"],
                         100 * s["runs_hostile"], s["answers"], d["cost_usd"]))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "report":
        report()
    else:
        opt = lambda name, default=None: args[args.index(name) + 1] if name in args else default  # noqa: E731
        only = opt("--only")
        measure(args[0], opt("--src"), int(opt("--samples", 2)), only.split(",") if only else None)
