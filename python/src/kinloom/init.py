"""`kinloom init`: sets up a game folder in seconds, for any engine and any coding agent.

1. finds the engine (Godot, Unity, other .NET, web/JS/TS, Python, LÖVE, Defold, Rust, Java, C++, Unreal, anything);
2. drops the one-file client (Godot: the addon, enabled);
3. writes the short instructions in AGENTS.md (read by most coding agents), in the files of the other agents found
   here (installed, or already used by the project: CLAUDE.md + skill, Gemini, Cursor, Copilot, Windsurf, aider,
   opencode; `agents="all"` writes them all) and the full reference KINLOOM.md;
4. says what model it found and what to do next.
Running it again updates everything in place (between markers) and never touches the rest of your files.
"""
import os
import re
import shutil

from . import __version__

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "kit")
CLIENTS = os.path.join(HERE, "clients")
START, END = "<!-- kinloom:start -->", "<!-- kinloom:end -->"
ENGINES = ("godot", "unity", "dotnet", "web", "python", "love", "defold", "rust", "java", "cpp", "unreal", "other")
_SKIP = {".git", "node_modules", ".godot", "Library", "Temp", "obj", "bin", ".venv", "venv", "__pycache__", ".kinloom",
         "dist", "build", "addons"}


# ---------------- engine ----------------

def _files(folder, depth=2):
    """Relative paths of files up to `depth` folders deep, skipping dependency and build folders."""
    out = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirs[:] = [d for d in dirs if d not in _SKIP and level < depth]
        out.extend(os.path.normpath(os.path.join(rel, f)) for f in files)
    return out


def detect(folder):
    """The engine or language of the game in `folder`."""
    names = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    files = _files(folder)
    base = {os.path.basename(f).lower() for f in files}
    ext = {os.path.splitext(f)[1].lower() for f in files}
    if "project.godot" in names:
        return "godot"
    if "Assets" in names and ("ProjectSettings" in names or "Packages" in names):
        return "unity"
    if any(n.endswith(".uproject") for n in names):
        return "unreal"
    if "game.project" in names:
        return "defold"
    if "conf.lua" in base or "main.lua" in names:
        return "love"
    if "Cargo.toml" in names:
        return "rust"
    if names & {"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"}:
        return "java"
    if ".csproj" in ext or ".sln" in ext or ".fsproj" in ext:
        return "dotnet"
    if "package.json" in names or "index.html" in base or ".ts" in ext or ".tsx" in ext:
        return "web"
    if ".py" in ext or "pyproject.toml" in names or "requirements.txt" in names:
        return "python"
    if "CMakeLists.txt" in names or ext & {".cpp", ".cc", ".cxx", ".hpp"}:
        return "cpp"
    return "other"


# ---------------- client ----------------

def _copy_tree(src, dst):
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.normpath(os.path.join(dst, rel))
        os.makedirs(target, exist_ok=True)
        for f in files:
            if f.endswith((".pyc", ".uid", ".import")):
                continue
            shutil.copyfile(os.path.join(root, f), os.path.join(target, f))


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _godot_enable(project_file):
    """Adds the Kinloom autoload and enables the editor plugin in project.godot (idempotent, keeps line endings)."""
    text = _read(project_file)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)

    def section(name):
        head = "[%s]" % name
        if head not in [l.strip() for l in lines]:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([head, ""])
        start = [l.strip() for l in lines].index(head)
        end = start + 1
        while end < len(lines) and not lines[end].strip().startswith("["):
            end += 1
        return start, end

    start, end = section("autoload")
    if not any(l.strip().startswith("Kinloom=") for l in lines[start:end]):
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, 'Kinloom="*res://addons/kinloom/kinloom.gd"')
    start, end = section("editor_plugins")
    plugin = "res://addons/kinloom/plugin.cfg"
    for i in range(start + 1, end):
        if lines[i].strip().startswith("enabled="):
            if plugin not in lines[i]:
                items = re.findall(r'"([^"]*)"', lines[i]) + [plugin]
                lines[i] = "enabled=PackedStringArray(%s)" % ", ".join('"%s"' % x for x in items)
            break
    else:
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, 'enabled=PackedStringArray("%s")' % plugin)
    new = nl.join(lines)
    if new != text:
        _write(project_file, new)


