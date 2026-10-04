"""`kinloom check`: finds the mistakes coding agents make when adding Kinloom to a game, before anyone plays it."""
import json
import os
import re
import urllib.request

from .init import detect

SOURCE = (".gd", ".js", ".mjs", ".ts", ".tsx", ".cs", ".py", ".lua", ".cpp", ".h", ".hpp", ".rs", ".java")
SKIP = {".git", "node_modules", ".godot", "Library", "Temp", "obj", "bin", ".venv", "venv", "__pycache__", ".kinloom",
        "dist", "build", ".claude", ".cursor", ".github"}
CLIENT_FILES = {"web": "kinloom.js", "love": "kinloom.lua", "defold": "kinloom.lua", "rust": "kinloom.rs",
                "java": "Kinloom.java", "cpp": "kinloom.hpp", "unreal": "kinloom.hpp"}
_KEY = re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{16,}|sk-[A-Za-z0-9]{24,})\b")
_DECLARE = re.compile(r"\b[Cc]haracter\(\s*[\"']([^\"']+)[\"']")
_USE = re.compile(r"\b(say|chat|decide|act|Say|Chat|Decide|Act)\(\s*[\"']([^\"']+)[\"']")
_ASYNC_JS = re.compile(r"(?<![\w.])(?:\w+\.)?(say|chat|create)\((?=\s*[\"'])")
_SPOKEN_USE = re.compile(r"\b[sS]peak\([^()\n]*\)\s*\.(path|data|url|audio|seconds|b64)\b")   # speak(...).path
_ASYNC_GD = re.compile(r"\bKinloom\.(say|chat|create)\(")
_CHAT = re.compile(r"\b(?:chat|Chat|chat_as)\(\s*[\"']([^\"']+)[\"']")
_FRAME = re.compile(r"(func\s+_(?:physics_)?process\b|void\s+(?:Fixed)?Update\s*\(|\bfunction\s+love\.update\b|"
                    r"\bdef\s+(?:update|tick|on_update)\s*\(|\b(?:update|tick|gameLoop|loop)\s*\([^)]*\)\s*\{|"
                    r"requestAnimationFrame\s*\()")
_FUNC = re.compile(r"(\bfunc\s+\w+|\bdef\s+\w+|\bfunction\b[^\n]*|\b(?:void|async|public|private|static)\s+[\w<>\[\]]+\s*\w*\s*\()")
_CREATE = re.compile(r"\b(?:create|Create|create_async|createAsync|create_image|CreateAsync)\(")
_PLACEHOLDER = re.compile(r"(?<![\w])([\"'])text\1(?!\s*[:\]=])")     # "text" as a value, not as a key
_GIVING = re.compile(r"^(give|gift|pay|sell|trade|unlock|open|free|reward|heal|teach|reveal|grant|lend|hand)", re.I)