def install_client(folder, engine):
    """Copies the client for the engine. Returns (paths written, client path for the docs or None)."""
    written = []
    if engine == "python":
        # Python games import the package itself: a copy next to the game (standard library only, ~0.5 MB) makes
        # `import kinloom` work with python, uv run, a venv or a frozen build players get, with nothing to install.
        here = os.path.dirname(os.path.abspath(__file__))
        dst = os.path.join(folder, "kinloom")
        if os.path.abspath(dst) == here or os.path.exists(os.path.join(folder, "pyproject.toml")) and \
                'name = "kinloom"' in _read(os.path.join(folder, "pyproject.toml")):
            return written, None                   # Kinloom's own source tree
        if os.path.isdir(dst) and not os.path.exists(os.path.join(dst, "brain.py")):
            return written, None                   # the game's own package called kinloom: leave it
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(here, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "clients", "*.egg-info"))
        written.append("kinloom/ (the package itself, to ship with the game)")
        ignore = os.path.join(folder, ".aiderignore")          # a library, not the game: out of agents' repo maps
        old = _read(ignore) if os.path.exists(ignore) else ""
        if "kinloom/" not in old.split():
            _write(ignore, old + ("" if not old or old.endswith("\n") else "\n") + "kinloom/\n")
        return written, "kinloom"
    if engine == "godot":
        dst = os.path.join(folder, "addons", "kinloom")
        _copy_tree(os.path.join(CLIENTS, "godot", "addons", "kinloom"), dst)
        _godot_enable(os.path.join(folder, "project.godot"))
        written += ["addons/kinloom/", "project.godot (Kinloom autoload + plugin enabled)"]
        return written, "addons/kinloom"
    if engine in ("unity", "dotnet"):
        rel = os.path.join("Assets", "Kinloom", "Kinloom.cs") if engine == "unity" else os.path.join("Kinloom", "Kinloom.cs")
        shutil.copyfile(os.path.join(CLIENTS, "csharp", "Kinloom.cs"), _ensure_dir(os.path.join(folder, rel)))
        written.append(rel.replace(os.sep, "/"))
        if engine == "unity":           # a ready dialogue box: add the component, write who the character is
            box = os.path.join("Assets", "Kinloom", "KinloomDialogue.cs")
            shutil.copyfile(os.path.join(CLIENTS, "csharp", "Unity", "KinloomDialogue.cs"), _ensure_dir(os.path.join(folder, box)))
            written.append(box.replace(os.sep, "/"))
        return written, rel.replace(os.sep, "/")
    if engine == "web":
        base = "src" if os.path.isdir(os.path.join(folder, "src")) else "."
        # TypeScript projects get the TypeScript source (plain tsc copies nothing else to its output folder).
        # kinloom-talk.js: a ready dialogue box (JavaScript projects; TypeScript ones build their own UI).
        names = ("kinloom.ts",) if os.path.exists(os.path.join(folder, "tsconfig.json")) else ("kinloom.js", "kinloom.d.ts", "kinloom-talk.js")
        for f in names:
            rel = os.path.normpath(os.path.join(base, "kinloom", f))
            shutil.copyfile(os.path.join(CLIENTS, "web", f), _ensure_dir(os.path.join(folder, rel)))
            written.append(rel.replace(os.sep, "/"))
        return written, os.path.normpath(os.path.join(base, "kinloom", names[0])).replace(os.sep, "/")
    single = {
        "love": ("lua", "kinloom.lua", "kinloom.lua"),
        "defold": ("lua", "kinloom.lua", os.path.join("kinloom", "kinloom.lua")),
        "rust": ("rust", "kinloom.rs", os.path.join("src", "kinloom.rs")),
        "java": ("java", "Kinloom.java", os.path.join("src", "main", "java", "kinloom", "Kinloom.java")),
        "cpp": ("cpp", "kinloom.hpp", os.path.join("src" if os.path.isdir(os.path.join(folder, "src")) else "", "kinloom.hpp")),
        "unreal": ("cpp", "kinloom.hpp", os.path.join("Source", _unreal_module(folder), "kinloom.hpp")),
    }.get(engine)
    if single:
        kind, name, rel = single
        rel = os.path.normpath(rel)
        shutil.copyfile(os.path.join(CLIENTS, kind, name), _ensure_dir(os.path.join(folder, rel)))
        rel = rel.replace(os.sep, "/")
        written.append(rel)
        return written, rel
    return written, None


def _unreal_module(folder):
    """The first game module folder under Source/ (the one with a .Build.cs), else ''."""
    source = os.path.join(folder, "Source")
    for name in sorted(os.listdir(source)) if os.path.isdir(source) else []:
        sub = os.path.join(source, name)
        if os.path.isdir(sub) and any(f.endswith(".Build.cs") for f in os.listdir(sub)):
            return name
    return ""


def _ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


# ---------------- instructions ----------------

def _ts_import_extension(folder):
    """'.ts' when the project's tsconfig allows importing .ts files, else '.js' (TypeScript maps it to the .ts file)."""
    try:
        text = _read(os.path.join(folder, "tsconfig.json"))
    except OSError:
        return ".js"
    return ".ts" if re.search(r'"(rewriteRelativeImportExtensions|allowImportingTsExtensions)"\s*:\s*true', text) else ".js"


def _engine_doc(engine, client_path, folder="."):
    key = {"godot": "godot", "unity": "csharp", "dotnet": "csharp", "web": "web", "python": "python", "love": "lua",
           "defold": "lua", "rust": "rust", "java": "java", "cpp": "cpp", "unreal": "cpp"}.get(engine, "http")
    text = _read(os.path.join(KIT, "engines", key + ".md")).replace("\r\n", "\n")
    head, code = text.split("\n---\n", 1)
    language = head.split("\n", 1)[0].split(":", 1)[1].strip()
    setup = head.split("\n", 1)[1].strip()
    client_path = client_path or {"web": "kinloom/kinloom.js", "unity": "Assets/Kinloom/Kinloom.cs",
                                  "dotnet": "Kinloom/Kinloom.cs", "love": "kinloom.lua", "defold": "kinloom/kinloom.lua",
                                  "rust": "src/kinloom.rs", "java": "src/main/java/kinloom/Kinloom.java",
                                  "cpp": "kinloom.hpp", "unreal": "Source/kinloom.hpp"}.get(engine)
    if client_path:
        # imports are relative to the importing file: code in src/ imports ./kinloom/kinloom.js
        imp = "./kinloom/" + os.path.basename(client_path) if engine == "web" else "./" + client_path
        if client_path.endswith(".ts"):
            imp = imp[:-3] + _ts_import_extension(folder)
        req = client_path[:-4].replace("/", ".") if client_path.endswith(".lua") else client_path
        setup = setup.replace("{client_path}", client_path).replace("{import_path}", imp).replace("{require_path}", req)
        code = code.replace("{import_path}", imp).replace("{require_path}", req)
    return language, setup, code.strip()


def guide(engine="python", client_path=None, folder="."):
    """The short instructions every coding agent gets (also served by `kinloom mcp` and `kinloom guide`)."""
    language, setup, code = _engine_doc(engine, client_path, folder)
    text = _read(os.path.join(KIT, "guide.md")).replace("\r\n", "\n")
    return text.replace("{setup}", setup).replace("{language}", language).replace("{code}", code).strip() + "\n"


def calls(lang):
    """Every call once, in the game's language (kit/calls.md): what the brief shows, so no call has to be guessed."""
    text = _read(os.path.join(KIT, "calls.md")).replace("\r\n", "\n")
    return text.split("\n## %s\n" % lang, 1)[1].split("\n## ", 1)[0].strip()