def _args(text, start):
    """The argument text of a call whose "(" is at start - 1 (to the matching parenthesis)."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1]


def _top_level_commas(args):
    depth, n, quote = 0, 0, None
    for ch in args:
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            n += 1
    return n


TOP_KEYS = ("provider", "model", "base_url", "command", "pool", "language", "calls_per_minute", "prices", "memory", "port",
            "banned_words", "max_cost_per_hour", "max_cost_per_day", "lore", "characters", "tools", "models", "rating",
            "reply_timeout")
API_PROVIDERS = ("deepseek", "anthropic", "openai", "ollama", "custom", "offline")


def _config_findings(folder):
    """kinloom.json: characters declared there, and mistakes in them."""
    from . import config
    from .brain import _tools
    from .harness import KINDS
    out, names = [], {}
    try:
        cfg = config.load(folder)
    except config.ConfigError as e:
        return [("error", "kinloom.json: %s" % e)], names
    unknown = [k for k in cfg if k not in TOP_KEYS and k not in config.DEFAULTS and not k.startswith("_")]
    if unknown:
        out.append(("warn", "kinloom.json: unknown keys %s (ignored)" % ", ".join(sorted(unknown))))
    kind = str(cfg.get("provider") or "").lower()
    if kind and kind not in API_PROVIDERS + KINDS:
        out.append(("error", "kinloom.json: unknown provider %r (an API key: %s; a coding agent: %s)" % (
            kind, ", ".join(API_PROVIDERS), ", ".join(KINDS))))
    elif kind in KINDS:
        try:
            config.provider(cfg, env={})
        except config.ConfigError as e:
            out.append(("error", str(e)))
    from .brain import _rating
    try:
        _rating(cfg.get("rating"))
    except ValueError as e:
        out.append(("error", "kinloom.json: %s" % e))
    rt = cfg.get("reply_timeout")
    if rt is not None and (isinstance(rt, bool) or not isinstance(rt, (int, float)) or rt <= 0):
        out.append(("error", "kinloom.json: \"reply_timeout\" is a number of seconds (8 by default), got %r" % (rt,)))
    models = cfg.get("models")
    if models is not None and (not isinstance(models, dict) or any(
            k not in ("chat", "background") or not (v is None or isinstance(v, (str, dict))) for k, v in models.items())):
        out.append(("error", "kinloom.json: \"models\" is {\"chat\" or \"background\": a model id}, e.g. "
                             "{\"background\": \"a-cheaper-model\"}"))
    game_tools = {}
    if cfg.get("tools") is not None:
        if not isinstance(cfg["tools"], dict):
            out.append(("error", "kinloom.json: \"tools\" (the game's tools) must be an object {name: example args}"))
        else:
            try:
                game_tools = _tools(cfg["tools"])[0]
            except ValueError as e:
                out.append(("error", "kinloom.json: tools: %s" % e))
    chars = cfg.get("characters")
    if chars is None:
        return out, names
    if not isinstance(chars, dict):
        return [("error", "kinloom.json: \"characters\" must be an object {name: {...}}")], names
    for name, spec in chars.items():
        if not isinstance(spec, dict):
            out.append(("error", "kinloom.json: character %r must be an object" % name))
            continue
        names[name] = "kinloom.json"
        given = spec.get("tools")
        tools = dict(given) if isinstance(given, dict) else {}
        if given == "all" or given is True:
            tools.update(game_tools)
        elif isinstance(given, list):
            for item in given:
                if isinstance(item, dict):
                    tools.update(item)
                elif isinstance(item, str) and item.strip().lower() == "all":
                    tools.update(game_tools)
                elif isinstance(item, str) and item in game_tools:
                    tools[item] = game_tools[item]
                elif isinstance(item, str):
                    out.append(("error", "kinloom.json: %s names the tool %r, which is not one of the game's tools "
                                         "(\"tools\" at the top of kinloom.json)" % (name, item)))
        trust = spec.get("trust") if isinstance(spec.get("trust"), dict) else {}
        for t in trust:
            if t not in tools:
                out.append(("error", "kinloom.json: %s trust names %r, which is not one of its tools" % (name, t)))
        for t in tools:
            if _GIVING.match(t) and t not in trust:
                out.append(("warn", "kinloom.json: players will try to talk %s into %r: bound it with \"trust\": "
                                    "{\"%s\": 0.3} (kinloom add ... --trust %s=0.3)" % (name, t, t, t)))
        for k in ("warmth", "secret_trust", "warm_up"):
            v = spec.get(k)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                out.append(("error", "kinloom.json: %s %s must be a number, got %r" % (name, k, v)))
        from .brain import _CONFIG_KEYS
        unknown = [k for k in spec if k not in _CONFIG_KEYS]
        if unknown:
            out.append(("warn", "kinloom.json: %s has unknown keys %s (ignored)" % (name, ", ".join(sorted(unknown)))))
    return out, names


def _sources(folder):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP and not (d == "kinloom" and os.path.basename(root) == "addons")
                   and not (d == "kinloom" and os.path.exists(os.path.join(root, d, "brain.py")))]   # the Python package
                                                                                                    # init copied in
        for f in files:
            if f.endswith(SOURCE) and f not in ("kinloom.js", "kinloom.ts", "kinloom.d.ts", "Kinloom.cs", "kinloom.lua", "kinloom.rs",
                                                "Kinloom.java", "kinloom.hpp", "kinloom-talk.js"):
                path = os.path.join(root, f)
                try:
                    if os.path.getsize(path) > 2_000_000:
                        continue
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        yield os.path.relpath(path, folder).replace(os.sep, "/"), fh.read()
                except OSError:
                    continue


def _server(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/v1/status", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def check(folder=".", url="http://127.0.0.1:7717"):
    """Returns (engine, [(level, message)]) with level in "ok", "warn", "error"."""
    folder = os.path.abspath(folder)
    engine = detect(folder)
    out = []
    # client
    if engine == "godot":
        project = open(os.path.join(folder, "project.godot"), encoding="utf-8", errors="replace").read()
        if not os.path.exists(os.path.join(folder, "addons", "kinloom", "kinloom.gd")):
            out.append(("error", "addons/kinloom is missing: run `kinloom init`"))
        elif 'Kinloom="*res://addons/kinloom/kinloom.gd"' not in project:
            out.append(("error", "the Kinloom autoload is not in project.godot: run `kinloom init` again"))
        else:
            out.append(("ok", "Godot addon installed and autoloaded"))
    elif engine in ("unity", "dotnet"):
        found = any(f == "Kinloom.cs" for _, _, fs in os.walk(folder) for f in fs)
        out.append(("ok", "Kinloom.cs present") if found else ("error", "Kinloom.cs is missing: run `kinloom init`"))
    elif engine in CLIENT_FILES:
        name = CLIENT_FILES[engine]
        names = {name, "kinloom.ts"} if engine == "web" else {name}
        found = any(f in names for r, _, fs in os.walk(folder) if "node_modules" not in r for f in fs)
        out.append(("ok", "%s present" % name) if found else ("error", "%s is missing: run `kinloom init`" % name))
    # kinloom.json
    found, declared = _config_findings(folder)
    out += found
    # code
    used = {}
    for rel, text in _sources(folder):
        for m in _KEY.finditer(text):
            out.append(("error", "%s:%d looks like an API key in the source: keys belong in the environment of "
                                 "`kinloom serve`, never in the game" % (rel, text.count("\n", 0, m.start()) + 1)))
        for m in _DECLARE.finditer(text):
            declared.setdefault(m.group(1), rel)
        for m in _USE.finditer(text):
            used.setdefault(m.group(2), "%s:%d" % (rel, text.count("\n", 0, m.start()) + 1))
        if rel.endswith((".js", ".mjs", ".ts", ".tsx")) and ("kinloom" in text.lower()):
            for m in _ASYNC_JS.finditer(text):
                before = text[max(0, m.start() - 12):m.start()]
                statement = text[m.end():].split("\n", 1)[0]
                if "await" not in before and ".then(" not in statement and not before.rstrip().endswith(("return", "[", ",")):
                    line = text.count("\n", 0, m.start()) + 1
                    out.append(("warn", "%s:%d %s(...) returns a Promise: use `await` (or .then), else the game shows "
                                        "[object Promise]" % (rel, line, m.group(1))))
        for m in _CREATE.finditer(text):
            if _PLACEHOLDER.search(_args(text, m.end())):
                out.append(("warn", "%s:%d create(...) has \"text\" in its example: the example is also the offline answer, so "
                                    "players would read the word \"text\"; write a real sample (\"Found under a cold stone.\")"
                            % (rel, text.count("\n", 0, m.start()) + 1)))
        for m in _SPOKEN_USE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(("warn", "%s:%d speak(...) gives nothing when no voice can speak (no key, no system voice): keep "
                                "the result and check it before using .%s" % (rel, line, m.group(1))))
        for m in _CHAT.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            args = _args(text, m.start() + text[m.start():].index("(") + 1)
            if _top_level_commas(args) < 3 and "speaker" not in args:
                out.append(("warn", "%s:%d chat(%r, ...) has no speaker: every player shares one memory and one bond "
                                    "with %s; pass the player's name (4th argument, or speaker=)" % (rel, line, m.group(1), m.group(1))))
            head = None
            for f in _FUNC.finditer(text, 0, m.start()):
                head = f
            frame = None
            for f in _FRAME.finditer(text, 0, m.start()):
                frame = f
            if frame is not None and (head is None or frame.start() >= head.start()):
                out.append(("warn", "%s:%d chat(...) inside a per-frame function: it takes ~1 s and calls a model; call it "
                                    "when the player talks (an input event), not every frame" % (rel, line)))
        if rel.endswith(".gd"):
            for m in _ASYNC_GD.finditer(text):
                if "await" not in text[max(0, m.start() - 12):m.start()]:
                    line = text.count("\n", 0, m.start()) + 1
                    out.append(("warn", "%s:%d Kinloom.%s(...) needs `await` in GDScript" % (rel, line, m.group(1))))
    for name, where in sorted(used.items()):
        if name not in declared:
            out.append(("warn", "%s uses the character %r but it is neither in kinloom.json nor declared with "
                                "character(...): it will have no personality or offline lines (kinloom add %s \"...\")"
                        % (where, name, name)))
    if declared:
        out.append(("ok", "characters declared: %s" % ", ".join(sorted(declared))))
    elif engine != "other":
        out.append(("warn", "no character yet: `kinloom add NAME \"who they are\"` (or character(...) in the code)"))
    # server
    if engine != "python":
        status = _server(url)
        if status is None:
            out.append(("warn", "kinloom serve is not running at %s (the game answers offline until it is)" % url))
        else:
            out.append(("ok", "kinloom serve is running (%s)" % (status.get("mode") or "?")))
    return engine, out


def run(folder=".", url="http://127.0.0.1:7717"):
    engine, results = check(folder, url)
    print("Kinloom check (%s)" % engine)
    for level, message in results:
        print("  %-5s %s" % (level.upper(), message))
    return 1 if any(level == "error" for level, _ in results) else 0