def brief(engine="python", client_path=None, folder="."):
    """What every agent reads in every session (AGENTS.md, CLAUDE.md...): the workflow and the rules, about 2 KB.
    The full reference (every call, 39 patterns) stays in KINLOOM.md and the Claude skill, read when needed."""
    from .add import LANGUAGE
    language, setup, code = _engine_doc(engine, client_path, folder)
    lang = LANGUAGE.get(engine, "http")
    snippet = calls(lang)
    if lang != "http":                   # the import and the client, from the engine's reference: the one line agents need
        head = []
        for line in code.strip("`\n").split("\n")[1:]:
            if re.search(r"[Cc]haracter\(|Characters with a soul", line):
                break
            head.append(line)
        head = "\n".join(head).strip()
        if head:
            snippet = head + "\n\n" + snippet
    text = _read(os.path.join(KIT, "brief.md")).replace("\r\n", "\n")
    return text.replace("{setup}", setup).replace("{language}", language).replace("{snippet}", snippet).replace("{fence}", "text" if lang == "http" else lang).strip() + "\n"


def cookbook():
    return _read(os.path.join(KIT, "cookbook.md")).replace("\r\n", "\n")


def _section(existing, body):
    block = "%s\n%s\n%s" % (START, body.strip(), END)
    if START in existing and END in existing:
        before, rest = existing.split(START, 1)
        after = rest.split(END, 1)[1]
        return before + block + after
    if existing.strip():
        return existing.rstrip() + "\n\n" + block + "\n"
    return block + "\n"


def _upsert(path, body):
    old = _read(path) if os.path.exists(path) else ""
    nl = "\r\n" if "\r\n" in old else "\n"
    new = _section(old.replace("\r\n", "\n"), body).replace("\n", nl)
    if new != old:
        _write(path, new)
        return True
    return False


SHORT = ("This game uses **Kinloom** for anything a model does while it runs (choices, content, actions, lines, talk). "
         "Read `KINLOOM.md` before adding any AI feature, and use its 7 calls instead of writing prompts, HTTP, "
         "JSON parsing or retries. `kinloom guide` prints the same instructions.")


# The agents with files of their own (AGENTS.md is always written: Codex and most others read it): the commands that
# show one is installed, and the files or folders of a project that already uses it.
AGENTS = (
    ("claude-code", ("claude",), ("CLAUDE.md", ".claude")),
    ("gemini-cli", ("gemini",), ("GEMINI.md", ".gemini")),
    ("opencode", ("opencode",), (".opencode", "opencode.json")),
    ("cursor", ("cursor", "cursor-agent"), (".cursor", ".cursorrules")),
    ("copilot", (), (os.path.join(".github", "copilot-instructions.md"),)),
    ("windsurf", ("windsurf",), (".windsurfrules", ".windsurf")),
    ("aider", ("aider",), (".aider.conf.yml", ".aider.chat.history.md", ".aider.input.history")),
)


def _which(exe):
    from . import harness
    return harness._which(exe)


def detect_agents(folder):
    """The agents installed on this machine or already used by the project in `folder`, in AGENTS order."""
    return [name for name, exes, marks in AGENTS
            if any(_which(e) for e in exes) or any(os.path.exists(os.path.join(folder, m)) for m in marks)]


def _chosen(folder, agents):
    if agents == "all":
        return [name for name, _, _ in AGENTS]
    if agents == "minimal":
        return ["claude-code", "opencode"]
    return detect_agents(folder)


def write_instructions(folder, engine, client_path, agents="auto"):
    """Writes KINLOOM.md (full), AGENTS.md and the files of the chosen agents (`agents`: "auto" = the ones found here,
    "all", "minimal" = Claude Code and opencode). Returns (the paths written, the agents written for)."""
    names = _chosen(folder, agents)
    core = guide(engine, client_path, folder)
    full = core + "\n---\n\n" + cookbook()
    written = []
    _write_if_changed(os.path.join(folder, "KINLOOM.md"),
                      "<!-- Written by `kinloom init` %s; re-running it replaces this file. -->\n\n%s" % (__version__, full))
    written.append("KINLOOM.md")
    body = brief(engine, client_path, folder)
    targets = [("AGENTS.md", "")]
    targets += [(rel, name) for name, rel in (("claude-code", "CLAUDE.md"),
                                              ("copilot", os.path.join(".github", "copilot-instructions.md")),
                                              ("gemini-cli", "GEMINI.md"), ("windsurf", ".windsurfrules"))
                if name in names]
    for rel, _ in targets:
        _upsert(os.path.join(folder, rel), body)
        written.append(rel.replace(os.sep, "/"))
    for rel, text in _commands(names):
        _write_if_changed(os.path.join(folder, rel), text)
        written.append(rel.replace(os.sep, "/"))
    if "claude-code" in names:
        skill = ("---\nname: kinloom\ndescription: Add AI to this game with Kinloom: anything a model "
                 "does while the game runs (choices and numbers, generated content of any shape, calls to game functions, lines, "
                 "conversation, crowds). Use for any request where the game should use AI, whatever it is.\n---\n\n" + core + "\nPatterns: `KINLOOM.md`.\n")
        _write_if_changed(os.path.join(folder, ".claude", "skills", "kinloom", "SKILL.md"), skill)
        written.append(".claude/skills/kinloom/SKILL.md")
    if "aider" in names and not os.path.exists(os.path.join(folder, ".aider.conf.yml")):
        _write(os.path.join(folder, ".aider.conf.yml"),
               "# Written by `kinloom init`: aider reads the Kinloom instructions in every session.\nread:\n  - AGENTS.md\n")
        written.append(".aider.conf.yml")
    if "cursor" in names:
        cursor = ("---\ndescription: Kinloom, the AI layer of this game. Use for anything a model should do "
                  "while the game runs.\nalwaysApply: true\n---\n\n" + body)
        _write_if_changed(os.path.join(folder, ".cursor", "rules", "kinloom.mdc"), cursor)
        written.append(".cursor/rules/kinloom.mdc")
    return written, names


COMMAND = """Add this to the game with Kinloom: {args}

1. Read the Kinloom part of AGENTS.md (or CLAUDE.md): it shows every call in this game's language. Pick the call by
   what the game needs back; if unsure, run `kinloom recipe "{args}"` and follow it.
2. A character people talk to: `kinloom add NAME "who they are" [--voice "how they sound"] [--tools "give(item)"
   --trust give=0.3]`, then call it from the game (no declaration code: it lives in kinloom.json).
3. Wire it where the game needs it, with the example as the offline answer. Write no prompts, HTTP calls, JSON parsing,
   retries or fallbacks of your own. `speak` gives None when no voice can speak: then show the text.
4. Run `kinloom check`, then `kinloom run -- <the command that starts the game>`, fix what the summary shows, and say
   in two lines what was added and how to try it.
"""


def _commands(names):
    """/kinloom <request> in the chosen agents that read project slash commands."""
    what = ("Add AI to this game with Kinloom: anything a model does while it runs (choices, content, actions, lines, "
            "conversation, voice)")
    out = []
    if "claude-code" in names:
        out.append((os.path.join(".claude", "commands", "kinloom.md"),
                    "---\ndescription: %s\nargument-hint: <what you want, in plain words>\n---\n\n" % what + COMMAND.format(args="$ARGUMENTS")))
    if "opencode" in names:
        out.append((os.path.join(".opencode", "commands", "kinloom.md"),
                    "---\ndescription: %s\n---\n\n" % what + COMMAND.format(args="$ARGUMENTS")))
    if "cursor" in names:
        out.append((os.path.join(".cursor", "commands", "kinloom.md"),
                    "# Kinloom\n\n" + COMMAND.format(args="<the request written after /kinloom>")))
    if "gemini-cli" in names:
        prompt = COMMAND.format(args="{{args}}")          # no triple quotes in COMMAND: a valid TOML string
        out.append((os.path.join(".gemini", "commands", "kinloom.toml"),
                    'description = "Add any AI feature to this game with Kinloom"\nprompt = """\n%s"""\n' % prompt))
    return out


def wizard(folder=".", ask=input, agents=None):
    """`kinloom init` for a person at a terminal: a few questions (Enter keeps the default), the rest automatic.
    Agents and scripts skip it (`--yes`, or no terminal). Ctrl+C leaves cleanly."""
    try:
        return _wizard(folder, ask, agents)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Run `kinloom init` again at any time (it only adds or refreshes Kinloom's own files).")
        return 1


def _wizard(folder, ask, agents=None):
    folder = os.path.abspath(folder)
    found = detect(folder)
    print("Kinloom %s: AI for the game in %s\n" % (__version__, folder))
    print("1/3  Engine")
    engine = (ask("     Detected: %s. Enter to keep, or type one (%s): " % (found, ", ".join(ENGINES))).strip().lower()
              or found)
    if engine not in ENGINES:
        print("     unknown engine %r: keeping %s" % (engine, found))
        engine = found
    print("\n2/3  Your coding agent")
    here = detect_agents(folder)
    if agents is None:
        pick = ask("     Instructions in AGENTS.md (Codex, Cursor, Copilot, opencode... read it)%s. Enter: that. "
                   "Every agent's own file too: a. Only AGENTS.md + CLAUDE.md: m " %
                   (" and for the agents found here: %s" % ", ".join(here) if here else "")).strip().lower()
        agents = "all" if pick.startswith("a") else "minimal" if pick.startswith("m") else "auto"
    _choose_model(folder, ask)
    print()
    code = run(folder, engine, agents)
    if code:
        return code
    print("\n3/3  A first idea (optional: your agent can do all of this later)")
    idea = ask("     What should AI do in this game? In plain words (Enter to skip): ").strip()
    if idea:
        from .recipe import recipe
        text = recipe(idea, engine)
        print("\n" + "\n".join("     " + line for line in text.splitlines()[:14]))
        print("     ... (the whole recipe: kinloom recipe \"%s\"; or ask your agent: /kinloom %s)" % (idea, idea))
    name = ask("\n     Someone people can talk to? Name (Enter to skip): ").strip()
    if name:
        soul = ask("     Who is %s, in one sentence: " % name).strip()
        voice = ask("     How does %s sound when speaking? e.g. low, tired, warm (Enter: skip): " % name).strip()
        tools = ask("     What can %s do in the game? e.g. give(item), follow (Enter: nothing): " % name).strip()
        trust = []
        if tools:
            from .add import parse_tools
            first = next(iter(parse_tools(tools)), "")
            level = ask("     Use %r only for people %s likes at least (0 to 1, Enter: anyone): " % (first, name)).strip()
            if level:
                trust = ["%s=%s" % (first, level)]
        from .add import add
        try:
            print("\n" + add(folder, name, soul, tools, trust, engine=engine, voice=voice))
            print("\nTry %s now: kinloom talk %s%s" % (name, name, " --voice" if voice else ""))
        except ValueError as e:
            print("could not add %s: %s (try again with kinloom add)" % (name, e))
    print("\nDone. In your coding agent, type /kinloom <what you want> (Claude Code, Cursor, Gemini CLI, opencode), or "
          "just ask in plain words. `kinloom` alone shows the model and voice in use; `kinloom speak \"hello\"` lets "
          "you hear the voice.")
    return 0


def _choose_model(folder, ask):
    """Where answers come from: an API key (environment) or the coding agent's subscription. Asked only when an agent
    is installed here (otherwise a key is the only choice, and nothing needs asking)."""
    from . import config
    from .harness import found
    agents = found()
    if not agents:
        return
    try:
        current = config.load(folder).get("provider")
    except config.ConfigError:
        return
    print("\n     The model: an API key from your environment, or the subscription of your coding agent (%s)." %
          ", ".join(agents))
    pick = ask("     Enter: %s. Or type %s: " % ("keep %s" % current if current else "an API key", " / ".join(agents))).strip().lower()
    if pick not in agents:
        if pick:
            print("     unknown choice %r: nothing changed" % pick)
        return
    model = ask("     Its model (Enter: the agent's default%s): " % (", e.g. haiku: fast" if pick == "claude-code" else "")).strip()
    try:
        from .harness import Harness
        Harness(pick, model or None, pool=0)
        config.update(folder, provider=pick, model=model or None)
        print("     %s answers with your plan (kinloom use key: back to an API key)." % pick)
    except (ValueError, config.ConfigError) as e:
        print("     not changed: %s" % e)


def _write_if_changed(path, text):
    if os.path.exists(path) and _read(path) == text:
        return False
    _write(path, text)
    return True


def _gitignore(folder):
    path = os.path.join(folder, ".gitignore")
    old = _read(path) if os.path.exists(path) else ""
    if ".kinloom/" in old.split():
        return False
    nl = "\r\n" if "\r\n" in old else "\n"
    _write(path, old + ("" if not old or old.endswith(("\n",)) else nl) + "# Kinloom memory (per player, not source)" + nl + ".kinloom/" + nl)
    return True


# ---------------- run ----------------

def setup(folder=".", engine=None, agents="auto"):
    """Does everything; returns a dict describing what was done (used by the CLI, the MCP server and tests)."""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise FileNotFoundError("no such folder: %s" % folder)
    engine = (engine or detect(folder)).lower()
    if engine not in ENGINES:
        raise ValueError("unknown engine %r (choose: %s)" % (engine, ", ".join(ENGINES)))
    files, client_path = install_client(folder, engine)
    written, names = write_instructions(folder, engine, client_path, agents)
    files += written
    if _gitignore(folder):
        files.append(".gitignore (.kinloom/)")
    return {"folder": folder, "engine": engine, "client": client_path, "files": files, "agents": names}


def run(folder=".", engine=None, agents="auto"):
    from . import config
    try:
        done = setup(folder, engine, agents)
    except (FileNotFoundError, ValueError) as e:
        print("error: %s" % e)
        return 2
    print("Kinloom %s set up %s (%s)" % (__version__, done["folder"], done["engine"]))
    for f in done["files"]:
        print("  wrote " + f)
    print("agents: %s" % ("AGENTS.md + " + ", ".join(done["agents"]) if done["agents"] else
                          "AGENTS.md only (no other coding agent found here; their own files: kinloom init --agents all)"))
    try:
        provider = config.provider(config.load(done["folder"]))
    except config.ConfigError as e:
        provider = None
        print("\nkinloom.json: %s" % e)
    if provider is not None:
        print("\nmodel: %s (%s)" % (getattr(provider, "name", "model"), getattr(provider, "model", "") or "its default model"))
        if getattr(provider, "missing", None):
            print("  but %s: characters answer offline until it is." % provider.missing)
        close = getattr(provider, "close", None)
        if close is not None:
            close()
    else:
        from .harness import found
        agents = found()
        print("\nmodel: none yet. The game works, but characters only say your lines and examples: no AI yet.\n"
              "  Two ways, your choice: one API key in your environment (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, or "
              "OPENAI_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY... + KINLOOM_MODEL), "
              "or your coding agent's subscription: kinloom use claude-code (or codex, gemini-cli, opencode)%s." %
              ("; installed here: " + ", ".join(agents) if agents else ""))
    from .voice import detect_voice
    heard = detect_voice()
    print("voice: %s" % (heard.describe() if heard is not None else
                         "none: text only (ELEVENLABS_API_KEY or OPENAI_API_KEY for voices; the system's voice is used "
                         "where there is one)"))
    print("\nNext: ask your coding agent, in plain words, anything, e.g. \"the weather follows how I play\", "
          "\"generate each new level\" or \"a blacksmith I can talk to\"; or type /kinloom <request> (Claude Code, Cursor, "
          "Gemini CLI, opencode).\nIt reads the instructions just written and uses kinloom recipe / kinloom add / "
          "kinloom run -- <your game command>.")
    return 0
